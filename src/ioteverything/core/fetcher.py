"""Fetch README content from GitHub repositories or local files."""

from __future__ import annotations

import re
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GITHUB_RAW = "https://raw.githubusercontent.com"
_GITHUB_API = "https://api.github.com/repos"
_GITHUB_URL_RE = re.compile(
    r"(?:https?://)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\s#?]+)"
)

# Typical README filenames in priority order
_README_NAMES = [
    "README.md",
    "readme.md",
    "Readme.md",
    "README.rst",
    "README.txt",
    "README",
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL.

    Raises ValueError if the URL doesn't match the expected pattern.
    """
    m = _GITHUB_URL_RE.search(url)
    if not m:
        raise ValueError(f"Not a valid GitHub URL: {url}")
    return m.group("owner"), m.group("repo").rstrip("/")


def is_github_url(source: str) -> bool:
    """Return True if *source* looks like a GitHub repository URL."""
    return bool(_GITHUB_URL_RE.search(source))


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------

class ReadmeFetcher:
    """Fetches README content from a GitHub repo URL or a local path."""

    def __init__(self, timeout: float = 30.0, github_token: str | None = None):
        self.timeout = timeout
        self.github_token = github_token

    # -- public API ----------------------------------------------------------

    def fetch(self, source: str) -> tuple[str, str]:
        """Fetch README content and return ``(content, repo_name)``.

        *source* can be:
        - A GitHub URL  (``https://github.com/owner/repo``)
        - A local file path (``./README.md`` or ``C:\\path\\to\\README.md``)

        Returns
        -------
        tuple[str, str]
            ``(markdown_content, repo_or_file_name)``
        """
        if is_github_url(source):
            return self._fetch_github(source)
        return self._fetch_local(source)

    # -- private -------------------------------------------------------------

    def _fetch_github(self, url: str) -> tuple[str, str]:
        owner, repo = parse_github_url(url)
        headers: dict[str, str] = {"Accept": "application/vnd.github.v3.raw"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        # Try raw.githubusercontent.com first (no auth required for public repos)
        for name in _README_NAMES:
            raw_url = f"{_GITHUB_RAW}/{owner}/{repo}/HEAD/{name}"
            try:
                resp = httpx.get(raw_url, timeout=self.timeout, follow_redirects=True)
                if resp.status_code == 200:
                    return resp.text, f"{owner}/{repo}"
            except httpx.HTTPError:
                continue

        # Fallback: GitHub contents API
        for name in _README_NAMES:
            api_url = f"{_GITHUB_API}/{owner}/{repo}/contents/{name}"
            try:
                resp = httpx.get(api_url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    return resp.text, f"{owner}/{repo}"
            except httpx.HTTPError:
                continue

        raise FileNotFoundError(
            f"Could not find a README in {owner}/{repo}. "
            "Make sure the repository exists and is public (or supply a token)."
        )

    @staticmethod
    def _fetch_local(path_str: str) -> tuple[str, str]:
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        content = path.read_text(encoding="utf-8")
        return content, path.stem
