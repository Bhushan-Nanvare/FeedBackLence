"""Turn a repository's own issue labels into draft "correct answers" for scoring.

Maintainers already sort issues with labels such as "bug" or "terminal". Those labels are a
free head start for the checked set: a person reviews them in the inbox instead of labelling
hundreds of issues from scratch. They are only drafts, because label use is inconsistent.
"""

from collections.abc import Sequence

# Only labels whose meaning is unambiguous.
TYPE_BY_LABEL = {
    "bug": "bug",
    "feature-request": "feature_request",
    "question": "question",
    "*question": "question",
}
# Labels such as "invalid", "*duplicate" or "*caused-by-extension" say how an issue was
# handled, not what kind of feedback it is, so they make poor answers to check against.

AREA_BY_LABEL = {
    "git": "source-control",
    "scm": "source-control",
    "perf": "performance",
    "freeze-slow-crash-leak": "performance",
    "tasks": "testing-tasks",
    "testing": "testing-tasks",
    "keybindings": "settings",
    "profiles": "settings",
    "config": "settings",
    "quick-open": "search",
    "intellisense": "languages",
    "suggest": "languages",
    "snippets": "languages",
    "containers": "remote",
    "ssh": "remote",
    "tunnels": "remote",
    "themes": "workbench",
    "layout": "workbench",
    "menus": "workbench",
    "marketplace": "extensions",
    "update": "install-update",
    "setup": "install-update",
}

# Checked in order, so more specific prefixes come first.
AREA_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("terminal", "terminal"),
    ("notebook", "notebooks"),
    ("debug", "debugging"),
    ("search", "search"),
    ("remote", "remote"),
    ("dev-container", "remote"),
    ("chat", "chat-ai"),
    ("copilot", "chat-ai"),
    ("agent", "chat-ai"),
    ("inline-chat", "chat-ai"),
    ("extension", "extensions"),
    ("settings", "settings"),
    ("accessibility", "accessibility"),
    ("install", "install-update"),
    ("workbench", "workbench"),
    ("editor", "editor"),
    ("diff-editor", "editor"),
    ("languages", "languages"),
    ("typescript", "languages"),
    ("javascript", "languages"),
    ("python", "languages"),
    ("markdown", "languages"),
    ("json", "languages"),
    ("css", "languages"),
    ("html", "languages"),
)


def expected_type(labels: Sequence[str]) -> str | None:
    """The type these labels imply, or None when they say nothing or disagree."""
    types = {TYPE_BY_LABEL[label] for label in labels if label in TYPE_BY_LABEL}
    return types.pop() if len(types) == 1 else None


def expected_area(labels: Sequence[str]) -> str | None:
    """The product area these labels imply, or None when no label matches."""
    for label in labels:
        area = AREA_BY_LABEL.get(label)
        if area is not None:
            return area
        for prefix, prefix_area in AREA_BY_PREFIX:
            if label.startswith(prefix):
                return prefix_area
    return None
