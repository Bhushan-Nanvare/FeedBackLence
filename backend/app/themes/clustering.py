"""Group similar feedback into themes.

Items are clustered by their vectors with HDBSCAN, which leaves one-off reports out instead
of forcing everything into a group. Each run matches its clusters against the previous run's
themes, so a theme keeps its id, and its name, as new feedback arrives.
"""

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA
from sqlalchemy import Date, cast, delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jobs import queue
from app.models import FeedbackItem, ItemEmbedding, Job, Theme, ThemeItem, ThemeWeeklyStat
from app.themes.assignment import assign_leftover_items
from app.themes.vectors import unit_vectors

logger = logging.getLogger(__name__)

CLUSTER_ITEMS_JOB = "cluster_items"
# A theme with no better name borrows the title of one of its most typical items.
MEDOID_NAME_MODEL = "medoid"
MAX_NAME_CHARS = 120
# Titles shorter than this ("bug", "Not loading") say too little to name a theme.
MIN_NAME_CHARS = 25
NAME_CANDIDATES = 10


@dataclass
class ClusterStats:
    items: int = 0
    themes: int = 0
    new_themes: int = 0
    reused_themes: int = 0
    attached_leftovers: int = 0
    unsorted: int = 0


@dataclass(frozen=True)
class Cluster:
    item_ids: list[int]
    similarities: list[float]
    centroid: list[float]
    # The most typical items, closest to the centre first: one of them names the theme.
    name_candidate_ids: list[int]

    @property
    def coherence(self) -> float:
        """How tightly the members sit around the centre, from 0 to 1."""
        return sum(self.similarities) / len(self.similarities)


def request_clustering(session: Session, workspace_id: int) -> Job:
    """Queue a clustering run, reusing one that hasn't started yet. The caller commits."""
    payload = {"workspace_id": workspace_id}
    existing = queue.find_active(session, CLUSTER_ITEMS_JOB, payload, statuses=("queued",))
    return existing or queue.enqueue(session, CLUSTER_ITEMS_JOB, payload, workspace_id=workspace_id)


def run_cluster_items_job(session: Session, payload: dict[str, Any]) -> None:
    workspace_id = payload["workspace_id"]
    stats = cluster_workspace(session, workspace_id)
    logger.info("clustered workspace %s: %s", workspace_id, asdict(stats))


def cluster_workspace(
    session: Session, workspace_id: int, *, min_cluster_size: int | None = None
) -> ClusterStats:
    settings = get_settings()
    min_size = min_cluster_size or settings.cluster_min_size

    rows = session.execute(
        select(ItemEmbedding.item_id, ItemEmbedding.embedding)
        .where(ItemEmbedding.workspace_id == workspace_id)
        .order_by(ItemEmbedding.item_id)
    ).all()
    stats = ClusterStats(items=len(rows), unsorted=len(rows))
    if len(rows) < min_size:
        return stats

    item_ids = [row.item_id for row in rows]
    vectors = unit_vectors([row.embedding for row in rows])
    labels = HDBSCAN(
        min_cluster_size=min_size, min_samples=settings.cluster_min_samples, copy=True
    ).fit_predict(_squeeze(vectors, settings.cluster_pca_dimensions))
    # Centres stay in the original space, so they can be compared with stored vectors.
    clusters = [
        cluster
        for cluster in _build_clusters(item_ids, vectors, labels)
        if cluster.coherence >= settings.cluster_min_coherence
    ]
    stats.themes = len(clusters)
    if not clusters:
        return stats

    matches = _match_previous_themes(
        session, workspace_id, clusters, settings.theme_match_min_overlap
    )
    session.execute(delete(ThemeItem).where(ThemeItem.workspace_id == workspace_id))
    names = _titles(
        session, [item_id for cluster in clusters for item_id in cluster.name_candidate_ids]
    )

    for index, cluster in enumerate(clusters):
        theme = _theme_for(session, workspace_id, cluster, matches.get(index), names, stats)
        session.add_all(
            ThemeItem(
                item_id=item_id,
                theme_id=theme.id,
                workspace_id=workspace_id,
                similarity=similarity,
            )
            for item_id, similarity in zip(cluster.item_ids, cluster.similarities, strict=True)
        )

    session.flush()
    _refresh_theme_rollups(session, workspace_id)
    stats.attached_leftovers = assign_leftover_items(session, workspace_id)
    _refresh_theme_rollups(session, workspace_id)
    _refresh_weekly_stats(session, workspace_id)

    stats.unsorted = len(rows) - (
        session.scalar(
            select(func.count())
            .select_from(ThemeItem)
            .where(ThemeItem.workspace_id == workspace_id)
        )
        or 0
    )
    session.commit()
    return stats


def _squeeze(vectors: np.ndarray, dimensions: int) -> np.ndarray:
    """Drop to fewer dimensions, where distances separate groups more clearly."""
    components = min(dimensions, vectors.shape[0] - 1, vectors.shape[1])
    if components < 2:
        return vectors
    reduced = PCA(n_components=components, random_state=0).fit_transform(vectors)
    return unit_vectors(reduced)


def _build_clusters(item_ids: list[int], vectors: np.ndarray, labels: np.ndarray) -> list[Cluster]:
    clusters = []
    for label in sorted({int(value) for value in labels if value >= 0}):
        members = np.flatnonzero(labels == label)
        centroid = unit_vectors([vectors[members].mean(axis=0)])[0]
        similarities = vectors[members] @ centroid
        most_typical_first = np.argsort(-similarities)
        clusters.append(
            Cluster(
                item_ids=[item_ids[index] for index in members],
                similarities=[float(value) for value in similarities],
                centroid=[float(value) for value in centroid],
                name_candidate_ids=[
                    item_ids[members[index]] for index in most_typical_first[:NAME_CANDIDATES]
                ],
            )
        )
    return sorted(clusters, key=lambda cluster: len(cluster.item_ids), reverse=True)


def _match_previous_themes(
    session: Session, workspace_id: int, clusters: list[Cluster], min_overlap: float
) -> dict[int, int]:
    """Map each new cluster to the previous theme it overlaps most, so ids stay stable."""
    previous: dict[int, set[int]] = {}
    for theme_id, item_id in session.execute(
        select(ThemeItem.theme_id, ThemeItem.item_id).where(ThemeItem.workspace_id == workspace_id)
    ):
        previous.setdefault(theme_id, set()).add(item_id)

    scores = []
    for index, cluster in enumerate(clusters):
        members = set(cluster.item_ids)
        for theme_id, old_members in previous.items():
            smaller = min(len(members), len(old_members))
            shared = len(members & old_members) / smaller if smaller else 0.0
            if shared >= min_overlap:
                scores.append((shared, index, theme_id))

    matches: dict[int, int] = {}
    taken: set[int] = set()
    for _, index, theme_id in sorted(scores, reverse=True):
        if index in matches or theme_id in taken:
            continue
        matches[index] = theme_id
        taken.add(theme_id)
    return matches


def _titles(session: Session, item_ids: list[int]) -> dict[int, str]:
    rows = session.execute(
        select(FeedbackItem.id, FeedbackItem.title).where(FeedbackItem.id.in_(item_ids))
    ).all()
    return {row.id: row.title.strip() for row in rows}


def _pick_name(candidate_ids: list[int], titles: dict[int, str]) -> str:
    """Use the most typical item's title, skipping ones too vague to mean anything."""
    for item_id in candidate_ids:
        title = titles.get(item_id, "")
        if len(title) >= MIN_NAME_CHARS:
            return title[:MAX_NAME_CHARS]
    # Every nearby title is vague, so fall back to the one that says the most.
    with_titles = [titles[item_id] for item_id in candidate_ids if titles.get(item_id)]
    return max(with_titles, key=len)[:MAX_NAME_CHARS] if with_titles else "Unnamed theme"


def _theme_for(
    session: Session,
    workspace_id: int,
    cluster: Cluster,
    theme_id: int | None,
    names: dict[int, str],
    stats: ClusterStats,
) -> Theme:
    if theme_id is not None:
        theme = session.get(Theme, theme_id)
        if theme is not None:
            theme.centroid = cluster.centroid
            stats.reused_themes += 1
            return theme

    theme = Theme(
        workspace_id=workspace_id,
        name=_pick_name(cluster.name_candidate_ids, names),
        centroid=cluster.centroid,
        name_model=MEDOID_NAME_MODEL,
    )
    session.add(theme)
    session.flush()
    stats.new_themes += 1
    return theme


def _refresh_theme_rollups(session: Session, workspace_id: int) -> None:
    totals = (
        select(
            ThemeItem.theme_id.label("theme_id"),
            func.count().label("item_count"),
            func.min(FeedbackItem.external_created_at).label("first_seen_at"),
            func.max(FeedbackItem.external_created_at).label("last_seen_at"),
        )
        .join(FeedbackItem, FeedbackItem.id == ThemeItem.item_id)
        .where(ThemeItem.workspace_id == workspace_id)
        .group_by(ThemeItem.theme_id)
        .subquery()
    )
    session.execute(
        update(Theme)
        .where(Theme.id == totals.c.theme_id)
        .values(
            item_count=totals.c.item_count,
            first_seen_at=totals.c.first_seen_at,
            last_seen_at=totals.c.last_seen_at,
        )
    )
    # Themes that lost every item are kept, so their history and name survive.
    session.execute(
        update(Theme)
        .where(
            Theme.workspace_id == workspace_id,
            Theme.id.not_in(
                select(ThemeItem.theme_id).where(ThemeItem.workspace_id == workspace_id)
            ),
        )
        .values(item_count=0)
    )
    session.flush()


def _refresh_weekly_stats(session: Session, workspace_id: int) -> None:
    workspace_themes = select(Theme.id).where(Theme.workspace_id == workspace_id)
    session.execute(delete(ThemeWeeklyStat).where(ThemeWeeklyStat.theme_id.in_(workspace_themes)))

    week_start = cast(func.date_trunc("week", FeedbackItem.external_created_at), Date)
    weekly_counts = (
        select(ThemeItem.theme_id, week_start, func.count())
        .join(FeedbackItem, FeedbackItem.id == ThemeItem.item_id)
        .where(ThemeItem.workspace_id == workspace_id)
        .group_by(ThemeItem.theme_id, week_start)
    )
    session.execute(
        insert(ThemeWeeklyStat).from_select(["theme_id", "week_start", "item_count"], weekly_counts)
    )
    session.flush()
