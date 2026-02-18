"""Tests for the table sorting module."""

from __future__ import annotations

import pytest

from opendocs.core.models import (
    DocumentModel,
    Section,
    TableBlock,
    ParagraphBlock,
)
from opendocs.generators.table_sorter import (
    TableSorter,
    SortStrategy,
    _extract_number,
    _classify_table,
    _sort_key_alpha,
    _sort_key_numeric,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc_with_table(
    headers: list[str], rows: list[list[str]]
) -> DocumentModel:
    """Create a minimal DocumentModel with a single table."""
    block = TableBlock(headers=headers, rows=rows)
    section = Section(title="Test", level=1, blocks=[block])
    return DocumentModel(
        sections=[section],
        all_blocks=[block],
    )


# ---------------------------------------------------------------------------
# _extract_number
# ---------------------------------------------------------------------------

class TestExtractNumber:
    def test_plain_integer(self):
        assert _extract_number("42") == 42.0

    def test_plain_float(self):
        assert _extract_number("3.14") == 3.14

    def test_number_with_commas(self):
        assert _extract_number("1,234,567") == 1234567.0

    def test_percentage(self):
        assert _extract_number("99.9%") == 99.9

    def test_value_with_unit(self):
        assert _extract_number("500ms") == 500.0
        assert _extract_number("10 Hz") == 10.0
        assert _extract_number("2 GB") == 2.0

    def test_no_number(self):
        assert _extract_number("hello world") == float("inf")

    def test_mixed_text(self):
        assert _extract_number("Up to 50") == 50.0

    def test_negative(self):
        assert _extract_number("-10") == -10.0

    def test_less_than_prefix(self):
        assert _extract_number("< 500ms") == 500.0


# ---------------------------------------------------------------------------
# _classify_table
# ---------------------------------------------------------------------------

class TestClassifyTable:
    def test_api_table(self):
        block = TableBlock(
            headers=["Endpoint", "Method", "Description"],
            rows=[["/api/foo", "GET", "Get foo"]],
        )
        assert _classify_table(block) == "api"

    def test_metric_table(self):
        block = TableBlock(
            headers=["Metric", "Value"],
            rows=[["Latency", "500ms"]],
        )
        assert _classify_table(block) == "metric"

    def test_feature_table(self):
        block = TableBlock(
            headers=["Feature", "Description"],
            rows=[["Auth", "OAuth2 support"]],
        )
        assert _classify_table(block) == "feature"

    def test_generic_table(self):
        block = TableBlock(
            headers=["Name", "Color"],
            rows=[["Apple", "Red"]],
        )
        assert _classify_table(block) == "generic"

    def test_no_headers(self):
        block = TableBlock(rows=[["a", "b"]])
        assert _classify_table(block) == "generic"


# ---------------------------------------------------------------------------
# Sort strategies
# ---------------------------------------------------------------------------

class TestAlphaSort:
    def test_sort_by_first_column(self):
        sorter = TableSorter("alpha")
        block = TableBlock(
            headers=["Name", "Value"],
            rows=[
                ["Banana", "2"],
                ["Apple", "1"],
                ["Cherry", "3"],
            ],
        )
        result = sorter.sort_table(block)
        assert result.rows[0][0] == "Apple"
        assert result.rows[1][0] == "Banana"
        assert result.rows[2][0] == "Cherry"

    def test_case_insensitive(self):
        sorter = TableSorter("alpha")
        block = TableBlock(
            headers=["Name"],
            rows=[["banana"], ["Apple"], ["cherry"]],
        )
        result = sorter.sort_table(block)
        assert [r[0] for r in result.rows] == ["Apple", "banana", "cherry"]


class TestNumericSort:
    def test_sort_by_numeric_values(self):
        sorter = TableSorter("numeric")
        block = TableBlock(
            headers=["Metric", "Value"],
            rows=[
                ["Latency", "500ms"],
                ["Rate", "10 Hz"],
                ["Uptime", "99.9%"],
            ],
        )
        result = sorter.sort_table(block)
        # 10, 99.9, 500 — ascending
        assert result.rows[0][0] == "Rate"
        assert result.rows[1][0] == "Uptime"
        assert result.rows[2][0] == "Latency"


class TestColumnSort:
    def test_sort_by_column_1(self):
        sorter = TableSorter("column:1")
        block = TableBlock(
            headers=["ID", "Name"],
            rows=[
                ["3", "Charlie"],
                ["1", "Alice"],
                ["2", "Bob"],
            ],
        )
        result = sorter.sort_table(block)
        assert result.rows[0][1] == "Alice"
        assert result.rows[1][1] == "Bob"
        assert result.rows[2][1] == "Charlie"

    def test_sort_by_column_desc(self):
        sorter = TableSorter("column:0:desc")
        block = TableBlock(
            headers=["Name", "Score"],
            rows=[
                ["Alice", "10"],
                ["Charlie", "30"],
                ["Bob", "20"],
            ],
        )
        result = sorter.sort_table(block)
        assert result.rows[0][0] == "Charlie"
        assert result.rows[1][0] == "Bob"
        assert result.rows[2][0] == "Alice"

    def test_numeric_column_detection(self):
        sorter = TableSorter("column:1")
        block = TableBlock(
            headers=["Name", "Score"],
            rows=[
                ["Alice", "30"],
                ["Bob", "10"],
                ["Charlie", "20"],
            ],
        )
        result = sorter.sort_table(block)
        # Column 1 is numeric, so sorted numerically
        assert result.rows[0][1] == "10"
        assert result.rows[1][1] == "20"
        assert result.rows[2][1] == "30"


class TestSmartSort:
    def test_api_table_sorted_by_endpoint(self):
        sorter = TableSorter("smart")
        block = TableBlock(
            headers=["Endpoint", "Method", "Description"],
            rows=[
                ["/api/sensors", "GET", "List sensors"],
                ["/api/alerts", "POST", "Configure alerts"],
                ["/api/readings", "GET", "Get readings"],
            ],
        )
        result = sorter.sort_table(block)
        assert result.rows[0][0] == "/api/alerts"
        assert result.rows[1][0] == "/api/readings"
        assert result.rows[2][0] == "/api/sensors"

    def test_metric_table_sorted_by_name(self):
        sorter = TableSorter("smart")
        block = TableBlock(
            headers=["Metric", "Value"],
            rows=[
                ["Uptime", "99.9%"],
                ["Latency", "500ms"],
                ["Sampling rate", "10 Hz"],
            ],
        )
        result = sorter.sort_table(block)
        assert result.rows[0][0] == "Latency"
        assert result.rows[1][0] == "Sampling rate"
        assert result.rows[2][0] == "Uptime"


class TestNoneSort:
    def test_no_sorting(self):
        sorter = TableSorter("none")
        block = TableBlock(
            headers=["Name"],
            rows=[["C"], ["A"], ["B"]],
        )
        result = sorter.sort_table(block)
        assert result.rows == [["C"], ["A"], ["B"]]


# ---------------------------------------------------------------------------
# Full document processing
# ---------------------------------------------------------------------------

class TestDocumentProcessing:
    def test_process_sorts_all_tables(self):
        sorter = TableSorter("alpha")
        doc = _make_doc_with_table(
            ["Name", "Value"],
            [["Banana", "2"], ["Apple", "1"]],
        )
        result = sorter.process(doc)
        # Check section blocks
        table = result.sections[0].blocks[0]
        assert isinstance(table, TableBlock)
        assert table.rows[0][0] == "Apple"

        # Check all_blocks
        all_table = result.all_blocks[0]
        assert isinstance(all_table, TableBlock)
        assert all_table.rows[0][0] == "Apple"

    def test_single_row_not_sorted(self):
        sorter = TableSorter("alpha")
        block = TableBlock(
            headers=["Name"],
            rows=[["Only"]],
        )
        result = sorter.sort_table(block)
        assert result.rows == [["Only"]]

    def test_empty_table(self):
        sorter = TableSorter("alpha")
        block = TableBlock(headers=["Name"], rows=[])
        result = sorter.sort_table(block)
        assert result.rows == []

    def test_nested_sections(self):
        sorter = TableSorter("alpha")
        table = TableBlock(
            headers=["Name"],
            rows=[["C"], ["A"], ["B"]],
        )
        inner = Section(title="Inner", level=2, blocks=[table])
        outer = Section(title="Outer", level=1, blocks=[], subsections=[inner])
        doc = DocumentModel(
            sections=[outer],
            all_blocks=[table],
        )
        sorter.process(doc)
        sorted_table = doc.sections[0].subsections[0].blocks[0]
        assert isinstance(sorted_table, TableBlock)
        assert sorted_table.rows[0][0] == "A"

    def test_unknown_strategy_defaults_to_smart(self):
        sorter = TableSorter("invalid_strategy")
        assert sorter._strategy == "smart"


# ---------------------------------------------------------------------------
# Preserve headers
# ---------------------------------------------------------------------------

class TestPreservation:
    def test_headers_preserved(self):
        sorter = TableSorter("alpha")
        block = TableBlock(
            headers=["Name", "Value"],
            rows=[["B", "2"], ["A", "1"]],
        )
        result = sorter.sort_table(block)
        assert result.headers == ["Name", "Value"]
        assert result.rows[0][0] == "A"
