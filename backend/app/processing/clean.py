"""Turn raw feedback text into the plain description that tagging and embeddings read.

Issue templates, environment dumps, logs and screenshots make unrelated reports look alike,
so they are stripped before any AI step sees the text.
"""

import re

MAX_CLEAN_CHARS = 4000
MAX_CODE_LINE_CHARS = 200

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DETAILS_BLOCK = re.compile(r"<details\b.*?</details>", re.DOTALL | re.IGNORECASE)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# Replies often quote earlier comments ("> ..."), including their code blocks.
_BLOCKQUOTE_MARKER = re.compile(r"^(?:[ \t]*>)+[ \t]?", re.MULTILINE)
_SINGLE_LINE_FENCE = re.compile(r"```([^`\n]+)```")
_FENCED_CODE = re.compile(
    r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)^[ \t]*\1[`~]*[ \t]*$", re.DOTALL | re.MULTILINE
)
_UNCLOSED_FENCE = re.compile(r"^[ \t]*(?:`{3,}|~{3,}).*", re.DOTALL | re.MULTILINE)
_STRAY_BACKTICKS = re.compile(r"`{3,}")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_BOLD_MARKER = re.compile(r"\*\*")
_HTML_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# "Type: <b>Bug</b>" is added by VS Code's in-app issue reporter.
_REPORTER_TYPE_LINE = re.compile(r"^Type:\s*<b>.*$", re.MULTILINE)
# Environment details and template questions that every report repeats.
_BOILERPLATE_LINE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:"
    r"Does this issue occur when all extensions are disabled\?"
    r"|(?:VS ?Code|OS|Remote OS|Electron|Chromium|Node\.js|V8)\s+version"
    r"|Install (?:Type|Location)"
    r"|Background Updates"
    r"|Modes"
    r")\s*:.*$",
    re.MULTILINE | re.IGNORECASE,
)
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_HEADING_MARKER = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
# Bullets or numbers with nothing after them, including unticked task boxes ("- [ ]").
_EMPTY_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])(?:\s*\[[ xX]?\])?\s*$", re.MULTILINE)
_EXTRA_BLANK_LINES = re.compile(r"\n{3,}")


def clean_body(raw: str | None) -> str:
    if not raw:
        return ""

    text = raw.replace("\r\n", "\n")
    text = _HTML_COMMENT.sub("", text)
    text = _DETAILS_BLOCK.sub("", text)
    text = _MARKDOWN_IMAGE.sub("[image]", text)
    text = _HTML_IMAGE.sub("[image]", text)
    text = _BLOCKQUOTE_MARKER.sub("", text)
    text = _SINGLE_LINE_FENCE.sub(r"\1", text)
    text = _FENCED_CODE.sub(_first_code_line, text)
    text = _UNCLOSED_FENCE.sub("", text)
    text = _STRAY_BACKTICKS.sub("", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _REPORTER_TYPE_LINE.sub("", text)
    text = _BOLD_MARKER.sub("", text)
    text = _BOILERPLATE_LINE.sub("", text)
    text = _HTML_BREAK.sub("\n", text)
    text = _HTML_TAG.sub("", text)
    text = _TABLE_ROW.sub("", text)
    text = _HEADING_MARKER.sub("", text)
    text = _EMPTY_LIST_ITEM.sub("", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _EXTRA_BLANK_LINES.sub("\n\n", text).strip()
    return _truncate(text, MAX_CLEAN_CHARS)


def _first_code_line(match: re.Match[str]) -> str:
    # The first line of a log or stack trace is usually the error message; the rest is noise.
    for line in match.group(2).splitlines():
        if line.strip():
            return line.strip()[:MAX_CODE_LINE_CHARS]
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(None, 1)[0] + " …"
