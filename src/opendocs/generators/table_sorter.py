"""Sort and organize tables extracted from README documents.

Provides multiple sorting strategies for ``TableBlock`` rows so that
generated documents present tabular data in a logical, consistent order.

Strategies
----------
- **alpha** — sort rows alphabetically by the first column.
- **numeric** — sort rows by the first numeric value found in each row
  (useful for metrics / performance tables).
- **column:N** — sort alphabetically by column *N* (0-indexed).
- **column:N:desc** — sort descending by column *N*.
- **smart** — heuristic: detects whether the table is
  API-reference, metrics, feature-list, etc. and picks the best
  strategy automatically.
- **none** — leave rows in their original order.
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from enum import Enum

from ..core.models import (
    ContentBlock,
    DocumentModel,
    Section,
    TableBlock,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Strategy enum
# ---------------------------------------------------------------------------

class SortStrategy(str, Enum):
    """Built-in table-sorting strategies."""
    NONE = "none"
    ALPHA = "alpha"
    NUMERIC = "numeric"
    SMART = "smart"
    # column:N and column:N:desc are parsed dynamically


# ---------------------------------------------------------------------------
# Sort key helpers
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"-?[\d,]+\.?\d*")
_PERCENTAGE_RE = re.compile(r"([\d.]+)\s*%")
_UNIT_RE = re.compile(
    r"([\d,]+\.?\d*)\s*"
    r"(Hz|hz|ms|s|sec|min|hrs?|KB|MB|GB|TB|%|k|K|M|B)"
)


def _extract_number(text: str) -> float:
    """Extract the first numeric value from a cell, returning ``inf`` when
    nothing numeric is found (so non-numeric rows sort to the end).
    """
    # Check for percentage first
    m = _PERCENTAGE_RE.search(text)
    if m:
        return float(m.group(1))

    # Check for value+unit
    m = _UNIT_RE.search(text)
    if m:
        return float(m.group(1).replace(",", ""))

    # Bare number
    m = _NUMERIC_RE.search(text)
    if m:
        return float(m.group().replace(",", ""))

    return float("inf")


def _sort_key_alpha(row: list[str], col: int = 0) -> str:
    """Case-insensitive alphabetical key from the given column."""
    if col < len(row):
        return row[col].strip().lower()
    return ""


def _sort_key_numeric(row: list[str], col: int | None = None) -> float:
    """Numeric key from the first numeric value found in the row, or
    from a specific column if *col* is given.
    """
    if col is not None and col < len(row):
        return _extract_number(row[col])
    # Scan all columns for the first number
    for cell in row:
        val = _extract_number(cell)
        if val != float("inf"):
            return val
    return float("inf")


# ---------------------------------------------------------------------------
# Smart classification heuristics
# ---------------------------------------------------------------------------

_API_HEADERS = {"endpoint", "method", "route", "url", "path", "api", "verb"}
_METRIC_HEADERS = {
    "metric", "value", "performance", "benchmark", "result",
    "measure", "score", "time", "latency", "rate", "uptime",
}
_FEATURE_HEADERS = {
    "feature", "description", "module", "component", "capability",
    "option", "parameter", "setting", "config", "flag",
}
_STATUS_HEADERS = {"status", "state", "phase", "stage", "version"}


def _classify_table(block: TableBlock) -> str:
    """Classify a table as ``api``, ``metric``, ``feature``, or ``generic``.

    Returns a tag string used by the smart strategy.
    """
    if not block.headers:
        return "generic"

    lower_headers = {h.strip().lower() for h in block.headers}

    if lower_headers & _API_HEADERS:
        return "api"
    if lower_headers & _METRIC_HEADERS:
        return "metric"
    if lower_headers & _FEATURE_HEADERS:
        return "feature"
    if lower_headers & _STATUS_HEADERS:
        return "status"
    return "generic"


# ---------------------------------------------------------------------------
# Core sorter
# ---------------------------------------------------------------------------

class TableSorter:
    """Sort rows within ``TableBlock`` objects in a document model.

    Parameters
    ----------
    strategy
        One of the built-in strategies (``none``, ``alpha``, ``numeric``,
        ``smart``) **or** a column-specific specifier like ``column:2``
        or ``column:1:desc``.
    """

    def __init__(self, strategy: str = "smart") -> None:
        self.strategy_str = strategy.strip().lower()
        self._col: int | None = None
        self._desc: bool = False

        # Parse column:N[:desc]
        if self.strategy_str.startswith("column:"):
            parts = self.strategy_str.split(":")
            try:
                self._col = int(parts[1])
            except (IndexError, ValueError):
                self._col = 0
            self._desc = len(parts) > 2 and parts[2] == "desc"
            self._strategy = "column"
        elif self.strategy_str in {s.value for s in SortStrategy}:
            self._strategy = self.strategy_str
        else:
            logger.warning("Unknown sort strategy '%s', defaulting to 'smart'", strategy)
            self._strategy = SortStrategy.SMART.value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, doc: DocumentModel) -> DocumentModel:
        """Sort all tables in *doc* (mutates in place and returns it)."""
        if self._strategy == SortStrategy.NONE.value:
            return doc

        # Walk all blocks
        for section in doc.sections:
            self._walk_section(section)

        # Also process top-level all_blocks
        for i, block in enumerate(doc.all_blocks):
            if isinstance(block, TableBlock):
                doc.all_blocks[i] = self._sort_table(block)

        return doc

    def sort_table(self, block: TableBlock) -> TableBlock:
        """Sort a single ``TableBlock`` and return it."""
        return self._sort_table(block)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _walk_section(self, section: Section) -> None:
        for i, block in enumerate(section.blocks):
            if isinstance(block, TableBlock):
                section.blocks[i] = self._sort_table(block)
        for sub in section.subsections:
            self._walk_section(sub)

    def _sort_table(self, block: TableBlock) -> TableBlock:
        """Return a new ``TableBlock`` with sorted rows."""
        if len(block.rows) <= 1:
            return block  # nothing to sort

        strategy = self._strategy
        col = self._col
        desc = self._desc

        # Smart strategy: pick the best approach per table
        if strategy == SortStrategy.SMART.value:
            strategy, col, desc = self._pick_smart_strategy(block)

        sorted_rows = self._apply_sort(block.rows, strategy, col, desc)

        return TableBlock(
            headers=block.headers,
            rows=sorted_rows,
        )

    def _pick_smart_strategy(
        self, block: TableBlock
    ) -> tuple[str, int | None, bool]:
        """Heuristically choose the best sort for this table."""
        kind = _classify_table(block)

        if kind == "api":
            # Sort API tables by endpoint (typically column 0)
            return "alpha", 0, False

        if kind == "metric":
            # Sort metrics alphabetically by metric name (col 0)
            return "alpha", 0, False

        if kind == "feature":
            # Sort features alphabetically (col 0)
            return "alpha", 0, False

        if kind == "status":
            return "alpha", 0, False

        # Generic: check if there's a dominant numeric column
        num_col = self._find_numeric_column(block)
        if num_col is not None:
            # Sort numeric descending (biggest first)
            return "numeric", num_col, True

        # Default: alphabetical by first column
        return "alpha", 0, False

    @staticmethod
    def _find_numeric_column(block: TableBlock) -> int | None:
        """Find the column with the most numeric values.

        Returns the column index if > 60 % of rows have numeric data
        in that column, else *None*.
        """
        if not block.rows:
            return None

        n_rows = len(block.rows)
        n_cols = len(block.rows[0]) if block.rows else 0
        best_col: int | None = None
        best_ratio = 0.0

        for c in range(n_cols):
            count = sum(
                1 for row in block.rows
                if c < len(row) and _extract_number(row[c]) != float("inf")
            )
            ratio = count / n_rows if n_rows else 0
            if ratio > best_ratio:
                best_ratio = ratio
                best_col = c

        return best_col if best_ratio > 0.6 else None

    @staticmethod
    def _apply_sort(
        rows: list[list[str]],
        strategy: str,
        col: int | None,
        desc: bool,
    ) -> list[list[str]]:
        """Sort a list of rows using the resolved strategy."""
        if strategy == "alpha":
            key_fn = lambda r: _sort_key_alpha(r, col or 0)
        elif strategy == "numeric":
            key_fn = lambda r: _sort_key_numeric(r, col)
        elif strategy == "column":
            # Check if most values in this column are numeric
            if col is not None and rows:
                nums = sum(
                    1 for r in rows
                    if col < len(r) and _extract_number(r[col]) != float("inf")
                )
                if nums / len(rows) > 0.5:
                    key_fn = lambda r: _sort_key_numeric(r, col)
                else:
                    key_fn = lambda r: _sort_key_alpha(r, col or 0)
            else:
                key_fn = lambda r: _sort_key_alpha(r, col or 0)
        else:
            return rows

        try:
            return sorted(rows, key=key_fn, reverse=desc)
        except Exception as exc:
            logger.warning("Table sort failed: %s", exc)
            return rows
