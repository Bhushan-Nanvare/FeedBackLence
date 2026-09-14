import hashlib


def content_hash(title: str, body_clean: str) -> str:
    """Fingerprint of the text AI steps read; an unchanged hash means no re-processing."""
    return hashlib.sha256(f"{title.strip()}\n{body_clean}".encode()).hexdigest()


def author_hash(provider: str, login: str) -> str:
    """Pseudonymous author id: enough to count distinct reporters without storing who they are."""
    return hashlib.sha256(f"{provider}:{login.lower()}".encode()).hexdigest()
