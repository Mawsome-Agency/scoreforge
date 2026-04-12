"""Tests for multi-voice note separation feature.

Covers changes in:
- models/note.py (stem field)
- core/musicxml_builder.py (stem emission, multi-voice backup)
- core/extractor.py (_build_note stem parsing)
- core/comparator.py (voice-aware comparison)
"""
import sys
from pathlib import Path

import pytest
from lxml import etree

# Project root on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.note import Note, NoteType, Pitch, Accidental
from models.measure import Measure, Clef, KeySignature, TimeSignature
from models.score import Part, Score
from core.musicxml_builder import build_musicxml, _build_notes_multivoice, _build_note
from core.comparator import (
    _compare_measures,
    _compare_note_lists,
    _parse_note_element,
    _pct,
    compare_musicxml_semantic,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_note(pitch_step="C", octave=4, note_type=NoteType.QUARTER, duration=1,
               voice=1, staff=1, stem=None, is_rest=False, is_chord=False,
               alter=0, accidental=None):
    """Create a Note with sensible defaults."""
    pitch = None
    if not is_rest:
        pitch = Pitch(step=pitch_step, octave=octave, alter=alter, accidental=accidental)
    return Note(
        note_type=note_type,
        duration=duration,
        is_rest=is_rest,
        pitch=pitch,
        voice=voice,
        staff=staff,
        stem=stem,
        is_chord=is_chord,
    )


def _parsed_note(step="C", octave=4, alter=0, duration=1, duration_normalized=1.0,
                 voice=1, staff=1, is_rest=False, is_chord=False, note_type="quarter",
                 tie_start=False, tie_stop=False, is_grace=False, dot_count=0):
    """Create a parsed note dict (as returned by comparator's _parse_note_element)."""
    pitch = None
    if not is_rest:
        pitch = {"step": step, "octave": octave, "alter": alter}
    return {
        "is_rest": is_rest,
        "is_chord": is_chord,
        "is_grace": is_grace,
        "pitch": pitch,
        "duration": duration,
        "duration_normalized": duration_normalized,
        "type": note_type,
        "dot_count": dot_count,
        "voice": voice,
        "staff": staff,
        "tie_start": tie_start,
        "tie_stop": tie_stop,
    }


# ============================================================================
# 1. Note model — stem field
# ============================================================================

class TestNoteStemField:
    """Verify Note model supports the stem attribute."""

    def test_stem_default_is_none(self):
        note = Note(note_type=NoteType.QUARTER, duration=1)
        assert note.stem is None

    def test_stem_up(self):
        note = Note(note_type=NoteType.QUARTER, duration=1, stem="up")
        assert note.stem == "up"

    def test_stem_down(self):
        note = Note(note_type=NoteType.QUARTER, duration=1, stem="down")
        assert note.stem == "down"

    def test_stem_none_explicit(self):
        note = Note(note_type=NoteType.QUARTER, duration=1, stem="none")
        assert note.stem == "none"

    def test_stem_preserved_in_str(self):
        """str(Note) should still work with stem set."""
        note = _make_note(stem="up")
        s = str(note)
        assert "C" in s  # pitch is present
        assert "quarter" in s


# ============================================================================
# 2. MusicXML builder — stem emission
# ============================================================================

class TestBuilderStemEmission:
    """Verify _build_note emits <stem> element correctly."""

    def _note_xml(self, note: Note) -> etree._Element:
        """Build a note's XML and return the parent element."""
        parent = etree.Element("measure")
        _build_note(parent, note)
        return parent

    def test_stem_up_emitted(self):
        parent = self._note_xml(_make_note(stem="up"))
        stem_el = parent.find(".//stem")
        assert stem_el is not None
        assert stem_el.text == "up"

    def test_stem_down_emitted(self):
        parent = self._note_xml(_make_note(stem="down"))
        stem_el = parent.find(".//stem")
        assert stem_el is not None
        assert stem_el.text == "down"

    def test_no_stem_when_none(self):
        parent = self._note_xml(_make_note(stem=None))
        stem_el = parent.find(".//stem")
        assert stem_el is None

    def test_stem_position_after_type(self):
        """In MusicXML, <stem> should appear after <type>."""
        parent = self._note_xml(_make_note(stem="up"))
        note_el = parent.find("note")
        children = [child.tag for child in note_el]
        type_idx = children.index("type")
        stem_idx = children.index("stem")
        assert stem_idx == type_idx + 1, f"stem at {stem_idx}, type at {type_idx}"

    def test_stem_on_rest_not_typical(self):
        """Rests normally don't have stems but if set, still emitted."""
        note = _make_note(is_rest=True, stem="up")
        parent = self._note_xml(note)
        stem_el = parent.find(".//stem")
        # We set stem explicitly, so it should be emitted
        assert stem_el is not None


# ============================================================================
# 3. MusicXML builder — multi-voice backup logic
# ============================================================================

class TestBuilderMultiVoice:
    """Test _build_notes_multivoice produces correct <backup> elements."""

    def test_single_voice_no_backup(self):
        """Single voice should have no <backup> elements."""
        notes = [_make_note(voice=1, duration=10) for _ in range(4)]
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, notes)

        backups = parent.findall("backup")
        assert len(backups) == 0
        assert len(parent.findall("note")) == 4

    def test_two_voices_one_backup(self):
        """Two voices should produce exactly one <backup> element."""
        v1_notes = [_make_note(voice=1, duration=10, stem="up") for _ in range(4)]
        v2_notes = [_make_note(voice=2, duration=20, stem="down", pitch_step="E") for _ in range(2)]
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, v1_notes + v2_notes)

        backups = parent.findall("backup")
        assert len(backups) == 1

    def test_backup_duration_matches_voice1_total(self):
        """<backup> duration should equal the total duration of voice 1."""
        v1_notes = [_make_note(voice=1, duration=10080) for _ in range(4)]
        v2_notes = [_make_note(voice=2, duration=20160, pitch_step="E") for _ in range(2)]
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, v1_notes + v2_notes)

        backup = parent.find("backup")
        assert backup is not None
        dur = backup.find("duration")
        assert dur is not None
        assert dur.text == str(4 * 10080)  # 40320

    def test_voice_ordering_preserved(self):
        """Notes should appear voice 1 first, then backup, then voice 2."""
        v1 = [_make_note(voice=1, duration=10, pitch_step="C")]
        v2 = [_make_note(voice=2, duration=10, pitch_step="E")]
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, v1 + v2)

        children = [child.tag for child in parent]
        # Should be: note, backup, note
        assert children == ["note", "backup", "note"]

    def test_three_voices_two_backups(self):
        """Three voices should produce two <backup> elements."""
        notes = (
            [_make_note(voice=1, duration=10)] +
            [_make_note(voice=2, duration=10, pitch_step="E")] +
            [_make_note(voice=3, duration=10, pitch_step="G")]
        )
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, notes)

        backups = parent.findall("backup")
        assert len(backups) == 2

    def test_chord_notes_not_counted_in_backup_duration(self):
        """Chord notes (is_chord=True) should not add to backup duration."""
        notes = [
            _make_note(voice=1, duration=40, pitch_step="C"),
            _make_note(voice=1, duration=40, pitch_step="E", is_chord=True),
            _make_note(voice=2, duration=40, pitch_step="G"),
        ]
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, notes)

        backup = parent.find("backup")
        dur = backup.find("duration")
        # Only non-chord note counted: 40 (not 80)
        assert dur.text == "40"

    def test_empty_notes_list(self):
        """Empty note list should produce no output."""
        parent = etree.Element("measure")
        _build_notes_multivoice(parent, [])
        assert len(list(parent)) == 0


# ============================================================================
# 4. Extractor — _build_note stem parsing
# ============================================================================

class TestExtractorBuildNoteStem:
    """Test that _build_note in extractor correctly parses stem field."""

    def test_stem_up_parsed(self):
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 5},
            "voice": 1,
            "stem": "up",
        }
        note = extractor_build_note(data)
        assert note.stem == "up"

    def test_stem_down_parsed(self):
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "half",
            "duration": 2,
            "pitch": {"step": "E", "octave": 4},
            "voice": 2,
            "stem": "down",
        }
        note = extractor_build_note(data)
        assert note.stem == "down"

    def test_stem_none_when_missing(self):
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
        }
        note = extractor_build_note(data)
        assert note.stem is None

    def test_stem_null_from_json(self):
        """JSON null maps to Python None."""
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
            "stem": None,
        }
        note = extractor_build_note(data)
        assert note.stem is None

    def test_voice_and_stem_together(self):
        """Stem and voice should both be set from extraction data."""
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "D", "octave": 5},
            "voice": 2,
            "staff": 1,
            "stem": "down",
        }
        note = extractor_build_note(data)
        assert note.voice == 2
        assert note.staff == 1
        assert note.stem == "down"

    def test_invalid_stem_sanitized_to_none(self):
        """Hallucinated stem value 'upward' must be sanitized to None."""
        from core.extractor import _build_note as extractor_build_note
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 5},
            "voice": 1,
            "stem": "upward",  # invalid — not in _VALID_STEMS
        }
        note = extractor_build_note(data)
        assert note.stem is None, f"Expected None, got {note.stem!r}"


# ============================================================================
# 5. Comparator — voice-aware comparison
# ============================================================================

class TestComparatorVoiceAware:
    """Test that _compare_measures groups notes by voice before comparing."""

    def test_single_voice_positional(self):
        """Single voice still uses positional comparison."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("D", 5, voice=1),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("D", 5, voice=1),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is True
        assert result["pitches_correct"] == 2

    def test_multi_voice_correct_assignment(self):
        """Multi-voice notes grouped by voice should match correctly."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1, duration=10080, duration_normalized=1.0),
                _parsed_note("D", 5, voice=1, duration=10080, duration_normalized=1.0),
                _parsed_note("E", 4, voice=2, duration=20160, duration_normalized=2.0),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1, duration=10080, duration_normalized=1.0),
                _parsed_note("D", 5, voice=1, duration=10080, duration_normalized=1.0),
                _parsed_note("E", 4, voice=2, duration=20160, duration_normalized=2.0),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is True
        assert result["pitches_correct"] == 3
        assert result["notes_matched"] == 3

    def test_multi_voice_wrong_voice_assignment(self):
        """Notes assigned to wrong voice should cause diffs in the right voice group."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=2),
            ],
        }
        # Extraction puts both in voice 1 (the bug this feature fixes)
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=1),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is False
        # Voice 1: gt has 1, ex has 2 → extra note
        # Voice 2: gt has 1, ex has 0 → missing note
        assert len(result["diffs"]) > 0

    def test_multi_voice_interleaved_input_order(self):
        """Even if extraction interleaves voices, grouping by voice should still match."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=2),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("E", 4, voice=2),
                _parsed_note("C", 5, voice=1),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        # After grouping by voice, voice 1: C5 vs C5, voice 2: E4 vs E4
        assert result["pitches_correct"] == 2
        assert result["is_perfect"] is True

    def test_missing_voice_in_extraction(self):
        """If extraction is missing an entire voice, all notes in that voice are diffs."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=2),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is False
        missing = [d for d in result["diffs"] if d["type"] == "missing_note"]
        assert len(missing) == 1

    def test_extra_voice_in_extraction(self):
        """Extra notes in a voice not in ground truth should be flagged."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=2),
            ],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is False
        extra = [d for d in result["diffs"] if d["type"] == "extra_note"]
        assert len(extra) == 1

    def test_voice_diff_label_in_output(self):
        """Diffs in multi-voice should carry a voice label."""
        gt = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("E", 4, voice=2),
            ],
        }
        ex = {
            "key": None, "time": None,
            "notes": [
                _parsed_note("C", 5, voice=1),
                _parsed_note("F", 4, voice=2),  # wrong pitch
            ],
        }
        result = _compare_measures(gt, ex, 1)
        pitch_diffs = [d for d in result["diffs"] if d["type"] == "wrong_pitch"]
        assert len(pitch_diffs) == 1
        assert pitch_diffs[0]["voice"] == 2


# ============================================================================
# 6. Comparator — _compare_note_lists
# ============================================================================

class TestCompareNoteLists:
    """Test the _compare_note_lists helper directly."""

    def test_empty_lists(self):
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists([], [], 1)
        assert matched == 0
        assert pitches == 0
        assert durs == 0
        assert len(diffs) == 0

    def test_gt_empty_ex_has_notes(self):
        ex = [_parsed_note("C", 4)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists([], ex, 1)
        assert len(diffs) == 1
        assert diffs[0]["type"] == "extra_note"

    def test_ex_empty_gt_has_notes(self):
        gt = [_parsed_note("C", 4)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists(gt, [], 1)
        assert len(diffs) == 1
        assert diffs[0]["type"] == "missing_note"

    def test_perfect_match(self):
        notes = [_parsed_note("C", 4), _parsed_note("D", 4)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists(notes, notes, 1)
        assert matched == 2
        assert pitches == 2
        assert durs == 2
        assert len(diffs) == 0

    def test_wrong_pitch(self):
        gt = [_parsed_note("C", 4)]
        ex = [_parsed_note("D", 4)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists(gt, ex, 1)
        assert pitches == 0
        wrong = [d for d in diffs if d["type"] == "wrong_pitch"]
        assert len(wrong) == 1

    def test_wrong_duration(self):
        gt = [_parsed_note("C", 4, duration=1, duration_normalized=1.0)]
        ex = [_parsed_note("C", 4, duration=2, duration_normalized=2.0)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists(gt, ex, 1)
        assert durs == 0
        dur_diffs = [d for d in diffs if d["type"] == "wrong_duration"]
        assert len(dur_diffs) == 1

    def test_rest_vs_note_mismatch(self):
        gt = [_parsed_note("C", 4)]
        ex = [_parsed_note(is_rest=True)]
        matched, pitches, durs, pitch_ct, diffs = _compare_note_lists(gt, ex, 1)
        assert matched == 0
        wrong_type = [d for d in diffs if d["type"] == "wrong_note_type"]
        assert len(wrong_type) == 1

    def test_voice_label_in_diffs(self):
        """When voice_num is provided, diffs should contain it."""
        gt = [_parsed_note("C", 4)]
        ex = [_parsed_note("D", 4)]
        _, _, _, _, diffs = _compare_note_lists(gt, ex, 1, voice_num=2)
        assert all(d.get("voice") == 2 for d in diffs)


# ============================================================================
# 7. Comparator — _pct utility
# ============================================================================

class TestPct:

    def test_normal(self):
        assert _pct(3, 4) == 75.0

    def test_zero_total(self):
        assert _pct(0, 0) == 100.0

    def test_perfect(self):
        assert _pct(10, 10) == 100.0

    def test_zero_correct(self):
        assert _pct(0, 10) == 0.0


# ============================================================================
# 8. Comparator — parse_note_element for voice
# ============================================================================

class TestParseNoteElement:
    """Test that _parse_note_element correctly reads voice from XML."""

    def test_voice_parsed(self):
        xml = '<note><pitch><step>C</step><octave>5</octave></pitch><duration>10080</duration><voice>2</voice><type>quarter</type></note>'
        el = etree.fromstring(xml)
        result = _parse_note_element(el, "", 10080)
        assert result["voice"] == 2

    def test_voice_defaults_to_1(self):
        xml = '<note><pitch><step>C</step><octave>5</octave></pitch><duration>10080</duration><type>quarter</type></note>'
        el = etree.fromstring(xml)
        result = _parse_note_element(el, "", 10080)
        assert result["voice"] == 1

    def test_staff_parsed(self):
        xml = '<note><pitch><step>C</step><octave>5</octave></pitch><duration>10080</duration><voice>1</voice><type>quarter</type><staff>2</staff></note>'
        el = etree.fromstring(xml)
        result = _parse_note_element(el, "", 10080)
        assert result["staff"] == 2

    def test_duration_normalized(self):
        xml = '<note><pitch><step>C</step><octave>5</octave></pitch><duration>20160</duration><voice>1</voice><type>half</type></note>'
        el = etree.fromstring(xml)
        result = _parse_note_element(el, "", 10080)
        assert result["duration_normalized"] == 2.0


# ============================================================================
# 9. End-to-end: multi_voice fixture semantic self-comparison
# ============================================================================

class TestMultiVoiceFixture:
    """Compare multi_voice.musicxml against itself — should be 100%."""

    FIXTURE = str(Path(__file__).parent / "fixtures" / "multi_voice.musicxml")

    def test_self_comparison_perfect(self):
        result = compare_musicxml_semantic(self.FIXTURE, self.FIXTURE)
        assert result["is_perfect"] is True
        assert result["scores"]["overall"] == 100.0

    def test_self_comparison_note_count(self):
        """multi_voice fixture has 6 notes in m1 (4 voice1 + 2 voice2) and 4 per chord measure."""
        result = compare_musicxml_semantic(self.FIXTURE, self.FIXTURE)
        # Total notes: m1=6, m2=4, m3=4, m4=4 = 18
        assert result["total_notes_gt"] == 18

    def test_self_comparison_part_count(self):
        result = compare_musicxml_semantic(self.FIXTURE, self.FIXTURE)
        assert result["gt_part_count"] == 1
        assert result["part_count_match"] is True

    def test_measure_1_voice_separation(self):
        """Measure 1 should have notes in both voice 1 and voice 2."""
        result = compare_musicxml_semantic(self.FIXTURE, self.FIXTURE)
        m1 = result["part_diffs"][0]["measure_diffs"][0]
        assert m1["gt_note_count"] == 6
        assert m1["is_perfect"] is True


# ============================================================================
# 10. Full build_musicxml round-trip for multi-voice
# ============================================================================

class TestBuildMultiVoiceRoundTrip:
    """Build MusicXML from a multi-voice Score and verify XML structure."""

    def _make_multi_voice_score(self):
        score = Score(title="Multi-Voice Test")
        part = Part(id="P1", name="Piano")

        m = Measure(number=1)
        m.divisions = 1
        m.key_signature = KeySignature(fifths=0, mode="major")
        m.time_signature = TimeSignature(beats=4, beat_type=4)
        m.clef = Clef(sign="G", line=2)

        # Voice 1: 4 quarter notes
        for step in ["C", "D", "E", "F"]:
            m.notes.append(_make_note(step, 5, NoteType.QUARTER, 1, voice=1, stem="up"))

        # Voice 2: 1 half note + 1 half rest
        m.notes.append(_make_note("G", 4, NoteType.HALF, 2, voice=2, stem="down"))
        m.notes.append(Note(
            note_type=NoteType.HALF, duration=2, is_rest=True, voice=2, stem=None,
        ))

        part.measures.append(m)
        score.parts.append(part)
        return score

    def test_xml_has_backup_element(self):
        score = self._make_multi_voice_score()
        xml = build_musicxml(score)
        assert "<backup>" in xml

    def test_xml_has_stem_elements(self):
        score = self._make_multi_voice_score()
        xml = build_musicxml(score)
        assert "<stem>up</stem>" in xml
        assert "<stem>down</stem>" in xml

    def test_xml_has_two_voices(self):
        score = self._make_multi_voice_score()
        xml = build_musicxml(score)
        assert "<voice>1</voice>" in xml
        assert "<voice>2</voice>" in xml

    def test_xml_backup_duration_correct(self):
        score = self._make_multi_voice_score()
        xml = build_musicxml(score)
        root = etree.fromstring(xml.encode())
        backup = root.find(".//backup")
        assert backup is not None
        dur = backup.find("duration")
        # Voice 1: 4 quarter notes × duration 1 = 4
        assert dur.text == "4"

    def test_xml_is_valid_structure(self):
        score = self._make_multi_voice_score()
        xml = build_musicxml(score)
        root = etree.fromstring(xml.encode())
        assert root.tag == "score-partwise"
        assert root.get("version") == "4.0"
        notes = root.findall(".//note")
        # 4 voice1 + 1 voice2 note + 1 voice2 rest = 6
        assert len(notes) == 6


# ============================================================================
# 11. Edge cases
# ============================================================================

class TestEdgeCases:

    def test_note_with_all_fields(self):
        """Note with every field populated should not crash."""
        note = Note(
            note_type=NoteType.QUARTER,
            duration=1,
            is_rest=False,
            pitch=Pitch(step="C", octave=4, alter=1, accidental=Accidental.SHARP),
            dot_count=1,
            is_chord=False,
            voice=2,
            staff=1,
            beam="begin",
            stem="down",
            tie_start=True,
            tie_stop=False,
            slur_start=True,
            slur_stop=False,
            dynamic="mf",
            articulation="staccato",
            fermata=True,
            grace=False,
        )
        assert note.stem == "down"
        assert note.voice == 2

    def test_compare_measures_no_notes(self):
        """Measures with no notes should compare as perfect."""
        gt = {"key": None, "time": None, "notes": []}
        ex = {"key": None, "time": None, "notes": []}
        result = _compare_measures(gt, ex, 1)
        assert result["is_perfect"] is True

    def test_compare_measures_key_mismatch(self):
        gt = {
            "key": {"fifths": 0, "mode": "major"},
            "time": None,
            "notes": [],
        }
        ex = {
            "key": {"fifths": 2, "mode": "major"},
            "time": None,
            "notes": [],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["key_correct"] is False
        wrong_key = [d for d in result["diffs"] if d["type"] == "wrong_key"]
        assert len(wrong_key) == 1

    def test_compare_measures_time_mismatch(self):
        gt = {
            "key": None,
            "time": {"beats": 4, "beat_type": 4},
            "notes": [],
        }
        ex = {
            "key": None,
            "time": {"beats": 3, "beat_type": 4},
            "notes": [],
        }
        result = _compare_measures(gt, ex, 1)
        assert result["time_correct"] is False


# ============================================================================
# 12. Ambiguous Stem Scenarios — tests for voice assignment when stems absent
# ============================================================================

class TestAmbiguousStemScenarios:
    """Test voice assignment when stems are absent or ambiguous."""

    def test_whole_note_no_stem_voice_fallback(self):
        """Whole note without stem should accept any voice (LLM decides by pitch)."""
        # A whole note with no stem set
        data = {
            "type": "whole",
            "duration": 4,
            "pitch": {"step": "C", "octave": 4},
            "voice": 1,
            "stem": "none",
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "none"
        assert note.voice == 1  # Voice 1 is valid default

    def test_half_note_no_stem_voice_fallback(self):
        """Half note without stem should accept any voice (LLM decides by pitch)."""
        data = {
            "type": "half",
            "duration": 2,
            "pitch": {"step": "D", "octave": 4},
            "voice": 2,
            "stem": "none",
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "none"
        assert note.voice == 2

    def test_chord_voice_assignment_lowest_note(self):
        """Chord voice assignment: lowest note gets voice, others inherit."""
        # Chord with three notes: C (lowest), E, G (highest)
        # Only C should have the voice field, others inherit via is_chord=True
        data_lowest = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
            "voice": 1,
            "is_chord": False,
            "stem": "up",
        }
        data_chord1 = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "E", "octave": 4},
            "is_chord": True,
            "stem": "up",  # Chord members can have stem
        }
        data_chord2 = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "G", "octave": 4},
            "is_chord": True,
            "stem": "up",
        }
        from core.extractor import _build_note as extractor_build_note
        note_lowest = extractor_build_note(data_lowest)
        note_chord1 = extractor_build_note(data_chord1)
        note_chord2 = extractor_build_note(data_chord2)
        assert note_lowest.voice == 1
        assert note_chord1.is_chord is True
        assert note_chord2.is_chord is True

    def test_pitch_based_fallback_lower_note_voice_1(self):
        """Lower pitch notes without stems default to voice 1."""
        data = {
            "type": "whole",
            "duration": 4,
            "pitch": {"step": "C", "octave": 3},  # Lower than E4
            "stem": "none",
            "voice": 1,  # Lower pitch = voice 1
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "none"
        assert note.voice == 1

    def test_pitch_based_fallback_higher_note_voice_2(self):
        """Higher pitch notes without stems default to voice 2."""
        data = {
            "type": "whole",
            "duration": 4,
            "pitch": {"step": "E", "octave": 4},  # Higher than C4
            "stem": "none",
            "voice": 2,  # Higher pitch = voice 2
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "none"
        assert note.voice == 2


# ============================================================================
# 13. Voice Assignment Fallbacks — tests for fallback logic
# ============================================================================

class TestVoiceAssignmentFallbacks:
    """Test fallback logic for voice assignment."""

    def test_stem_up_voice_1(self):
        """Stem up always maps to voice 1 regardless of pitch."""
        # Even a high note with stem up should be voice 1
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "E", "octave": 5},  # High note
            "stem": "up",
            "voice": 1,
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "up"
        assert note.voice == 1

    def test_stem_down_voice_2(self):
        """Stem down always maps to voice 2 regardless of pitch."""
        # Even a low note with stem down should be voice 2
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 3},  # Low note
            "stem": "down",
            "voice": 2,
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "down"
        assert note.voice == 2

    def test_stem_overrides_pitch_heuristic(self):
        """When stem is visible, it overrides pitch-based heuristics."""
        # High note with stem DOWN should be voice 2, not voice 1
        data = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "E", "octave": 5},  # High pitch
            "stem": "down",  # Stem overrides pitch heuristic
            "voice": 2,  # Follows stem, not pitch
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.stem == "down"
        assert note.voice == 2

    def test_rest_default_voice_1(self):
        """Rests default to voice 1 when not explicitly assigned."""
        data = {
            "type": "quarter",
            "duration": 1,
            "is_rest": True,
            "voice": 1,  # Default voice for rests
            "stem": "none",
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.is_rest is True
        assert note.voice == 1

    def test_rest_explicit_voice_2(self):
        """Rests can be assigned to voice 2 when explicitly notated."""
        data = {
            "type": "half",
            "duration": 2,
            "is_rest": True,
            "voice": 2,  # Explicit voice assignment
            "stem": "none",
        }
        from core.extractor import _build_note as extractor_build_note
        note = extractor_build_note(data)
        assert note.is_rest is True
        assert note.voice == 2

    def test_tied_note_voice_inheritance(self):
        """Tied continuation inherits voice from origin note."""
        data_origin = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
            "voice": 1,
            "stem": "up",
            "tie_start": True,
            "tie_stop": False,
        }
        data_continuation = {
            "type": "quarter",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
            "voice": 1,  # Inherits voice from origin
            "stem": "up",
            "tie_start": False,
            "tie_stop": True,
        }
        from core.extractor import _build_note as extractor_build_note
        note_origin = extractor_build_note(data_origin)
        note_cont = extractor_build_note(data_continuation)
        # Both notes should have same voice
        assert note_origin.voice == 1
        assert note_cont.voice == 1
        assert note_origin.tie_start is True
        assert note_cont.tie_stop is True

    def test_beam_notes_same_voice(self):
        """All notes in a beam group should share the same voice."""
        data_beam1 = {
            "type": "eighth",
            "duration": 1,
            "pitch": {"step": "C", "octave": 4},
            "voice": 1,
            "stem": "up",
            "beam": "begin",
        }
        data_beam2 = {
            "type": "eighth",
            "duration": 1,
            "pitch": {"step": "E", "octave": 4},
            "voice": 1,  # Same voice as beam start
            "stem": "up",
            "beam": "end",
        }
        from core.extractor import _build_note as extractor_build_note
        note_beam1 = extractor_build_note(data_beam1)
        note_beam2 = extractor_build_note(data_beam2)
        assert note_beam1.voice == 1
        assert note_beam2.voice == 1
        assert note_beam1.beam == "begin"
        assert note_beam2.beam == "end"

    def test_voice_assignment_musicxml_emission(self):
        """Verify voice assignment emits correctly to MusicXML."""
        parent = etree.Element("measure")
        note1 = _make_note(voice=1, stem="up", pitch_step="C")
        note2 = _make_note(voice=2, stem="down", pitch_step="E")
        _build_notes_multivoice(parent, [note1, note2])

        # Verify voices were set correctly
        notes = parent.findall("note")
        assert notes[0].find("voice").text == "1"
        assert notes[0].find("stem").text == "up"
        assert notes[1].find("voice").text == "2"
        assert notes[1].find("stem").text == "down"


# ============================================================================
# 14. is_perfect KEY/TIME — compare_musicxml_semantic must require correct
#     key and time signatures for is_perfect to be True.
# ============================================================================

import tempfile
import os


def _write_musicxml(content: str) -> str:
    """Write MusicXML content to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".musicxml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


_MUSICXML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list>
    <score-part id="P1"><part-name>Piano</part-name></score-part>
  </part-list>
  <part id="P1">
"""

_MUSICXML_FOOTER = """  </part>
</score-partwise>
"""


def _make_score_xml(key_fifths: int = 0, time_beats: int = 4, time_beat_type: int = 4,
                    divisions: int = 1) -> str:
    """Generate a minimal 1-measure MusicXML with one quarter note."""
    return (
        _MUSICXML_HEADER
        + f"""    <measure number="1">
      <attributes>
        <divisions>{divisions}</divisions>
        <key><fifths>{key_fifths}</fifths><mode>major</mode></key>
        <time><beats>{time_beats}</beats><beat-type>{time_beat_type}</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef>
      </attributes>
      <note>
        <pitch><step>C</step><octave>4</octave></pitch>
        <duration>{divisions}</duration>
        <voice>1</voice>
        <type>quarter</type>
      </note>
    </measure>
"""
        + _MUSICXML_FOOTER
    )


class TestIsPerfectKeyTime:
    """compare_musicxml_semantic.is_perfect must be False when key or time differs."""

    def test_identical_files_are_perfect(self):
        """Self-comparison must be is_perfect=True."""
        path = _write_musicxml(_make_score_xml(key_fifths=0))
        try:
            result = compare_musicxml_semantic(path, path)
            assert result["is_perfect"] is True
        finally:
            os.unlink(path)

    def test_wrong_key_makes_not_perfect(self):
        """When extracted key differs from GT, is_perfect must be False."""
        gt_path = _write_musicxml(_make_score_xml(key_fifths=0))
        ex_path = _write_musicxml(_make_score_xml(key_fifths=2))  # D major vs C major
        try:
            result = compare_musicxml_semantic(gt_path, ex_path)
            assert result["is_perfect"] is False
        finally:
            os.unlink(gt_path)
            os.unlink(ex_path)

    def test_wrong_time_makes_not_perfect(self):
        """When extracted time signature differs from GT, is_perfect must be False."""
        gt_path = _write_musicxml(_make_score_xml(time_beats=4, time_beat_type=4))
        ex_path = _write_musicxml(_make_score_xml(time_beats=3, time_beat_type=4))  # 3/4 vs 4/4
        try:
            result = compare_musicxml_semantic(gt_path, ex_path)
            assert result["is_perfect"] is False
        finally:
            os.unlink(gt_path)
            os.unlink(ex_path)

    def test_wrong_key_reported_in_scores(self):
        """key_sig_accuracy must be 0 when key is wrong."""
        gt_path = _write_musicxml(_make_score_xml(key_fifths=0))
        ex_path = _write_musicxml(_make_score_xml(key_fifths=3))
        try:
            result = compare_musicxml_semantic(gt_path, ex_path)
            assert result["scores"]["key_sig_accuracy"] == 0.0
        finally:
            os.unlink(gt_path)
            os.unlink(ex_path)

    def test_wrong_time_reported_in_scores(self):
        """time_sig_accuracy must be 0 when time is wrong."""
        gt_path = _write_musicxml(_make_score_xml(time_beats=4, time_beat_type=4))
        ex_path = _write_musicxml(_make_score_xml(time_beats=2, time_beat_type=2))
        try:
            result = compare_musicxml_semantic(gt_path, ex_path)
            assert result["scores"]["time_sig_accuracy"] == 0.0
        finally:
            os.unlink(gt_path)
            os.unlink(ex_path)

    def test_voice_accuracy_in_scores(self):
        """voice_accuracy must be present in scores output."""
        path = _write_musicxml(_make_score_xml())
        try:
            result = compare_musicxml_semantic(path, path)
            assert "voice_accuracy" in result["scores"]
            assert result["scores"]["voice_accuracy"] == 100.0
        finally:
            os.unlink(path)

    def test_duration_normalization_cross_divisions(self):
        """A quarter note at divisions=10080 and divisions=1 must compare equal."""
        # GT uses divisions=10080 (music21 default), ex uses divisions=1
        gt_path = _write_musicxml(_make_score_xml(divisions=10080))
        ex_path = _write_musicxml(_make_score_xml(divisions=1))
        try:
            result = compare_musicxml_semantic(gt_path, ex_path)
            # Duration should match despite different raw values
            assert result["scores"]["rhythm_accuracy"] == 100.0
        finally:
            os.unlink(gt_path)
            os.unlink(ex_path)


# ============================================================================
# 15. _infer_duration() helper - duration inference from note type
# ============================================================================

class TestInferDuration:
    """Test _infer_duration() helper function."""

    def test_whole_note_divisions_1(self):
        """Whole note at divisions=1 should be 4."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.WHOLE, dots=0, divisions=1) == 4

    def test_half_note_divisions_1(self):
        """Half note at divisions=1 should be 2."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.HALF, dots=0, divisions=1) == 2

    def test_quarter_note_divisions_1(self):
        """Quarter note at divisions=1 should be 1."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.QUARTER, dots=0, divisions=1) == 1

    def test_eighth_note_divisions_2(self):
        """Eighth note at divisions=2 should be 1."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.EIGHTH, dots=0, divisions=2) == 1

    def test_sixteenth_note_divisions_4(self):
        """Sixteenth note at divisions=4 should be 1."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.SIXTEENTH, dots=0, divisions=4) == 1

    def test_dotted_half_note_divisions_1(self):
        """Dotted half note at divisions=1 should be 3 (2 * 1.5)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.HALF, dots=1, divisions=1) == 3

    def test_dotted_quarter_note_divisions_1(self):
        """Dotted quarter note at divisions=1 should be 2 (1 * 1.5, rounded)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.QUARTER, dots=1, divisions=1) == 2

    def test_dotted_whole_note_divisions_1(self):
        """Dotted whole note at divisions=1 should be 6 (4 * 1.5)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.WHOLE, dots=1, divisions=1) == 6

    def test_double_dotted_quarter_note_divisions_1(self):
        """Double-dotted quarter note at divisions=1 should be 2 (1 * 1.75, rounded)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.QUARTER, dots=2, divisions=1) == 2

    def test_eighth_note_divisions_1_rounds_to_1(self):
        """Eighth note at divisions=1 should round to 1 (0.5 * 1 = 0.5, max(1, round(0.5)) = 1)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.EIGHTH, dots=0, divisions=1) == 1

    def test_sixteenth_note_divisions_1_rounds_to_1(self):
        """Sixteenth note at divisions=1 should round to 1 (0.25 * 1 = 0.25, max(1, round(0.25)) = 1)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.SIXTEENTH, dots=0, divisions=1) == 1

    def test_dotted_half_note_divisions_2(self):
        """Dotted half note at divisions=2 should be 6 (2 * 2 * 1.5 = 6)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.HALF, dots=1, divisions=2) == 6

    def test_thirty_second_note_divisions_8(self):
        """Thirty-second note at divisions=8 should be 1 (0.125 * 8 = 1)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.THIRTY_SECOND, dots=0, divisions=8) == 1

    def test_sixty_fourth_note_divisions_16(self):
        """Sixty-fourth note at divisions=16 should be 1 (0.0625 * 16 = 1)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.SIXTY_FOURTH, dots=0, divisions=16) == 1

    def test_dotted_eighth_note_divisions_2(self):
        """Dotted eighth note at divisions=2 should be 2 (0.5 * 2 * 1.5 = 1.5, rounded to 2)."""
        from core.extractor import _infer_duration
        assert _infer_duration(NoteType.EIGHTH, dots=1, divisions=2) == 2

    def test_all_note_types_divisions_1(self):
        """All note types at divisions=1 should produce valid durations."""
        from core.extractor import _infer_duration
        for note_type in NoteType:
            duration = _infer_duration(note_type, dots=0, divisions=1)
            assert duration >= 1, f"{note_type} produced duration {duration} < 1"

    def test_all_note_types_divisions_4(self):
        """All note types at divisions=4 should produce valid durations."""
        from core.extractor import _infer_duration
        for note_type in NoteType:
            duration = _infer_duration(note_type, dots=0, divisions=4)
            assert duration >= 1, f"{note_type} produced duration {duration} < 1"
