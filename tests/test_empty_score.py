"""Edge case tests for empty / zero-note scores.

Covers:
- build_musicxml() does not crash on a Score with no parts
- build_musicxml() output on an empty Score is valid XML
- compare_musicxml_semantic() reports 0% recall when GT has notes but
  extraction returns no matching notes
- The empty_score fixture is registered in BUILT_IN_TESTS
"""

import sys
import tempfile
import os
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# ---------------------------------------------------------------------------
# Minimal "no-notes" extraction XML for comparator tests
# ---------------------------------------------------------------------------
_EMPTY_EXTRACTION_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions></attributes>
    </measure>
  </part>
</score-partwise>
"""


class TestEmptyScoreEdgeCase:
    """Edge case tests for empty / zero-note scores."""

    def test_build_musicxml_empty_parts_doesnt_crash(self):
        """Score with no parts — build_musicxml should not raise."""
        from models.score import Score
        from core.musicxml_builder import build_musicxml

        score = Score(parts=[])
        xml_str = build_musicxml(score)
        assert xml_str is not None
        assert len(xml_str) > 0

    def test_build_musicxml_empty_score_is_valid_xml(self):
        """build_musicxml output for an empty Score must be parseable XML."""
        from models.score import Score
        from core.musicxml_builder import build_musicxml

        score = Score(parts=[])
        xml_str = build_musicxml(score)

        # Must parse without raising
        root = etree.fromstring(xml_str.encode("utf-8"))
        assert root is not None
        # Must be a score-partwise document
        assert root.tag == "score-partwise"

    def test_comparator_empty_extraction_zero_recall(self):
        """When GT has notes but extraction has none, overall accuracy is 0%."""
        from core.comparator import compare_musicxml_semantic

        gt_path = FIXTURE_DIR / "empty_score.musicxml"
        assert gt_path.exists(), f"Fixture not found: {gt_path}"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".musicxml", delete=False, encoding="utf-8"
        ) as f:
            f.write(_EMPTY_EXTRACTION_XML)
            tmp_path = f.name

        try:
            result = compare_musicxml_semantic(str(gt_path), tmp_path)
            # GT has 1 rest note; extraction has 0 — nothing matched
            assert result["total_notes_gt"] >= 1, (
                "empty_score.musicxml should have at least 1 rest note in GT"
            )
            assert result["total_notes_matched"] == 0, (
                "Extraction with no notes should match 0 GT notes"
            )
            assert result["scores"]["note_accuracy"] == 0.0, (
                "note_accuracy must be 0% when extraction is empty"
            )
            assert result["scores"]["overall"] == 0.0, (
                "overall must be 0% when extraction is empty"
            )
        finally:
            os.unlink(tmp_path)

    def test_fixture_file_exists(self):
        """The empty_score fixture must be on disk."""
        fixture_path = FIXTURE_DIR / "empty_score.musicxml"
        assert fixture_path.exists(), (
            f"tests/fixtures/empty_score.musicxml is missing — "
            f"the hand-authored fixture was not committed"
        )

    def test_empty_score_in_built_in_tests(self):
        """empty_score must be registered in BUILT_IN_TESTS in test_harness."""
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from test_harness import BUILT_IN_TESTS

        names = {t.name for t in BUILT_IN_TESTS}
        assert "empty_score" in names, (
            "empty_score is not in BUILT_IN_TESTS — Gap #7 promotion is incomplete"
        )

        # Verify the entry has expected metadata
        entry = next(t for t in BUILT_IN_TESTS if t.name == "empty_score")
        assert entry.difficulty == "edge_case", (
            f"empty_score difficulty should be 'edge_case', got '{entry.difficulty}'"
        )
        assert "empty" in entry.tags or "zero_notes" in entry.tags, (
            "empty_score should have 'empty' or 'zero_notes' in tags"
        )
