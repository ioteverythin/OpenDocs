"""Tests for the GitHub README fetcher."""

from __future__ import annotations

import pytest

from opendocs.core.fetcher import ReadmeFetcher, is_github_url, parse_github_url


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

class TestParseGithubUrl:
    def test_standard_url(self):
        owner, repo = parse_github_url("https://github.com/octocat/hello-world")
        assert owner == "octocat"
        assert repo == "hello-world"

    def test_url_with_trailing_slash(self):
        owner, repo = parse_github_url("https://github.com/octocat/hello-world/")
        assert owner == "octocat"
        assert repo == "hello-world"

    def test_url_with_subpath(self):
        owner, repo = parse_github_url("https://github.com/octocat/hello-world/tree/main")
        assert owner == "octocat"
        assert repo == "hello-world"

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Not a valid GitHub URL"):
            parse_github_url("https://example.com/not-github")


class TestIsGithubUrl:
    def test_valid(self):
        assert is_github_url("https://github.com/owner/repo") is True

    def test_invalid(self):
        assert is_github_url("./README.md") is False
        assert is_github_url("/home/user/project/README.md") is False


# ---------------------------------------------------------------------------
# Local fetch
# ---------------------------------------------------------------------------

class TestLocalFetch:
    def test_fetch_local_file(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Hello\n\nWorld", encoding="utf-8")

        fetcher = ReadmeFetcher()
        content, name = fetcher.fetch(str(readme))
        assert "# Hello" in content
        assert name == "README"

    def test_fetch_missing_file_raises(self):
        fetcher = ReadmeFetcher()
        with pytest.raises(FileNotFoundError):
            fetcher.fetch("/nonexistent/path/README.md")
