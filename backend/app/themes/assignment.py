"""Attach leftover items to an existing theme when they are close enough to its centre."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ItemEmbedding, Theme, ThemeItem
from app.themes.vectors import unit_vectors

logger = logging.getLogger(__name__)


def assign_leftover_items(
    session: Session, workspace_id: int, *, min_similarity: float | None = None
) -> int:
    """Put items with no theme into the nearest one, if they are similar enough.

    Clustering deliberately leaves one-off reports out. This picks up the ones that are
    plainly about an existing theme anyway, and the ones that arrived since the last run.
    """
    settings = get_settings()
    threshold = (
        min_similarity if min_similarity is not None else settings.theme_assign_min_similarity
    )

    themes = session.execute(
        select(Theme.id, Theme.centroid).where(
            Theme.workspace_id == workspace_id, Theme.item_count > 0
        )
    ).all()
    leftovers = session.execute(
        select(ItemEmbedding.item_id, ItemEmbedding.embedding)
        .outerjoin(ThemeItem, ThemeItem.item_id == ItemEmbedding.item_id)
        .where(ItemEmbedding.workspace_id == workspace_id, ThemeItem.item_id.is_(None))
    ).all()
    if not themes or not leftovers:
        return 0

    centroids = unit_vectors([theme.centroid for theme in themes])
    vectors = unit_vectors([row.embedding for row in leftovers])
    similarities = vectors @ centroids.T
    best_theme = similarities.argmax(axis=1)

    assigned = 0
    for row_index, theme_index in enumerate(best_theme):
        similarity = float(similarities[row_index, theme_index])
        if similarity < threshold:
            continue
        session.add(
            ThemeItem(
                item_id=leftovers[row_index].item_id,
                theme_id=themes[theme_index].id,
                workspace_id=workspace_id,
                similarity=similarity,
            )
        )
        assigned += 1

    session.flush()
    return assigned
