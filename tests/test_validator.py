"""Tests for the musicxml validation module."""

import sys
import tempfile
import os
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.validator import validate_musicxml_structure

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_valid_returns_true():
    """Valid XML should return (True, '')."""
    valid_xml = FIXTURE_DIR / "simple_melody.musicxml"
    is_valid, error = validate_musicxml_structure(str(valid_xml))
    assert is_valid is True
    assert error == ""


def test_empty_string_returns_false():
    """Empty string should return (False, error message)."""
    is_valid, error = validate_musicxml_structure("")
    assert is_valid is False
    assert "XML parsing failed" in error


def test_malformed_xml_returns_false():
    """Malformed XML should return (False, error message)."""
    malformed_xml = """<?xml version="1.0"?>
<root>
  <unclosed_tag>
</root>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(malformed_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "XML parsing failed" in error
    finally:
        os.unlink(temp_path)


def test_wrong_root_element_returns_false():
    """XML with wrong root element should return (False, error message)."""
    wrong_root_xml = """<?xml version="1.0"?>
<score-part>
  <part>
    <measure number="1">
      <note><pitch><step>C</step><octave>4</octave></pitch></note>
    </measure>
  </part>
</score-part>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(wrong_root_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "Root element is 'score-part'" in error
        assert "expected 'score-partwise'" in error
    finally:
        os.unlink(temp_path)


def test_no_parts_returns_false():
    """XML with no parts should return (False, error message)."""
    no_parts_xml = """<?xml version="1.0"?>
<score-priority version="4.0">
</score-priority>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(no_parts_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "Root element is" in error or "No <part> elements found" in error
    finally:
        os.unlink(temp_path)


def test_part_with_no_measures_returns_false():
    """XML with part but no measures should return (False, error message)."""
    part_no_measures_xml = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
  </part>
</score-partwise>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(part_no_measures_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "Part 0 has no <measure> elements" in error
    finally:
        os.unlink(temp_path)


def test_measure_with_no_notes_returns_false():
    """XML with measure but no notes should return (False, error message)."""
    measure_no_notes_xml = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>1</divisions>
      </attributes>
    </measure>
  </part>
</score-partwise>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(measure_no_notes_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "Measure 1 in part 0 has no <note> or <rest> elements" in error
    finally:
        os.unlink(temp_path)


def test_first_measure_missing_divisions_returns_false():
    """XML with first measure missing divisions should return (False, error message)."""
    missing_divisions_xml = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <note><rest/></note>
    </measure>
  </part>
</score-partwise>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(missing_divisions_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "First measure has no <attributes> element" in error or "First measure has no <divisions> element in <attributes>" in error
    finally:
        os.unlink(temp_path)


def test_first_measure_empty_divisions_returns_false():
    """XML with first measure having empty divisions should return (False, error message)."""
    empty_divisions_xml = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions></divisions>
      </attributes>
      <note><rest/></note>
    </measure>
  </part>
</score-partwise>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(empty_divisions_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "First measure has empty <divisions> element" in error
    finally:
        os.unlink(temp_path)


def test_first_measure_invalid_divisions_returns_false():
    """XML with first measure having invalid divisions should return (False, error message)."""
    invalid_divisions_xml = """<?xml version="1.0"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Test</part-name></score-part>
  </part-list>
  <part id="P1">
    <measure number="1">
      <attributes>
        <divisions>invalid</divisions>
      </attributes>
      <note><rest/></note>
    </measure>
  </part>
</score-partwise>"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
        f.write(invalid_divisions_xml)
        temp_path = f.name
    
    try:
        is_valid, error = validate_musicxml_structure(temp_path)
        assert is_valid is False
        assert "First measure has invalid divisions value: 'invalid'" in error
    finally:
        os.unlink(temp_path)


def test_valid_empty_score_passes():
    """The empty_score fixture should pass validation."""
    valid_xml = FIXTURE_DIR / "empty_score.musicxml"
    is_valid, error = validate_musicxml_structure(str(valid_xml))
    assert is_valid is True
    assert error == ""


if __name__ == "__main__":
    pytest.main([__file__])
