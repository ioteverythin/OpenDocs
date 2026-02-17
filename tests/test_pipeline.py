"""Tests for the end-to-end pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from ioteverything.core.models import OutputFormat
from ioteverything.pipeline import Pipeline


@pytest.fixture
def sample_readme_path():
    return str(Path(__file__).parent.parent / "examples" / "sample_readme.md")


class TestPipeline:
    def test_local_all_formats(self, sample_readme_path, tmp_path):
        pipeline = Pipeline()
        result = pipeline.run(
            sample_readme_path,
            output_dir=tmp_path,
            local=True,
        )
        # 3 formats + 1 analysis report = 4
        assert len(result.results) == 4
        assert all(r.success for r in result.results)
        assert result.word_path is not None
        assert result.pdf_path is not None
        assert result.pptx_path is not None

    def test_local_single_format(self, sample_readme_path, tmp_path):
        pipeline = Pipeline()
        result = pipeline.run(
            sample_readme_path,
            output_dir=tmp_path,
            formats=[OutputFormat.WORD],
            local=True,
        )
        # 1 format + 1 analysis report = 2
        assert len(result.results) == 2
        assert all(r.success for r in result.results)
        assert result.word_path is not None
