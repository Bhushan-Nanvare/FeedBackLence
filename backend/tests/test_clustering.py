from collections.abc import Callable

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.models import FeedbackItem, ItemEmbedding, Theme, ThemeItem, ThemeWeeklyStat, Workspace
from app.themes.assignment import assign_leftover_items
from app.themes.clustering import (
    Cluster,
    _match_previous_themes,
    _pick_name,
    cluster_workspace,
    request_clustering,
)

MakeItem = Callable[..., FeedbackItem]
AddItem = Callable[..., FeedbackItem]


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(7)


def vector_near(rng: np.random.Generator, axis: int, noise: float = 0.02) -> list[float]:
    """A vector pointing along one axis, nudged slightly, so groups are clearly separate."""
    vector = np.zeros(EMBEDDING_DIMENSIONS, dtype=np.float32)
    vector[axis] = 1.0
    vector += rng.normal(0, noise, EMBEDDING_DIMENSIONS).astype(np.float32)
    return (vector / np.linalg.norm(vector)).tolist()


@pytest.fixture
def add_item(db: Session, make_item: MakeItem) -> AddItem:
    def add(number: int, vector: list[float], *, title: str | None = None) -> FeedbackItem:
        item = make_item(number)
        if title is not None:
            item.title = title
        db.add(
            ItemEmbedding(
                item_id=item.id,
                workspace_id=item.workspace_id,
                embedding=vector,
                model="fake-embedder",
                content_hash=item.content_hash,
            )
        )
        db.commit()
        return item

    return add


def themes_of(db: Session) -> list[Theme]:
    db.expire_all()
    return list(db.scalars(select(Theme).order_by(Theme.item_count.desc(), Theme.id)))


def test_groups_similar_items_and_leaves_one_offs_out(
    db: Session, workspace: Workspace, add_item: AddItem, rng: np.random.Generator
) -> None:
    for number in range(8):
        add_item(number, vector_near(rng, 0), title=f"Terminal crashes on split {number}")
    for number in range(8, 16):
        add_item(number, vector_near(rng, 1), title=f"Chat panel is slow to answer {number}")
    for number in range(16, 24):
        add_item(number, vector_near(rng, 2), title=f"Settings sync fails to finish {number}")
    for offset, number in enumerate(range(90, 95)):
        add_item(number, vector_near(rng, 100 + offset * 30), title=f"A one-off report {number}")

    stats = cluster_workspace(db, workspace.id, min_cluster_size=4)

    themes = themes_of(db)
    assert (stats.themes, stats.new_themes, stats.unsorted) == (3, 3, 5)
    assert [theme.item_count for theme in themes] == [8, 8, 8]
    assert all(theme.name_model == "medoid" for theme in themes)
    assert any(theme.name.startswith("Terminal crashes") for theme in themes)
    assert any(theme.name.startswith("Chat panel") for theme in themes)
    assert all(
        theme.first_seen_at is not None and theme.last_seen_at is not None for theme in themes
    )
    weekly = db.scalars(select(ThemeWeeklyStat)).all()
    assert sum(stat.item_count for stat in weekly) == 24


def test_theme_ids_and_names_survive_the_next_run(
    db: Session, workspace: Workspace, add_item: AddItem, rng: np.random.Generator
) -> None:
    for number in range(6):
        add_item(number, vector_near(rng, 0))
    for number in range(6, 12):
        add_item(number, vector_near(rng, 1))
    cluster_workspace(db, workspace.id, min_cluster_size=4)
    for theme in themes_of(db):
        theme.name = f"named {theme.id}"
        theme.renamed_by_human = True
    db.commit()
    ids_before = {theme.id for theme in themes_of(db)}

    add_item(12, vector_near(rng, 0))
    stats = cluster_workspace(db, workspace.id, min_cluster_size=4)

    themes = themes_of(db)
    assert stats.reused_themes == 2
    assert {theme.id for theme in themes} == ids_before
    assert all(theme.name.startswith("named ") for theme in themes)
    assert [theme.item_count for theme in themes] == [7, 6]


def test_not_enough_items_to_form_a_theme(
    db: Session, workspace: Workspace, add_item: AddItem, rng: np.random.Generator
) -> None:
    for number in range(3):
        add_item(number, vector_near(rng, 0))

    stats = cluster_workspace(db, workspace.id, min_cluster_size=5)

    assert (stats.themes, stats.unsorted) == (0, 3)
    assert themes_of(db) == []


def test_leftover_item_joins_the_closest_theme(
    db: Session, workspace: Workspace, add_item: AddItem, rng: np.random.Generator
) -> None:
    for number in range(6):
        add_item(number, vector_near(rng, 0))
    for number in range(6, 12):
        add_item(number, vector_near(rng, 1))
    cluster_workspace(db, workspace.id, min_cluster_size=4)
    close = add_item(50, vector_near(rng, 0, noise=0.01))
    far = add_item(51, vector_near(rng, 250))

    assigned = assign_leftover_items(db, workspace.id)
    db.commit()

    assert assigned == 1
    members = {row.item_id for row in db.scalars(select(ThemeItem))}
    assert close.id in members
    assert far.id not in members


def test_a_theme_that_grew_by_attachment_is_still_recognised(
    db: Session, workspace: Workspace, add_item: AddItem, rng: np.random.Generator
) -> None:
    """Themes collect leftover reports, so they hold more items than the cluster they came from."""
    clustered = [add_item(number, vector_near(rng, 0)) for number in range(8)]
    attached = [add_item(number, vector_near(rng, 0, noise=0.01)) for number in range(20, 32)]
    theme = Theme(
        workspace_id=workspace.id,
        name="Grew by attachment",
        centroid=vector_near(rng, 0, noise=0.0),
        item_count=20,
        name_model="medoid",
    )
    db.add(theme)
    db.flush()
    for item in clustered + attached:
        db.add(
            ThemeItem(item_id=item.id, theme_id=theme.id, workspace_id=workspace.id, similarity=0.9)
        )
    db.commit()

    cluster = Cluster(
        item_ids=[item.id for item in clustered],
        similarities=[0.95] * len(clustered),
        centroid=vector_near(rng, 0, noise=0.0),
        name_candidate_ids=[clustered[0].id],
    )
    matches = _match_previous_themes(db, workspace.id, [cluster], 0.5)

    assert matches == {0: theme.id}


def test_theme_names_skip_titles_that_say_nothing() -> None:
    titles = {1: "bug", 2: "Not loading", 3: "Terminal crashes when splitting a pane"}

    assert _pick_name([1, 2, 3], titles) == "Terminal crashes when splitting a pane"
    # When every title is vague, the one that says the most wins.
    assert _pick_name([1, 2], titles) == "Not loading"
    assert _pick_name([9], {}) == "Unnamed theme"


def test_request_clustering_reuses_a_job_that_has_not_started(
    db: Session, workspace: Workspace
) -> None:
    first = request_clustering(db, workspace.id)
    db.commit()

    assert request_clustering(db, workspace.id).id == first.id
