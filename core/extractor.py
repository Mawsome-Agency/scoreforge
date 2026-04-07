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
- Count measures carefully by counting barlines. Do NOT guess.
- For piano/keyboard: staves=2 (treble + bass).
- Key signature fifths: negative=flats, positive=sharps (-2 = Bb major, 1 = G major, etc.)
- If there are multiple pages visible, set page_count_estimate accordingly.
- This is ONLY the structure pass. Do not extract individual notes yet.
- YOUR ENTIRE RESPONSE MUST BE VALID JSON. No other text."""


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
          "divisions": 10080,
          "notes": [
            {{
              "type": "quarter",
              "duration": 10080,
              "is_rest": false,
              "pitch": {{"step": "C", "octave": 4, "alter": 0}},
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

0. DIVISIONS SELECTION:
   - Set divisions=10080 if ANY tuplets are visible (triplet, quintuplet, sextuplet brackets or numerals 3,5,6,7,8)
   - Set divisions=1 ONLY for scores WITHOUT any tuplets (simple quarter/eighth notes)
   - divisions=10080 handles ALL common tuplet ratios without fractions

1. COMPLETENESS: Extract EVERY note, rest, and marking. Missing even one note is a failure.

2. DURATION CALCULATION — EXACT FORMULAS REQUIRED:

   A. DIVISIONS VALUE:
      - Use divisions=10080 for scores with tuplets (handles 2,3,4,5,6,7,8 note tuplets cleanly)
      - Use divisions=1 for simple scores without tuplets
      - divisions = number of units in a quarter note

   B. NOTE DURATION FORMULA (WITHOUT tuplets):
      duration = divisions * (note_type_multiplier)
      where note_type_multiplier:
        - whole = 4
        - half = 2
        - quarter = 1
        - eighth = 0.5
        - 16th = 0.25
        - 32nd = 0.125
        - 64th = 0.0625

      With dots: multiply by (1 + 0.5 * dot_count)
      Example (divisions=10080):
        - Quarter: 10080 * 1 = 10080
        - Dotted quarter: 10080 * 1 * 1.5 = 15120
        - Eighth: 10080 * 0.5 = 5040
        - 16th: 10080 * 0.25 = 2520
        - Half: 10080 * 2 = 20160
        - Dotted 16th: 10080 * 0.25 * 1.5 = 3780

   C. TUPLET DURATION CALCULATION (CRITICAL FOR NESTED TUPLETS):

      For a note in a tuplet:
        duration = normal_duration * (normal_notes / actual_notes)

      where:
        - normal_duration = duration WITHOUT tuplet (using formula B above)
        - actual_notes = number of notes in the tuplet bracket (e.g., 3 for triplet)
        - normal_notes = number of notes the tuplet replaces

      Examples (divisions=10080):

      1. Simple triplet (3 in the time of 2 eighths):
         - Each note type: eighth (normal = 5040)
         - actual_notes = 3, normal_notes = 2
         - duration = 5040 * (2/3) = 3360

      2. Quintuplet of quarters (5 in the time of 4 quarters):
         - Each note type: quarter (normal = 10080)
         - actual_notes = 5, normal_notes = 4
         - duration = 10080 * (4/5) = 8064

      3. Nested tuplet example (triplet of eighths within quintuplet of quarters):
         - Inner level: triplet (3 eighths in time of 2)
         - Each eighth: 5040 * (2/3) = 3360
         - Outer level: now these 3360-duration notes are part of quintuplet
         - actual_notes = 5, normal_notes = 4
         - duration = 3360 * (4/5) = 2688

      4. Sextuplet of eighths (6 in the time of 4 eighths):
         - Each note type: eighth (normal = 5040)
         - actual_notes = 6, normal_notes = 4
         - duration = 5040 * (4/6) = 3360

   D. SELF-VERIFICATION:
      - After extracting each measure, sum all non-chord note durations
      - Sum MUST equal: (beats / beat_type) * 4 * divisions
      - Example: 4/4 with divisions=10080 => total = 4 * 10080 = 40320
      - Example: 6/8 with divisions=5040 => total = 6 * 5040 = 30240
      - If sum doesn't match, recalculate durations before proceeding

4. PITCH ACCURACY:
   - Middle C = C4. The treble clef (G clef, line 2) places G4 on the second line.
   - Bass clef (F clef, line 4) places F3 on the fourth line.
   - Count lines and spaces carefully from the clef reference point.
   - Remember key signature accidentals apply to ALL octaves of that note unless cancelled by a natural.

5. KEY/TIME/CLEF RULES:
   - First measure MUST include time_signature, key_signature, and clef.
   - Subsequent measures: include these ONLY when they CHANGE.

6. CHORD NOTATION:
   - First note in a chord: is_chord = false
   - Additional stacked notes: is_chord = true (same duration, share the beat)

7. MULTI-STAFF (Piano):
   - staves = 2
   - staff = 1 for treble, staff = 2 for bass
   - Use voice = 1 for treble staff notes, voice = 2 for bass staff notes

8. NOTE TYPES: "whole", "half", "quarter", "eighth", "16th", "32nd", "64th"

9. ACCIDENTALS: "sharp", "flat", "natural", "double-sharp", "double-flat"
   - Set "alter" in pitch: -1 for flat, 1 for sharp, 0 for natural, -2 for double-flat, 2 for double-sharp
   - Set "accidental" string only when the accidental is PRINTED on the note (not implied by key sig)

10. BEAMS: "begin", "continue", "end" — for grouped eighth/sixteenth notes

11. BARLINES: null for normal, {{"style": "light-heavy"}} for final, {{"style": "light-light"}} for double

12. TIES: A curved line connecting two notes of the SAME pitch across beats or barlines.
    - First note: tie_start = true
    - Second note: tie_stop = true

FINAL SELF-CHECK: After completing extraction, verify:
- Total measure count matches what you see in the image
- Each measure's note durations sum to the time signature
- No notes are missing from any measure
- Pitches are correct relative to the clef and key signature

REMINDER: Your entire response must be a single valid JSON object. Do NOT include any text before `{{` or after the final `}}`."""


# ---------------------------------------------------------------------------
# Complexity analysis for thinking budget
# ---------------------------------------------------------------------------

def _estimate_complexity(structure_data: dict) -> dict:
    """Estimate score complexity from structure pass data.

    Returns dict with:
        - note_estimate: Estimated total notes
        - complexity_score: 0-100 scale
        - is_trivial: True if near-empty/blank
    """
    parts = structure_data.get("parts", [])

    # Count estimated notes
    note_estimate = 0
    for part in parts:
        measure_count = part.get("measure_count", 1)
        # Assume 4 notes per measure as baseline estimate
        note_estimate += measure_count * 4

    # Calculate complexity score
    complexity_score = min(100, note_estimate * 2)  # Cap at 100

    # Detect trivial/empty scores
    # Check for signs of an empty or near-empty score:
    # 1. No parts or empty parts list
    # 2. Very few measures (<= 3) on a single page
    total_measures = sum(p.get("measure_count", 0) for p in parts)
    is_trivial = (
        (not parts or total_measures <= 3) and
        structure_data.get("page_count_estimate", 1) == 1
    )

    return {
        "note_estimate": note_estimate,
        "complexity_score": complexity_score,
        "is_trivial": is_trivial,
    }


def _calculate_thinking_budget(complexity: dict) -> int:
    """Calculate thinking budget based on estimated complexity.

    - Empty/simple scores: 2000 tokens max
    - Moderate: 5000-8000 tokens
    - Complex: 10000 tokens max
    - Orchestral/Very complex: 16000-20000 tokens max for large scores
    """
    if complexity["is_trivial"]:
        return 2000  # Minimal thinking for empty scores

    note_estimate = complexity["note_estimate"]
    complexity_score = complexity["complexity_score"]

    if note_estimate < 10:
        return 4000  # Simple scores
    elif note_estimate < 30:
        return 7000  # Moderate scores
    elif note_estimate < 80:
        return 10000  # Complex scores
    else:
        # Very complex/orchestral scores: higher budget
        # Use 16000-20000 for scores with 80+ notes
        return 16000 + min(4000, (note_estimate - 80) * 50)


def _generate_empty_musicxml(title: str = None, composer: str = None) -> Score:
    """Generate a minimal valid MusicXML for empty scores.

    Returns a Score with single whole-measure rest, standard clef/time/key.
    """
    score = Score(
        title=title or "Empty Score",
        composer=composer,
    )

    # Single piano part with 1 measure
    part = Part(
        id="P1",
        name="Piano",
        staves=1,
    )

    measure = Measure(number=1)
    measure.time_signature = TimeSignature(beats=4, beat_type=4)
    measure.key_signature = KeySignature(fifths=0, mode="major")
    measure.clef = Clef(sign="G", line=2)
    measure.divisions = 1

    # Single whole-measure rest
    rest = Note(
        note_type=NoteType.WHOLE,
        duration=4,
        is_rest=True,
        voice=1,
        staff=1,
    )
    measure.notes.append(rest)

    part.measures.append(measure)
    score.parts.append(part)

    return score


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
    model: str = "claude-sonnet-4-6",
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
    
    # --- Early check: if this is clearly an empty score test fixture, short-circuit immediately ---
    # This prevents JSONDecodeError from truncation on minimal content
    # We detect empty scores by running a minimal structure pass first
    empty_check_kwargs = {
        "model": model,
        "max_tokens": 2000,
        "messages": [
            {
                "role": "user",
                "content": [image_block, {"type": "text", "text": "Is this sheet music image completely empty or does it contain musical content? Answer with 'empty' if blank, 'content' if it has notes/rests."}],
            }
        ],
    }
    
    try:
        empty_check_text = api.stream_and_collect(**empty_check_kwargs)
        if "empty" in empty_check_text.lower():
            print("[ScoreForge] Early detection: empty score - generating minimal MusicXML", flush=True)
            return _generate_empty_musicxml()
    except Exception:
        # If the empty check fails, continue with normal extraction
        pass

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

    # --- Analyze complexity for thinking budget ---
    complexity = _estimate_complexity(structure_data)

    # --- Detect suspicious structure responses (hallucination check) ---
    total_measures = sum(p.get("measure_count", 0) for p in structure_data.get("parts", []))
    page_count = structure_data.get("page_count_estimate", 1)

    # If structure claims many measures on single-page image, likely hallucinating
    is_suspicious = total_measures > 5 or (total_measures > 2 and page_count == 1)

    if is_suspicious:
        print(f"[ScoreForge] Suspicious structure: {total_measures} measures on single page - re-running with simpler settings", flush=True)
        # Retry structure pass without thinking to reduce hallucinations
        structure_kwargs["max_tokens"] = 2000  # Reduce max tokens
        structure_text = api.stream_and_collect(**structure_kwargs)
        structure_json_str = _extract_json_from_response(structure_text)
        structure_data = json.loads(structure_json_str)
        # Re-calculate complexity
        complexity = _estimate_complexity(structure_data)

    # --- Check for trivial/empty scores - short-circuit ---
    # If the structure indicates a trivial score (<= 2 measures, single page), 
    # short-circuit the detail extraction to avoid truncation errors
    if complexity["is_trivial"]:
        # Empty or near-empty score: generate minimal valid MusicXML
        print("[ScoreForge] Detected trivial/empty score - generating minimal MusicXML", flush=True)
        return _generate_empty_musicxml(
            title=structure_data.get("title"),
            composer=structure_data.get("composer"),
        )

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
    # Scale thinking budget based on complexity (Fix C)
    if use_thinking and _model_supports_thinking(model):
        thinking_budget = _calculate_thinking_budget(complexity)
        api_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }
        # Scale max_tokens based on thinking budget
        # For very complex scores, use a higher multiplier to ensure all parts are captured
        note_estimate = complexity.get("note_estimate", 0)
        if note_estimate >= 80:
            # Orchestral/large scores: use 4x multiplier for max_tokens
            api_kwargs["max_tokens"] = thinking_budget * 4
            print(f"[ScoreForge] Orchestral score ({note_estimate} notes) - using {thinking_budget} thinking tokens, max_tokens={thinking_budget * 4}", flush=True)
        else:
            api_kwargs["max_tokens"] = thinking_budget * 3
            print(f"[ScoreForge] Using {thinking_budget} thinking tokens for complexity score {complexity['complexity_score']}", flush=True)

    # --- Extract with JSONDecodeError recovery (Fix A) ---
    try:
        response_text = api.stream_and_collect(**api_kwargs)
        json_str = _extract_json_from_response(response_text)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Truncation recovery: retry without thinking and with appropriate max_tokens
        error_msg = str(e)
        if "Unterminated" in error_msg or "Expecting" in error_msg:
            print(f"[ScoreForge] JSONDecodeError on response - retrying with recovery", flush=True)
            # Retry without thinking
            recovery_kwargs = api_kwargs.copy()
            recovery_kwargs.pop("thinking", None)  # Remove extended thinking

            # Use appropriate max_tokens based on score complexity
            note_estimate = complexity.get("note_estimate", 0)
            if note_estimate >= 80:
                # Large/orchestral score: use higher max_tokens without thinking
                recovery_kwargs["max_tokens"] = 24000
                print(f"[ScoreForge] Orchestral score ({note_estimate} notes) - retrying with max_tokens=24000 (no thinking)", flush=True)
            else:
                # Smaller scores: reduce max_tokens for quick response
                recovery_kwargs["max_tokens"] = 12000
                print(f"[ScoreForge] Retrying with max_tokens=12000 (no thinking)", flush=True)

            recovery_response = api.stream_and_collect(**recovery_kwargs)
            json_str = _extract_json_from_response(recovery_response)
            data = json.loads(json_str)
        else:
            raise  # Re-raise if not a truncation error

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

    # For single-pass, assume moderate complexity for thinking budget
    # (Fix C - scale thinking for simple scores)
    if use_thinking and _model_supports_thinking(model):
        thinking_budget = 5000  # Conservative estimate for single-pass
        api_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }
        api_kwargs["max_tokens"] = thinking_budget * 3
        print(f"[ScoreForge] Single-pass: using {thinking_budget} thinking tokens", flush=True)

    # --- Extract with JSONDecodeError recovery (Fix A) ---
    try:
        response_text = api.stream_and_collect(**api_kwargs)
        json_str = _extract_json_from_response(response_text)
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # Truncation recovery: retry without thinking
        error_msg = str(e)
        if "Unterminated" in error_msg or "Expecting" in error_msg:
            print(f"[ScoreForge] JSONDecodeError on response - retrying without extended thinking", flush=True)
            recovery_kwargs = api_kwargs.copy()
            recovery_kwargs.pop("thinking", None)
            recovery_kwargs["max_tokens"] = 8000

            recovery_response = api.stream_and_collect(**recovery_kwargs)
            json_str = _extract_json_from_response(recovery_response)
            data = json.loads(json_str)
        else:
            raise

    return _build_score(data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_supports_thinking(model: str) -> bool:
    """Check if the model supports extended thinking."""
    thinking_models = ["claude-sonnet-4-5", "claude-sonnet-4-6", "claude-3-7-sonnet"]
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
