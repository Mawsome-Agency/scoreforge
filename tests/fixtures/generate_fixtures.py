#!/usr/bin/env python3
"""ScoreForge Fixture Generator - Creates comprehensive MusicXML test fixtures."""

import sys
from pathlib import Path
import click
from music21 import stream, note, pitch, duration, meter, key, clef, chord, articulations, dynamics, expressions, tempo, spanner, repeat, bar, metadata
from music21.musicxml import m21ToXml

FIXTURE_DIR = Path(__file__).parent

def create_score(title: str, composer: str = "ScoreForge Test") -> stream.Score:
    s = stream.Score()
    md = metadata.Metadata()
    md.title = title
    md.composer = composer
    s.metadata = md
    return s

def save_score(score: stream.Score, name: str) -> Path:
    output_path = FIXTURE_DIR / f"{name}.musicxml"
    xml_bytes = m21ToXml.GeneralObjectExporter().parse(score)
    with open(output_path, 'wb') as f:
        f.write(xml_bytes)
    print(f"  Generated: {name}")
    return output_path

# =============================================================================
# RHYTHM & METER
# =============================================================================

def create_nested_tuplets():
    s = create_score("Nested Tuplets")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Triplet eighths
    m1 = stream.Measure(number=1)
    t1 = duration.Tuplet(3, 2, 'eighth')
    for i, pc in enumerate(['C5', 'D5', 'E5']):
        n = note.Note(pc)
        n.duration.appendTuplet(t1)
        m1.append(n)
    m1.append(note.Note('F5', quarterLength=2.5))
    p.append(m1)

    # Quintuplet
    m2 = stream.Measure(number=2)
    t2 = duration.Tuplet(5, 4, 'eighth')
    for i in range(5):
        n = note.Note(pitch.Pitch(65 + i))
        n.duration.appendTuplet(t2)
        m2.append(n)
    m2.append(note.Note('A5', quarterLength=1.5))
    p.append(m2)

    # Sextuplet
    m3 = stream.Measure(number=3)
    t3 = duration.Tuplet(6, 4, 'eighth')
    for i in range(6):
        n = note.Note(pitch.Pitch(67 + i % 5))
        n.duration.appendTuplet(t3)
        m3.append(n)
    m3.append(note.Note('C6', quarterLength=1))
    p.append(m3)

    # Regular
    m4 = stream.Measure(number=4)
    m4.append(note.Note('B5', quarterLength=2))
    m4.append(note.Note('A5', quarterLength=2))
    p.append(m4)

    s.append(p)
    return s

def create_mixed_meters():
    s = create_score("Mixed Meters")
    p = stream.Part()
    p.append(clef.TrebleClef())

    # 7/8
    m1 = stream.Measure(number=1)
    m1.append(meter.TimeSignature('7/8'))
    for i in range(7):
        m1.append(note.Note(pitch.Pitch(60 + i), quarterLength=0.5))
    p.append(m1)

    # 5/4
    m2 = stream.Measure(number=2)
    m2.append(meter.TimeSignature('5/4'))
    for i in range(5):
        m2.append(note.Note(pitch.Pitch(64 + i), quarterLength=1))
    p.append(m2)

    # 3/4
    m3 = stream.Measure(number=3)
    m3.append(meter.TimeSignature('3/4'))
    for i in range(3):
        m3.append(note.Note(pitch.Pitch(68 + i), quarterLength=1))
    p.append(m3)

    # 9/8
    m4 = stream.Measure(number=4)
    m4.append(meter.TimeSignature('9/8'))
    for i in range(3):
        m4.append(note.Note(pitch.Pitch(71 - i * 2), quarterLength=1.5))
    p.append(m4)

    # 4/4
    m5 = stream.Measure(number=5)
    m5.append(meter.TimeSignature('4/4'))
    m5.append(note.Note('C5', quarterLength=4))
    p.append(m5)

    s.append(p)
    return s

def create_complex_syncopation():
    s = create_score("Complex Syncopation")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Off-beat eighths
    m1 = stream.Measure(number=1)
    m1.append(note.Rest(quarterLength=0.5))
    for i in range(7):
        n = note.Note(pitch.Pitch(60 + (i % 5) * 2), quarterLength=0.5)
        m1.append(n)
    p.append(m1)

    # Tie across barline using spanner
    m2 = stream.Measure(number=2)
    n1 = note.Note('C5', quarterLength=3)
    m2.append(n1)
    p.append(m2)

    m3 = stream.Measure(number=3)
    n2 = note.Note('C5', quarterLength=1)
    # Create tie
    tie_spanner = spanner.Tie(n1, n2)
    m3.append(n2)
    m3.append(note.Rest(quarterLength=0.5))
    m3.append(note.Note('B4', quarterLength=0.5))
    m3.append(note.Rest(quarterLength=0.5))
    m3.append(note.Note('A4', quarterLength=0.5))
    m3.append(note.Rest(quarterLength=0.5))
    m3.append(note.Note('G4', quarterLength=0.5))
    p.append(m3)

    # Double-dotted
    m4 = stream.Measure(number=4)
    dd = note.Note('E4')
    dd.duration = duration.Duration(type='half', dots=2)
    m4.append(dd)
    m4.append(note.Note('D4', quarterLength=0.5))
    p.append(m4)

    s.append(p)
    return s

def create_grace_notes():
    s = create_score("Grace Notes")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Acciaccatura
    m1 = stream.Measure(number=1)
    gn = note.Note('D5')
    gn.duration.isGrace = True
    gn.duration.slash = True
    gn.duration.type = 'eighth'
    m1.append(gn)
    m1.append(note.Note('C5', quarterLength=1))
    m1.append(note.Note('B4', quarterLength=1))
    m1.append(note.Note('A4', quarterLength=2))
    p.append(m1)

    # Appoggiatura
    m2 = stream.Measure(number=2)
    gn2 = note.Note('G4')
    gn2.duration.isGrace = True
    gn2.duration.slash = False
    gn2.duration.type = 'eighth'
    m2.append(gn2)
    m2.append(note.Note('A4', quarterLength=2))
    m2.append(note.Note('B4', quarterLength=2))
    p.append(m2)

    # Grace chord
    m3 = stream.Measure(number=3)
    m3.append(note.Note('C5', quarterLength=2))
    gc = chord.Chord(['D5', 'E5'])
    gc.duration.isGrace = True
    gc.duration.type = 'eighth'
    m3.append(gc)
    m3.append(note.Note('F5', quarterLength=2))
    p.append(m3)

    # Long grace
    m4 = stream.Measure(number=4)
    gl = note.Note('A4')
    gl.duration.isGrace = True
    gl.duration.type = '16th'
    m4.append(gl)
    m4.append(note.Note('G4', quarterLength=4))
    p.append(m4)

    s.append(p)
    return s

# =============================================================================
# NOTATION & TEXT
# =============================================================================

def create_lyrics_verses():
    s = create_score("Lyrics with Verses")
    p = stream.Part()
    p.append(meter.TimeSignature('3/4'))
    p.append(clef.TrebleClef())

    lyrics = ["Hel-", "lo,", "sweet", "mu-", "sic", "song"]

    for meas in range(2):
        m = stream.Measure(number=meas + 1)
        for i in range(3):
            idx = meas * 3 + i
            n = note.Note(pitch.Pitch(64 + i), quarterLength=1)
            if idx < len(lyrics):
                n.lyric = lyrics[idx]
            m.append(n)
        p.append(m)

    s.append(p)
    return s

def create_title_metadata():
    s = stream.Score()
    md = metadata.Metadata()
    md.title = "Complete Metadata Test"
    md.subtitle = "A Test Piece for ScoreForge"
    md.composer = "Jane Composer"
    md.arranger = "John Arranger"
    md.lyricist = "Jill Lyricist"
    md.date = metadata.DateSingle("2024")
    md.copyright = "Copyright 2024 ScoreForge Test"
    s.metadata = md

    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    for meas in range(1, 5):
        m = stream.Measure(number=meas)
        for i in range(4):
            m.append(note.Note(pitch.Pitch(64 + i), quarterLength=1))
        p.append(m)

    s.append(p)
    return s

def create_annotations():
    s = create_score("Annotations Test")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Tempo + Rehearsal A
    m1 = stream.Measure(number=1)
    mm = tempo.MetronomeMark(number=120)
    m1.insert(0, mm)
    rm = expressions.RehearsalMark('A')
    m1.insert(0, rm)
    m1.append(note.Note('C5', quarterLength=2))
    m1.append(note.Note('D5', quarterLength=2))
    p.append(m1)

    # Text expression
    m2 = stream.Measure(number=2)
    te = expressions.TextExpression("dolce")
    m2.insert(0, te)
    m2.append(note.Note('E5', quarterLength=4))
    p.append(m2)

    # Rehearsal B + rit.
    m3 = stream.Measure(number=3)
    rm2 = expressions.RehearsalMark('B')
    m3.insert(0, rm2)
    rit = expressions.TextExpression("rit.")
    m3.insert(0, rit)
    m3.append(note.Note('F5', quarterLength=2))
    m3.append(note.Note('G5', quarterLength=2))
    p.append(m3)

    # Segno
    m4 = stream.Measure(number=4)
    seg = repeat.Segno()
    m4.insert(0, seg)
    m4.append(note.Note('A5', quarterLength=4))
    p.append(m4)

    # Coda
    m5 = stream.Measure(number=5)
    cod = repeat.Coda()
    m5.insert(0, cod)
    m5.append(note.Note('B5', quarterLength=4))
    p.append(m5)

    # Fine
    m6 = stream.Measure(number=6)
    fine = expressions.TextExpression("Fine")
    m6.insert(0, fine)
    m6.append(note.Note('C6', quarterLength=4))
    p.append(m6)

    s.append(p)
    return s

def create_dynamics_hairpins():
    s = create_score("Dynamics and Hairpins")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # pp -> p -> mp
    m1 = stream.Measure(number=1)
    m1.insert(0, dynamics.Dynamic('pp'))
    m1.append(note.Note('C5', quarterLength=1))
    m1.insert(1, dynamics.Dynamic('p'))
    m1.append(note.Note('D5', quarterLength=1))
    m1.insert(2, dynamics.Dynamic('mp'))
    m1.append(note.Note('E5', quarterLength=1))
    m1.append(note.Note('F5', quarterLength=1))
    p.append(m1)

    # mf with crescendo to f
    m2 = stream.Measure(number=2)
    m2.insert(0, dynamics.Dynamic('mf'))
    n1 = note.Note('G5', quarterLength=2)
    n2 = note.Note('A5', quarterLength=2)
    cresc = dynamics.Crescendo()
    cresc.addSpannedElements([n1, n2])
    m2.append(n1)
    m2.insert(2, dynamics.Dynamic('f'))
    m2.append(n2)
    p.append(m2)

    # sfz and ff
    m3 = stream.Measure(number=3)
    m3.insert(0, dynamics.Dynamic('sfz'))
    m3.append(note.Note('B5', quarterLength=2))
    m3.insert(2, dynamics.Dynamic('ff'))
    m3.append(note.Note('C6', quarterLength=2))
    p.append(m3)

    # Decrescendo
    m4 = stream.Measure(number=4)
    m4.insert(0, dynamics.Dynamic('f'))
    n3 = note.Note('D6', quarterLength=2)
    n4 = note.Note('C6', quarterLength=2)
    decresc = dynamics.Diminuendo()
    decresc.addSpannedElements([n3, n4])
    m4.append(n3)
    m4.insert(2, dynamics.Dynamic('p'))
    m4.append(n4)
    p.append(m4)

    # fp and sfp
    m5 = stream.Measure(number=5)
    m5.insert(0, dynamics.Dynamic('fp'))
    m5.append(note.Note('A5', quarterLength=2))
    m5.insert(2, dynamics.Dynamic('sfp'))
    m5.append(note.Note('G5', quarterLength=2))
    p.append(m5)

    s.append(p)
    return s

# =============================================================================
# ARTICULATION & PERFORMANCE
# =============================================================================

def create_articulations():
    s = create_score("Articulations Test")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    arts = [
        (articulations.Staccato, 'C5'),
        (articulations.Accent, 'D5'),
        (articulations.Tenuto, 'E5'),
        (articulations.StrongAccent, 'F5'),
        (articulations.Spiccato, 'G5'),
        (articulations.Sforzando, 'A5'),
        (articulations.DetachedLegato, 'B5'),
    ]

    meas = 1
    for i in range(0, len(arts), 2):
        m = stream.Measure(number=meas)
        for j in range(2):
            if i + j < len(arts):
                art_cls, pc = arts[i + j]
                n = note.Note(pc, quarterLength=2)
                n.articulations.append(art_cls())
                m.append(n)
            else:
                m.append(note.Rest(quarterLength=2))
        p.append(m)
        meas += 1

    # Fermata
    mf = stream.Measure(number=meas)
    nf = note.Note('C5', quarterLength=4)
    nf.articulations.append(articulations.Fermata())
    mf.append(nf)
    p.append(mf)

    # Staccatissimo
    ms = stream.Measure(number=meas + 1)
    ns = note.Note('D5', quarterLength=4)
    ns.articulations.append(articulations.Staccatissimo())
    ms.append(ns)
    p.append(ms)

    s.append(p)
    return s

def create_marching_stickings():
    s = create_score("Marching Stickings")
    p = stream.Part()
    p.partName = "Snare Drum"
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.PercussionClef())

    stickings = ['R', 'L', 'R', 'L', 'R', 'R', 'L', 'L', 'R', 'L', 'R', 'L', 'L', 'R', 'L', 'R']

    idx = 0
    for meas in range(1, 5):
        m = stream.Measure(number=meas)
        for i in range(4):
            n = note.Unpitched()
            n.duration = duration.Duration(quarterLength=1)
            if idx < len(stickings):
                se = expressions.TextExpression(stickings[idx])
                n.expressions.append(se)
            m.append(n)
            idx += 1
        p.append(m)

    s.append(p)
    return s

def create_ornaments():
    s = create_score("Ornaments Test")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Trill
    m1 = stream.Measure(number=1)
    nt = note.Note('C5', quarterLength=4)
    nt.expressions.append(expressions.Trill())
    m1.append(nt)
    p.append(m1)

    # Turn
    m2 = stream.Measure(number=2)
    nturn = note.Note('D5', quarterLength=2)
    nturn.expressions.append(expressions.Turn())
    m2.append(nturn)
    m2.append(note.Note('E5', quarterLength=2))
    p.append(m2)

    # Mordent
    m3 = stream.Measure(number=3)
    nm = note.Note('F5', quarterLength=2)
    nm.expressions.append(expressions.Mordent())
    m3.append(nm)
    nim = note.Note('A5', quarterLength=2)
    nim.expressions.append(expressions.InvertedMordent())
    m3.append(nim)
    p.append(m3)

    # Tremolo
    m4 = stream.Measure(number=4)
    ntr = note.Note('B5', quarterLength=4)
    ntr.expressions.append(expressions.Tremolo())
    m4.append(ntr)
    p.append(m4)

    s.append(p)
    return s

# =============================================================================
# ENSEMBLE & LAYOUT
# =============================================================================

def create_full_orchestra():
    s = create_score("Full Orchestra")

    instruments = [
        ("Flute", clef.TrebleClef(), 20),
        ("Oboe", clef.TrebleClef(), 18),
        ("Clarinet", clef.TrebleClef(), 16),
        ("Bassoon", clef.BassClef(), 0),
        ("Horn", clef.TrebleClef(), 11),
        ("Trumpet", clef.TrebleClef(), 13),
        ("Trombone", clef.BassClef(), -5),
        ("Tuba", clef.BassClef(), -12),
        ("Timpani", clef.BassClef(), -8),
        ("Violin I", clef.TrebleClef(), 15),
        ("Violin II", clef.TrebleClef(), 14),
        ("Viola", clef.AltoClef(), 7),
        ("Cello", clef.BassClef(), -1),
        ("Bass", clef.BassClef(), -14),
        ("Harp", clef.TrebleClef(), 15),
    ]

    for name, clef_type, pitch_off in instruments:
        p = stream.Part()
        p.partName = name
        p.append(meter.TimeSignature('4/4'))
        p.append(clef_type)

        for meas in range(1, 3):
            m = stream.Measure(number=meas)
            base = 60 + pitch_off
            m.append(note.Note(pitch.Pitch(base), quarterLength=2))
            m.append(note.Note(pitch.Pitch(base + 2), quarterLength=2))
            m.append(note.Note(pitch.Pitch(base + 3), quarterLength=1))
            m.append(note.Note(pitch.Pitch(base + 4), quarterLength=1))
            p.append(m)

        s.append(p)

    return s

def create_solo_with_accompaniment():
    s = create_score("Solo with Accompaniment")

    # Solo Violin
    solo = stream.Part()
    solo.partName = "Solo Violin"
    solo.append(meter.TimeSignature('4/4'))
    solo.append(clef.TrebleClef())

    for meas in range(1, 5):
        m = stream.Measure(number=meas)
        m.append(note.Note(pitch.Pitch(72 + meas), quarterLength=2))
        m.append(note.Note(pitch.Pitch(74 + meas), quarterLength=2))
        solo.append(m)

    s.append(solo)

    # Piano RH
    prh = stream.Part()
    prh.partName = "Piano"
    prh.append(meter.TimeSignature('4/4'))
    prh.append(clef.TrebleClef())

    for meas in range(1, 5):
        m = stream.Measure(number=meas)
        c = chord.Chord([60 + meas, 64 + meas, 67 + meas])
        c.duration = duration.Duration(quarterLength=4)
        m.append(c)
        prh.append(m)

    s.append(prh)

    # Piano LH
    plh = stream.Part()
    plh.partName = "Piano"
    plh.append(meter.TimeSignature('4/4'))
    plh.append(clef.BassClef())

    for meas in range(1, 5):
        m = stream.Measure(number=meas)
        m.append(note.Note(pitch.Pitch(36 + meas * 2), quarterLength=4))
        plh.append(m)

    s.append(plh)

    return s

def create_multi_voice():
    s = create_score("Multi-Voice")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Voice 1
    v1 = stream.Voice()
    for i in range(4):
        n = note.Note(pitch.Pitch(72 + i * 1), quarterLength=1)
        n.stemDirection = 'up'
        v1.append(n)

    # Voice 2
    v2 = stream.Voice()
    for i in range(1):
        n = note.Note(pitch.Pitch(64), quarterLength=2)
        n.stemDirection = 'down'
        v2.append(n)

    m1 = stream.Measure(number=1)
    m1.insert(0, v1)
    m1.insert(0, v2)
    p.append(m1)

    # Homophonic chords
    for meas in range(2, 5):
        m = stream.Measure(number=meas)
        c = chord.Chord(['C5', 'E4', 'G4', 'C4'])
        c.duration = duration.Duration(quarterLength=4)
        m.append(c)
        p.append(m)

    s.append(p)
    return s

# =============================================================================
# EDGE CASES
# =============================================================================

def create_key_changes():
    s = create_score("Key Changes")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    keys = [
        key.KeySignature(0), key.KeySignature(1), key.KeySignature(2),
        key.KeySignature(-1), key.KeySignature(-1), key.KeySignature(1),
    ]

    for meas, ks in enumerate(keys, 1):
        m = stream.Measure(number=meas)
        m.insert(0, ks)
        for i in range(4):
            m.append(note.Note(pitch.Pitch(60 + i * 2), quarterLength=1))
        p.append(m)

    s.append(p)
    return s

def create_clef_changes():
    s = create_score("Clef Changes")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Treble -> Bass
    m1 = stream.Measure(number=1)
    m1.append(note.Note('C5', quarterLength=2))
    m1.insert(2, clef.BassClef())
    m1.append(note.Note('C3', quarterLength=2))
    p.append(m1)

    # Bass -> Alto -> Treble
    m2 = stream.Measure(number=2)
    m2.append(note.Note('E3', quarterLength=1))
    m2.insert(1, clef.AltoClef())
    m2.append(note.Note('C4', quarterLength=1))
    m2.insert(2, clef.TrebleClef())
    m2.append(note.Note('G4', quarterLength=2))
    p.append(m2)

    # Tenor
    m3 = stream.Measure(number=3)
    m3.insert(0, clef.TenorClef())
    m3.append(note.Note('B3', quarterLength=4))
    p.append(m3)

    # Treble 8va
    m4 = stream.Measure(number=4)
    m4.insert(0, clef.TrebleClef())
    m4.append(note.Note('C5', quarterLength=4))
    p.append(m4)

    # Percussion
    m5 = stream.Measure(number=5)
    m5.insert(0, clef.PercussionClef())
    for i in range(4):
        n = note.Unpitched()
        n.duration = duration.Duration(quarterLength=1)
        m5.append(n)
    p.append(m5)

    # Treble 8vb
    m6 = stream.Measure(number=6)
    m6.insert(0, clef.Treble8vbClef())
    m6.append(note.Note('C5', quarterLength=4))
    p.append(m6)

    s.append(p)
    return s

def create_repeats_codas():
    s = create_score("Repeats and Codas")
    p = stream.Part()
    p.append(meter.TimeSignature('4/4'))
    p.append(clef.TrebleClef())

    # Segno
    m1 = stream.Measure(number=1)
    m1.insert(0, repeat.Segno())
    m1.append(note.Note('C5', quarterLength=4))
    p.append(m1)

    # Start repeat
    m2 = stream.Measure(number=2)
    m2.leftBarline = bar.Barline('heavy-light')
    m2.append(note.Note('D5', quarterLength=4))
    p.append(m2)

    # End repeat
    m3 = stream.Measure(number=3)
    m3.rightBarline = bar.Barline('light-heavy')
    m3.append(note.Note('E5', quarterLength=4))
    p.append(m3)

    # Volta 1
    m4 = stream.Measure(number=4)
    rb1 = spanner.RepeatBracket(m4, number=1)
    m4.append(note.Note('F5', quarterLength=4))
    p.append(m4)

    # Volta 2
    m5 = stream.Measure(number=5)
    rb2 = spanner.RepeatBracket(m5, number=1)
    m5.append(note.Note('G5', quarterLength=4))
    p.append(m5)

    # Coda
    m6 = stream.Measure(number=6)
    m6.insert(0, repeat.Coda())
    m6.append(note.Note('A5', quarterLength=4))
    p.append(m6)

    # DS al Fine
    m7 = stream.Measure(number=7)
    m7.insert(0, expressions.TextExpression("D.S. al Fine"))
    m7.append(note.Note('B5', quarterLength=4))
    p.append(m7)

    # Fine
    m8 = stream.Measure(number=8)
    m8.insert(0, expressions.TextExpression("Fine"))
    m8.append(note.Note('C6', quarterLength=4))
    m8.rightBarline = bar.Barline('light-heavy')
    p.append(m8)

    s.append(p)
    return s

# =============================================================================
# CLI
# =============================================================================

CATEGORIES = {
    'rhythm': [
        ('nested_tuplets', create_nested_tuplets),
        ('mixed_meters', create_mixed_meters),
        ('complex_syncopation', create_complex_syncopation),
        ('grace_notes', create_grace_notes),
    ],
    'notation': [
        ('lyrics_verses', create_lyrics_verses),
        ('title_metadata', create_title_metadata),
        ('annotations', create_annotations),
        ('dynamics_hairpins', create_dynamics_hairpins),
    ],
    'articulation': [
        ('articulations', create_articulations),
        ('marching_stickings', create_marching_stickings),
        ('ornaments', create_ornaments),
    ],
    'ensemble': [
        ('full_orchestra', create_full_orchestra),
        ('solo_with_accompaniment', create_solo_with_accompaniment),
        ('multi_voice', create_multi_voice),
    ],
    'edge': [
        ('key_changes', create_key_changes),
        ('clef_changes', create_clef_changes),
        ('repeats_codas', create_repeats_codas),
    ],
}

@click.command()
@click.option('--category', '-c', default=None, help='Generate only this category')
@click.option('--fixture', '-f', default=None, help='Generate only this fixture')
def main(category, fixture):
    print("=" * 60)
    print("ScoreForge Fixture Generator")
    print("=" * 60)

    generated = []

    if category and category not in CATEGORIES:
        print(f"Unknown category: {category}")
        print(f"Valid categories: {', '.join(CATEGORIES.keys())}")
        sys.exit(1)

    cats = [category] if category else list(CATEGORIES.keys())

    for cat in cats:
        print(f"\n[{cat.upper()}]")
        for name, creator in CATEGORIES[cat]:
            if fixture and name != fixture:
                continue
            try:
                score = creator()
                path = save_score(score, name)
                generated.append((name, cat, str(path)))
            except Exception as e:
                print(f"  ERROR {name}: {e}")

    print(f"\n{'=' * 60}")
    print(f"Generated {len(generated)} fixtures")
    print("=" * 60)

if __name__ == "__main__":
    main()
