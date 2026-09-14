from app.processing.hashing import author_hash, content_hash


def test_content_hash_changes_only_when_text_changes() -> None:
    original = content_hash("Terminal crashes", "Split the terminal twice.")

    assert content_hash("Terminal crashes ", "Split the terminal twice.") == original
    assert content_hash("Terminal crashes", "Split the terminal three times.") != original


def test_author_hash_hides_login_and_ignores_case() -> None:
    hashed = author_hash("github", "OctoCat")

    assert "octocat" not in hashed.lower()
    assert hashed == author_hash("github", "octocat")
    assert hashed != author_hash("csv", "octocat")
