"""Build MusicXML documents from Score models."""
from lxml import etree

from models.score import Score, Part
from models.measure import Measure
from models.note import Note


def build_musicxml(score: Score) -> str:
    """Convert a Score model to a MusicXML string."""
    root = etree.Element("score-partwise", version="4.0")

    # Work (title)
    if score.title:
        work = etree.SubElement(root, "work")
        etree.SubElement(work, "work-title").text = score.title

    # Identification (composer)
    if score.composer:
        identification = etree.SubElement(root, "identification")
        creator = etree.SubElement(identification, "creator", type="composer")
        creator.text = score.composer
        encoding = etree.SubElement(identification, "encoding")
        etree.SubElement(encoding, "software").text = "ScoreForge"

    # Part list
    part_list = etree.SubElement(root, "part-list")
    for part in score.parts:
        score_part = etree.SubElement(part_list, "score-part", id=part.id)
        etree.SubElement(score_part, "part-name").text = part.name
        if part.abbreviation:
            etree.SubElement(score_part, "part-abbreviation").text = part.abbreviation

    # Parts with measures
    for part in score.parts:
        part_elem = etree.SubElement(root, "part", id=part.id)
        for measure in part.measures:
            _build_measure(part_elem, measure, part)

    # Serialize
    tree = etree.ElementTree(root)
    xml_bytes = etree.tostring(
        tree,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
        doctype='<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
    )
    return xml_bytes.decode("utf-8")


def _build_measure(parent: etree._Element, measure: Measure, part: Part):
    """Build a single measure element."""
    m_elem = etree.SubElement(parent, "measure", number=str(measure.number))

    # Attributes (key, time, clef, divisions)
    needs_attributes = any([
        measure.key_signature,
        measure.time_signature,
        measure.clef,
        measure.divisions > 1 or measure.number == 1,
    ])

    if needs_attributes:
        attr = etree.SubElement(m_elem, "attributes")

        if measure.divisions or measure.number == 1:
            etree.SubElement(attr, "divisions").text = str(measure.divisions)

        if measure.key_signature:
            key_elem = etree.SubElement(attr, "key")
            etree.SubElement(key_elem, "fifths").text = str(measure.key_signature.fifths)
            etree.SubElement(key_elem, "mode").text = measure.key_signature.mode

        if measure.time_signature:
            time_elem = etree.SubElement(attr, "time")
            etree.SubElement(time_elem, "beats").text = str(measure.time_signature.beats)
            etree.SubElement(time_elem, "beat-type").text = str(measure.time_signature.beat_type)

        if part.staves > 1 and measure.number == 1:
            etree.SubElement(attr, "staves").text = str(part.staves)

        if measure.clef:
            clef_elem = etree.SubElement(attr, "clef")
            etree.SubElement(clef_elem, "sign").text = measure.clef.sign
            etree.SubElement(clef_elem, "line").text = str(measure.clef.line)

    # Direction (tempo)
    if measure.tempo:
        direction = etree.SubElement(m_elem, "direction", placement="above")
        direction_type = etree.SubElement(direction, "direction-type")
        metronome = etree.SubElement(direction_type, "metronome")
        etree.SubElement(metronome, "beat-unit").text = "quarter"
        etree.SubElement(metronome, "per-minute").text = str(measure.tempo)
        sound = etree.SubElement(direction, "sound", tempo=str(measure.tempo))

    # Left barline
    if measure.barline_left:
        bl = etree.SubElement(m_elem, "barline", location="left")
        etree.SubElement(bl, "bar-style").text = measure.barline_left.style
        if measure.barline_left.repeat_direction:
            etree.SubElement(bl, "repeat", direction=measure.barline_left.repeat_direction)

    # Notes
    for note in measure.notes:
        _build_note(m_elem, note)

    # Right barline
    if measure.barline_right:
        bl = etree.SubElement(m_elem, "barline", location="right")
        etree.SubElement(bl, "bar-style").text = measure.barline_right.style
        if measure.barline_right.repeat_direction:
            etree.SubElement(bl, "repeat", direction=measure.barline_right.repeat_direction)


def _build_note(parent: etree._Element, note: Note):
    """Build a note element."""
    n_elem = etree.SubElement(parent, "note")

    # Chord
    if note.is_chord:
        etree.SubElement(n_elem, "chord")

    # Grace
    if note.grace:
        etree.SubElement(n_elem, "grace")

    # Rest or pitch
    if note.is_rest:
        etree.SubElement(n_elem, "rest")
    elif note.pitch:
        pitch_elem = etree.SubElement(n_elem, "pitch")
        etree.SubElement(pitch_elem, "step").text = note.pitch.step
        if note.pitch.alter and note.pitch.alter != 0:
            etree.SubElement(pitch_elem, "alter").text = str(note.pitch.alter)
        etree.SubElement(pitch_elem, "octave").text = str(note.pitch.octave)

    # Duration
    etree.SubElement(n_elem, "duration").text = str(note.duration)

    # Voice
    etree.SubElement(n_elem, "voice").text = str(note.voice)

    # Type
    etree.SubElement(n_elem, "type").text = note.note_type.value

    # Dots
    for _ in range(note.dot_count):
        etree.SubElement(n_elem, "dot")

    # Accidental
    if note.pitch and note.pitch.accidental:
        etree.SubElement(n_elem, "accidental").text = note.pitch.accidental.value

    # Staff
    if note.staff > 1:
        etree.SubElement(n_elem, "staff").text = str(note.staff)

    # Beam
    if note.beam:
        beam_elem = etree.SubElement(n_elem, "beam", number="1")
        beam_elem.text = note.beam

    # Notations
    has_notations = any([
        note.tie_start, note.tie_stop,
        note.slur_start, note.slur_stop,
        note.fermata, note.articulation,
    ])
    if has_notations:
        notations = etree.SubElement(n_elem, "notations")

        if note.tie_start:
            etree.SubElement(n_elem, "tie", type="start")
            etree.SubElement(notations, "tied", type="start")
        if note.tie_stop:
            etree.SubElement(n_elem, "tie", type="stop")
            etree.SubElement(notations, "tied", type="stop")
        if note.slur_start:
            etree.SubElement(notations, "slur", type="start")
        if note.slur_stop:
            etree.SubElement(notations, "slur", type="stop")
        if note.fermata:
            etree.SubElement(notations, "fermata")
        if note.articulation:
            artic = etree.SubElement(notations, "articulations")
            etree.SubElement(artic, note.articulation)

    # Dynamics (as direction before the note, but we attach it here for simplicity)
    if note.dynamic:
        direction = etree.SubElement(parent, "direction", placement="below")
        direction_type = etree.SubElement(direction, "direction-type")
        dynamics = etree.SubElement(direction_type, "dynamics")
        etree.SubElement(dynamics, note.dynamic)

    # Lyrics — Claude may return strings or dicts like {"text": "...", "syllabic": "..."}
    for i, lyric_item in enumerate(note.lyrics):
        if isinstance(lyric_item, dict):
            lyric_text = lyric_item.get("text") or lyric_item.get("syllable") or str(lyric_item)
            syllabic = lyric_item.get("syllabic", "single")
        else:
            lyric_text = str(lyric_item) if lyric_item is not None else ""
            syllabic = "single"
        lyric = etree.SubElement(n_elem, "lyric", number=str(i + 1))
        etree.SubElement(lyric, "syllabic").text = syllabic
        etree.SubElement(lyric, "text").text = lyric_text
