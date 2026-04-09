"""Vision-based music extraction using Claude."""
import base64
import json
import os
from pathlib import Path
from typing import Optional

from core import api

from models.score import Score, Part
from models.measure import Measure, KeySignature, TimeSignature, Clef, Barline
from models.note import Note, NoteType, Pitch, Accidental


# ---------------------------------------------------------------------------
# Structured two-pass extraction prompts
# ---------------------------------------------------------------------------

STRUCTURE_PROMPT = """You are an expert music notation reader. Analyze this sheet music image and extract the HIGH-LEVEL STRUCTURE first.

Output ONLY a valid JSON object — no explanation, no preamble, no markdown fences. Start your response with `{` and end with `}`.

Use this exact structure:
{
  "title": "string or null",
  "composer": "string or null",
  "page_count_estimate": 1,
  "parts": [
    {
      "name": "string (e.g., 'Piano', 'Violin')",
      "staves": 1,
      "clefs": [{"sign": "G", "line": 2}],
      "measure_count": 8
    }
  ],
  "global_key_signature": {"fifths": 0, "mode": "major"},
  "global_time_signature": {"beats": 4, "beat_type": 4},
  "tempo": null
}

RULES:
- Count measures carefully by counting barlines visible in the image. Do NOT guess or extrapolate.
- For piano/keyboard: staves=2 (treble + bass).
- Key signature fifths: negative=flats, positive=sharps (-2 = Bb major, 1 = G major, etc.)
- TIME SIGNATURE: Read the printed number at the top (beats) and bottom (beat-type) of the time signature symbol. Do NOT assume 4/4 as a default — it may be 3/4, 6/8, 2/4, or anything else.
- If there are multiple pages visible, set page_count_estimate accordingly.
- This is ONLY the structure pass. Do not extract individual notes yet.
- YOUR ENTIRE RESPONSE MUST BE VALID JSON. No other text.

CRITICAL — ANTI-HALLUCINATION:
- Do NOT infer the title, composer, or musical content from melody patterns in your training data.
- Extract ONLY information explicitly printed in the image (title block, composer credit, notation symbols).
- If you think you recognize a famous melody, DISCARD that recognition entirely — read the image literally.
- The measure count MUST come from counting visible barlines, not from memory of any piece."""


DETAIL_PROMPT = """You are an expert music notation reader performing a DETAILED note-by-note extraction.

IMPORTANT: Output ONLY a valid JSON object. No explanation, no preamble, no markdown fences, no trailing text. Start your response with `{{` and end with `}}`.

The score structure has already been identified:
{structure_json}

Now extract EVERY note, rest, and marking into the full JSON structure below. Be extremely precise.

Output a JSON object with this exact structure:
{{
  "title": "string or null",
  "composer": "string or null",
  "parts": [
    {{
      "name": "string",
      "staves": 1 or 2,
      "measures": [
        {{
          "number": 1,
          "time_signature": {{"beats": 4, "beat_type": 4}} or null,
          "key_signature": {{"fifths": 0, "mode": "major"}} or null,
          "clef": {{"sign": "G", "line": 2}} or null,
          "divisions": 1,
          "notes": [
            {{
              "type": "quarter",
              "is_rest": false,
              "pitch": {{"step": "C", "octave": 4, "alter": 0}},
              "accidental": null,
              "dots": 0,
              "is_chord": false,
              "voice": 1,
              "staff": 1,
              "stem": null,
              "tie_start": false,
              "tie_stop": false,
              "slur_start": false,
              "slur_stop": false,
              "beam": null,
              "dynamic": null,
              "articulation": null,
              "lyrics": [],
              "fermata": false,
              "grace": false,
              "tuplet_actual": null,
              "tuplet_normal": null,
              "tuplet_start": false,
              "tuplet_stop": false
            }}
          ],
          "barline_right": null,
          "tempo": null
        }}
      ]
    }}
  ]
}}

CRITICAL RULES — READ CAREFULLY:

1. COMPLETENESS: Extract EVERY note, rest, and marking. Missing even one note is a failure.

2. DURATION MATH — SELF-VERIFICATION REQUIRED:
   - "divisions" = number of divisions per quarter note.
   - In each measure, the sum of non-chord note durations MUST equal:
     (time_signature.beats / time_signature.beat_type) * 4 * divisions
   - Example: 4/4 with divisions=1 => total = 4. 3/4 with divisions=1 => total = 3. 6/8 with divisions=2 => total = 6.
   - For EACH measure, after writing it, verify the sum. If the sum is SHORT, you are MISSING NOTES — look again.
   - Do NOT move to the next measure until the current one is duration-complete.

3. PITCH ACCURACY — STEP-BY-STEP PROTOCOL (FOLLOW IN ORDER):
   STEP 1: IDENTIFY THE CLEF FIRST (before reading any notes)
   - Look at the LEFT SIDE of the staff for the clef symbol
   - Is it treble (G clef), bass (F clef), or alto (C clef)?
   
   STEP 2: ESTABLISH THE REFERENCE PITCH AS SPATIAL ANCHOR
   - Treble clef: spiral wraps around line 2 = G4. Lines bottom-to-top: E4 G4 B4 D5 F5. Spaces: F4 A4 C5 E5
   - Bass clef: two dots around line 4 = F3. Lines: G2 B2 D3 F3 A3. Spaces: A2 C3 E3 G3
   - Use this anchor for EVERY note — count from this known position
   
   STEP 3: FOR EACH NOTE, COUNT LINES/SPACES FROM ANCHOR
   - Count the notehead vertical position relative to the clef anchor line
   - Each step up/down = one diatonic step (C D E F G A B then repeat)
   - Above the staff: continue counting upward with ledger lines
   - Below the staff: continue counting downward with ledger lines
   
   STEP 4: ASSIGN CORRECT OCTAVE
   - Octave changes at C (every C resets the octave number)
   - Middle C = C4 (one ledger line below treble staff)

4. KEY/TIME/CLEF RULES:
   - First measure MUST include time_signature, key_signature, and clef.
   - Subsequent measures: include these ONLY when they CHANGE.
   - TIME SIGNATURE: Read the printed symbol carefully. Do NOT default to 4/4. A "3" on top means 3 beats per measure.

5. CHORD NOTATION:
   - First note in a chord: is_chord = false
   - Additional stacked notes: is_chord = true (same duration, share the beat)

6. MULTI-STAFF (Piano):
   - staves = 2
   - staff = 1 for treble, staff = 2 for bass
   - Use voice = 1 for treble staff notes, voice = 2 for bass staff notes

6a. MULTI-VOICE (Same Staff):
   - When multiple independent voices share a single staff (common in keyboard music, Bach chorales, polyphony), you MUST assign each note to the correct voice.
   - STEM DIRECTION is the primary voice separator:
     * Notes with stems pointing UP (above the notehead) → voice 1
     * Notes with stems pointing DOWN (below the notehead) → voice 2
   - Set the "stem" field on every note: "up" or "down"
   - Number voices sequentially: voice 1, voice 2, voice 3, etc.
   - Within a measure, list ALL voice 1 notes first, then ALL voice 2 notes, etc.
   - Each voice must be duration-complete on its own (voice 1 notes sum to full measure, voice 2 notes sum to full measure).
   - If a voice has no notes for part of the measure, include a rest with that voice number.
   - Example: In 4/4 time, voice 1 has 4 quarter notes (C5 C#5 D5 Eb5, all stem up), voice 2 has 1 half note (E4, stem down) + 1 half rest. List: 4 voice-1 notes first, then 1 voice-2 half note, then 1 voice-2 half rest.

   VOICE ASSIGNMENT FALLBACK RULES (apply when stem direction is absent or ambiguous):
   a) WHOLE NOTES & HALF NOTES (no visible stem): assign by pitch position on the staff.
      - The note with the HIGHER pitch (closer to the top of the staff) → voice 1
      - The note with the LOWER pitch → voice 2
      - If only one such note exists in the measure, assign it to voice 1.
   b) RESTS: assign to voice 1 by default.
      - Only assign a rest to voice 2 (or higher) when a second voice rest is EXPLICITLY
        notated in the score (e.g., a rest visually offset from the voice-1 rest position).
   c) TIED NOTES: carry the voice number from the note that BEGINS the tie.
      - Do NOT re-derive the voice from stem direction on tied continuations — the
        continuation note (tie_stop=true) inherits the same voice as its tie origin.
   d) BEAMED GROUPS: all notes within a single beam group share the same voice.
      - Determine the voice from the stem direction of the beam (beam stems up → voice 1,
        beam stems down → voice 2) and apply that voice to every note in the group,
        even if individual noteheads appear ambiguous.

7. NOTE TYPES: "whole", "half", "quarter", "eighth", "16th", "32nd", "64th"

8. ACCIDENTALS: "sharp", "flat", "natural", "double-sharp", "double-flat"
   - Set "alter" in pitch: -1 for flat, 1 for sharp, 0 for natural, -2 for double-flat, 2 for double-sharp
   - Set "accidental" string only when the accidental is PRINTED on the note (not implied by key sig)

9. BEAMS: "begin", "continue", "end" — for grouped eighth/sixteenth notes

10. BARLINES: null for normal, {{"style": "light-heavy"}} for final, {{"style": "light-light"}} for double

11. TIES: A curved line connecting two notes of the SAME pitch across beats or barlines.
    - First note: tie_start = true
    - Second note: tie_stop = true

12. TUPLETS:
    - Tuplets are groups of notes that modify the regular subdivision of the beat.
    - Common tuplets: triplets (3 notes in time of 2), quintuplets (5 notes in time of 4), sextuplets (6 notes in time of 4).
    - For the FIRST note of a tuplet group: tuplet_start = true, set tuplet_actual = [total notes], tuplet_normal = [normal duration notes replace]
      Example: For a triplet of eighth notes, tuplet_start = true, tuplet_actual = 3, tuplet_normal = 2
    - For subsequent notes within the tuplet group: leave tuplet fields as null
    - For the LAST note of a tuplet group: tuplet_stop = true
    - ONLY set tuplet fields when you see a specific tuplet bracket or number notation (e.g., "3" over beam). Do NOT guess.

13. ANTI-HALLUCINATION (CRITICAL):
    - Extract ONLY the notes, pitches, and rhythms you can SEE in the image.
    - Do NOT generate notes from memory or prior musical knowledge about any piece.
    - NEVER infer pitches from melody patterns you might recognize. If you think you see a familiar melody, IGNORE that recognition entirely. Read ONLY the visual vertical position of each notehead on the staff.
    - The measure count from the structure analysis is a guide, but always prefer what you can count in the image. Generate EXACTLY as many measures as you can see — no more.
    - LYRICS: If lyrics are printed below the staff, use them as a cross-check: each syllabic unit = exactly one note. Count syllables per measure to verify your note count.

14. MEASURE COMPLETENESS (PER-MEASURE GATE):
    - After writing each measure's notes array, pause and verify:
      (a) Duration sum = expected total (rule 2 above)
      (b) If lyrics are present: syllable count = note count
    - If either check fails, add the missing notes before closing the measure.
    - A measure with only 2 quarter notes in 4/4 time is INCOMPLETE — you are missing 2 beats.



15. STAFF COUNT:
    - Count the number of physically visible staff systems in the image.
    - Report only staves you can see — do not add a bass staff because the music style might imply one.
    - If you see only one staff (treble or bass), set staves=1.

FINAL SELF-CHECK: After completing extraction, verify:
- Total measure count matches what you can count in the image
- Each measure's note durations sum to the time signature
- No notes are missing from any measure
- Pitches are correct relative to the clef and key signature

REMINDER: Your entire response must be a single valid JSON object. Do NOT include any text before `{{` or after the final `}}`."""


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

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


def encode_pdf_pages(pdf_path: str) -> list[tuple[str, str]]:
    """Encode a multi-page PDF as individual page images.

    Falls back to sending the whole PDF if conversion tools aren't available.
    Returns list of (base64_data, media_type) tuples.
    """
    path = Path(pdf_path)
    if path.suffix.lower() != ".pdf":
        return [encode_image(pdf_path)]

    # Try to split PDF pages using Pillow (requires pdf2image or similar)
    # Fallback: send the whole PDF as one document
    data, media_type = encode_image(pdf_path)
    return [(data, media_type)]


# ---------------------------------------------------------------------------
# Main extraction entry point
# ---------------------------------------------------------------------------

def extract_from_image(
    image_path: str,
    model: str = "claude-sonnet-4-5-20250929",
    use_thinking: bool = True,
    two_pass: bool = True,
) -> Score:
    """Extract musical score from an image using Claude Vision.

    Args:
        image_path: Path to sheet music image (PNG, JPG, PDF).
        model: Claude model to use.
        use_thinking: Whether to use extended thinking for complex analysis.
        two_pass: Whether to do structure-first then detail extraction.

    Returns:
        Parsed Score object.
    """
    # Client managed by core.api with fallback
    image_data, media_type = encode_image(image_path)

    image_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": image_data,
        },
    }

    if two_pass:
        return _extract_two_pass(image_block, model, use_thinking)
    else:
        return _extract_single_pass(image_block, model, use_thinking)


# ---------------------------------------------------------------------------
# Two-pass extraction (structure first, then details)
# ---------------------------------------------------------------------------

# Streaming handled by core.api.stream_and_collect


def _extract_two_pass(
    image_block: dict,
    model: str,
    use_thinking: bool,
) -> Score:
    """Two-pass extraction: structure first, then note-by-note details."""

    # --- Pass 1: Extract structure ---
    structure_kwargs = {
        "model": model,
        "max_tokens": 4000,
        "messages": [
            {
                "role": "user",
                "content": [image_block, {"type": "text", "text": STRUCTURE_PROMPT}],
            }
        ],
    }

    structure_text = api.stream_and_collect(**structure_kwargs)
    structure_json_str = _extract_json_from_response(structure_text)
    structure_data = json.loads(structure_json_str)

    # --- Pass 2: Extract detailed notes ---
    detail_prompt = DETAIL_PROMPT.format(
        structure_json=json.dumps(structure_data, indent=2)
    )

    # Build the API call kwargs
    api_kwargs = {
        "model": model,
        "max_tokens": 16000,
        "messages": [
            {
                "role": "user",
                "content": [image_block, {"type": "text", "text": detail_prompt}],
            }
        ],
    }

    # Use extended thinking for complex scores if the model supports it
    if use_thinking and _model_supports_thinking(model):
        api_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": 10000,
        }
        # Extended thinking requires higher max_tokens
        api_kwargs["max_tokens"] = 32000

    response_text = api.stream_and_collect(**api_kwargs)
    json_str = _extract_json_from_response(response_text)
    data = json.loads(json_str)

    return _build_score(data)


# ---------------------------------------------------------------------------
# Single-pass extraction (legacy / simpler path)
# ---------------------------------------------------------------------------

def _extract_single_pass(
    image_block: dict,
    model: str,
    use_thinking: bool,
) -> Score:
    """Single-pass extraction with the full detail prompt."""

    # Use a minimal structure placeholder for the detail prompt
    placeholder = {"note": "Structure not pre-analyzed. Extract everything from the image."}
    detail_prompt = DETAIL_PROMPT.format(
        structure_json=json.dumps(placeholder, indent=2)
    )

    api_kwargs = {
        "model": model,
        "max_tokens": 16000,
        "messages": [
            {
                "role": "user",
                "content": [image_block, {"type": "text", "text": detail_prompt}],
            }
        ],
    }

    if use_thinking and _model_supports_thinking(model):
        api_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": 10000,
        }
        api_kwargs["max_tokens"] = 32000

    response_text = api.stream_and_collect(**api_kwargs)
    json_str = _extract_json_from_response(response_text)
    data = json.loads(json_str)

    return _build_score(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_supports_thinking(model: str) -> bool:
    """Check if the model supports extended thinking."""
    thinking_models = ["claude-sonnet-4-5", "claude-3-7-sonnet"]
    return any(m in model for m in thinking_models)


def _get_text_from_response(message) -> str:
    """Extract text content from a message, skipping thinking blocks."""
    for block in message.content:
        if hasattr(block, "type") and block.type == "text":
            return block.text
    # Fallback
    return message.content[0].text if message.content else ""


def _extract_json_from_response(text: str) -> str:
    """Extract JSON from a response that may have preamble text or markdown fences.

    Strategy (in order):
    1. Strip markdown fences (```json ... ``` or ``` ... ```)
    2. Find the outermost { } or [ ] by bracket scanning (handles preamble/postamble)
    3. Fall back to the raw stripped text
    """
    stripped = text.strip()

    # 1. Markdown fence extraction
    if "```json" in stripped:
        candidate = stripped.split("```json")[1].split("```")[0].strip()
        if candidate:
            return candidate
    if "```" in stripped:
        candidate = stripped.split("```")[1].split("```")[0].strip()
        if candidate:
            return candidate

    # 2. Bracket scan: find first { or [ and its matching closer
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start_idx = stripped.find(start_char)
        if start_idx == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start_idx, len(stripped)):
            ch = stripped[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return stripped[start_idx:i + 1]
        # If we reach here without finding the closer, return from start to end
        return stripped[start_idx:]

    # 3. Raw fallback
    return stripped


# ---------------------------------------------------------------------------
# Score model building
# ---------------------------------------------------------------------------

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

# Allowlist for stem values emitted into MusicXML <stem> elements.
# Anything outside this set (e.g. "upward", "northward", arrow chars) is
# treated as an LLM hallucination and coerced to None.
_VALID_STEMS = {"up", "down", "none", "double"}


def _sanitize_stem(raw) -> "Optional[str]":
    """Coerce LLM stem value to an allowlisted string or None."""
    normalized = (raw or "").lower().strip()
    return normalized if normalized in _VALID_STEMS else None


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
        tuplet_actual=data.get("tuplet_actual"),
        tuplet_normal=data.get("tuplet_normal"),
        tuplet_start=data.get("tuplet_start", False),
        tuplet_stop=data.get("tuplet_stop", False),
        stem=_sanitize_stem(data.get("stem")),
        lyrics=data.get("lyrics", []),
        fermata=data.get("fermata", False),
        grace=data.get("grace", False),
    )
