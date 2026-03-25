"""Vision-based music extraction using Claude."""
import base64
import json
import os
from pathlib import Path
from typing import Optional

import anthropic

from models.score import Score, Part
from models.measure import Measure, KeySignature, TimeSignature, Clef, Barline
from models.note import Note, NoteType, Pitch, Accidental


EXTRACTION_PROMPT = """You are an expert music notation reader. Analyze this sheet music image and extract EVERY detail into structured JSON.

Output a JSON object with this exact structure:
{
  "title": "string or null",
  "composer": "string or null",
  "parts": [
    {
      "name": "string (e.g., 'Piano', 'Violin')",
      "staves": 1 or 2,
      "measures": [
        {
          "number": 1,
          "time_signature": {"beats": 4, "beat_type": 4} or null,
          "key_signature": {"fifths": 0, "mode": "major"} or null,
          "clef": {"sign": "G", "line": 2} or null,
          "divisions": 1,
          "notes": [
            {
              "type": "quarter",
              "is_rest": false,
              "pitch": {"step": "C", "octave": 4, "alter": 0},
              "accidental": null,
              "dots": 0,
              "is_chord": false,
              "voice": 1,
              "staff": 1,
              "tie_start": false,
              "tie_stop": false,
              "slur_start": false,
              "slur_stop": false,
              "beam": null,
              "dynamic": null,
              "articulation": null,
              "lyrics": [],
              "fermata": false,
              "grace": false
            }
          ],
          "barline_right": null,
          "tempo": null
        }
      ]
    }
  ]
}

CRITICAL RULES:
- Extract EVERY note, rest, and marking. Missing even one note makes the output wrong.
- For piano/keyboard: staves=2, staff=1 for treble, staff=2 for bass
- Accidentals: "sharp", "flat", "natural", "double-sharp", "double-flat"
- Note types: "whole", "half", "quarter", "eighth", "16th", "32nd", "64th"
- Key signature fifths: negative=flats, positive=sharps (e.g., -3 = Eb major / C minor)
- Include time/key/clef only when they CHANGE (first measure must have all three)
- Chords: first note has is_chord=false, subsequent stacked notes have is_chord=true
- Beam groups: "begin", "continue", "end"
- divisions = number of divisions per quarter note (determines duration math)
- Each note's duration should be expressed in divisions (quarter=divisions, half=2*divisions, etc.)

Be extremely precise. Count every beat. Verify note durations add up to the time signature per measure."""


def encode_image(image_path: str) -> tuple[str, str]:
    """Encode an image file to base64 with media type."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }
    media_type = media_types.get(suffix, "image/png")

    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    return data, media_type


def extract_from_image(image_path: str, model: str = "claude-sonnet-4-5-20250929") -> Score:
    """Extract musical score from an image using Claude Vision."""
    client = anthropic.Anthropic()
    image_data, media_type = encode_image(image_path)

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    # Parse the JSON response
    response_text = message.content[0].text

    # Extract JSON from response (may be wrapped in markdown code blocks)
    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    data = json.loads(json_str.strip())
    return _build_score(data)


def _build_score(data: dict) -> Score:
    """Convert raw JSON extraction to Score model."""
    score = Score(
        title=data.get("title"),
        composer=data.get("composer"),
    )

    for i, part_data in enumerate(data.get("parts", [])):
        part = Part(
            id=f"P{i + 1}",
            name=part_data.get("name", f"Part {i + 1}"),
            staves=part_data.get("staves", 1),
        )

        for m_data in part_data.get("measures", []):
            measure = Measure(number=m_data.get("number", 1))

            # Time signature
            if ts := m_data.get("time_signature"):
                measure.time_signature = TimeSignature(
                    beats=ts["beats"], beat_type=ts["beat_type"]
                )
                if not score.initial_time:
                    score.initial_time = measure.time_signature

            # Key signature
            if ks := m_data.get("key_signature"):
                measure.key_signature = KeySignature(
                    fifths=ks["fifths"], mode=ks.get("mode", "major")
                )
                if not score.initial_key:
                    score.initial_key = measure.key_signature

            # Clef
            if cl := m_data.get("clef"):
                measure.clef = Clef(sign=cl["sign"], line=cl["line"])

            # Divisions
            measure.divisions = m_data.get("divisions", 1)

            # Tempo
            measure.tempo = m_data.get("tempo")
            if measure.tempo and not score.initial_tempo:
                score.initial_tempo = measure.tempo

            # Barline
            if bl := m_data.get("barline_right"):
                measure.barline_right = Barline(style=bl.get("style", "regular"))

            # Notes
            for n_data in m_data.get("notes", []):
                note = _build_note(n_data)
                measure.notes.append(note)

            part.measures.append(measure)

        score.parts.append(part)

    return score


NOTE_TYPE_MAP = {
    "whole": NoteType.WHOLE,
    "half": NoteType.HALF,
    "quarter": NoteType.QUARTER,
    "eighth": NoteType.EIGHTH,
    "16th": NoteType.SIXTEENTH,
    "32nd": NoteType.THIRTY_SECOND,
    "64th": NoteType.SIXTY_FOURTH,
}

ACCIDENTAL_MAP = {
    "sharp": Accidental.SHARP,
    "flat": Accidental.FLAT,
    "natural": Accidental.NATURAL,
    "double-sharp": Accidental.DOUBLE_SHARP,
    "double-flat": Accidental.DOUBLE_FLAT,
}


def _build_note(data: dict) -> Note:
    """Convert raw note data to Note model."""
    note_type = NOTE_TYPE_MAP.get(data.get("type", "quarter"), NoteType.QUARTER)

    pitch = None
    if not data.get("is_rest", False) and data.get("pitch"):
        p = data["pitch"]
        acc = ACCIDENTAL_MAP.get(data.get("accidental")) if data.get("accidental") else None
        pitch = Pitch(
            step=p["step"],
            octave=p["octave"],
            alter=p.get("alter", 0),
            accidental=acc,
        )

    return Note(
        note_type=note_type,
        duration=data.get("duration", 1),
        is_rest=data.get("is_rest", False),
        pitch=pitch,
        dot_count=data.get("dots", 0),
        is_chord=data.get("is_chord", False),
        voice=data.get("voice", 1),
        staff=data.get("staff", 1),
        beam=data.get("beam"),
        tie_start=data.get("tie_start", False),
        tie_stop=data.get("tie_stop", False),
        slur_start=data.get("slur_start", False),
        slur_stop=data.get("slur_stop", False),
        dynamic=data.get("dynamic"),
        articulation=data.get("articulation"),
        lyrics=data.get("lyrics", []),
        fermata=data.get("fermata", False),
        grace=data.get("grace", False),
    )
