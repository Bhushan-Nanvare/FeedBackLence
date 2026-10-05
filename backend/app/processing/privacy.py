"""Remove obvious personal details from feedback that did not come from a public source.

GitHub issues are already public, but a spreadsheet of support tickets or a widget on a
website can carry email addresses and phone numbers. Those are stripped on the way in, so
they are never stored and never reach an AI model.
"""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")
# A run of digits with the usual separators: +1 (555) 123-4567, 07700 900123, and so on.
PHONE_SHAPED = re.compile(r"(?<![\w-])\+?\d[\d\s().-]{5,}\d(?![\w-])")
# Dates and version numbers look similar but are not personal details.
DATE_LIKE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
VERSION_LIKE = re.compile(r"\d+\.\d+\.\d+")
MIN_PHONE_DIGITS = 7
MAX_PHONE_DIGITS = 15


def scrub_personal_data(text: str) -> str:
    if not text:
        return text
    return PHONE_SHAPED.sub(_mask_phone, EMAIL.sub("[email]", text))


def _mask_phone(match: re.Match[str]) -> str:
    value = match.group(0)
    if DATE_LIKE.search(value) or VERSION_LIKE.search(value):
        return value
    digits = sum(character.isdigit() for character in value)
    if MIN_PHONE_DIGITS <= digits <= MAX_PHONE_DIGITS:
        return "[phone]"
    return value
