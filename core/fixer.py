"""AI-powered MusicXML correction based on comparison results."""
import base64
import json
from pathlib import Path
from typing import Optional

import anthropic


FIX_PROMPT = """You are an expert MusicXML editor. You are looking at the ORIGINAL sheet music image and must fix the MusicXML to match it exactly.

DIFFERENCES FOUND (between ground truth and current extraction):
{differences}

CURRENT MUSICXML:
```xml
{musicxml}
```

RULES:
1. Look at the image carefully. The differences list tells you what's wrong — verify each one against the image.
2. Fix ALL listed issues. For pitch errors, count lines/spaces from the clef reference to get the correct pitch.
3. Maintain valid MusicXML 4.0 structure.
4. Ensure note durations still add up correctly per measure:
   - 4/4 with divisions=1: each measure sums to 4
   - 4/4 with divisions=2: each measure sums to 8
   - 3/4 with divisions=1: each measure sums to 3
   - 6/8 with divisions=2: each measure sums to 6
5. Preserve all existing correct elements.
6. Output the COMPLETE corrected MusicXML document (not just the changes).

PITCH REFERENCE (verify against the image):
- TREBLE CLEF lines bottom to top: E4, G4, B4, D5, F5
- TREBLE CLEF spaces bottom to top: F4, A4, C5, E5
- BASS CLEF lines bottom to top: G2, B2, D3, F3, A3
- BASS CLEF spaces bottom to top: A2, C3, E3, G3
- Middle C = C4 (ledger line below treble, above bass)
- Key signature accidentals apply to ALL octaves unless cancelled by a natural.

Output ONLY the corrected XML, wrapped in ```xml ... ``` tags. No explanations."""


FIX_PROMPT_WITH_IMAGE = """You are an expert MusicXML editor. You are looking at the ORIGINAL sheet music image and must fix the MusicXML to match it exactly.

DIFFERENCES FOUND (between ground truth and current extraction):
{differences}

CURRENT MUSICXML:
```xml
{musicxml}
```

INSTRUCTIONS:
1. Look at the ORIGINAL IMAGE above carefully.
2. For each difference listed, look at the specific measure in the image and determine the correct value.
3. For pitch errors: count lines/spaces from the clef. Treble clef bottom line = E4. Bass clef bottom line = G2.
4. For duration errors: check the note head (filled/open) and stem flags/beams.
5. For missing/extra notes: carefully count all notes in that measure of the image.
6. After fixing, verify each measure's durations sum correctly for the time signature.

DURATION MATH:
- divisions=1: whole=4, half=2, quarter=1
- divisions=2: whole=8, half=4, quarter=2, eighth=1
- Measure total = (beats / beat_type) * 4 * divisions

PITCH REFERENCE:
- TREBLE CLEF lines bottom to top: E4, G4, B4, D5, F5
- TREBLE CLEF spaces bottom to top: F4, A4, C5, E5
- BASS CLEF lines bottom to top: G2, B2, D3, F3, A3
- BASS CLEF spaces bottom to top: A2, C3, E3, G3
- Middle C = C4. Key sig accidentals apply to ALL octaves.

Output ONLY the corrected XML, wrapped in ```xml ... ``` tags. No explanations."""


REEXTRACT_WITH_CONTEXT_PROMPT = """You are an expert music notation reader. You previously attempted to extract this sheet music but made errors. Here is what went wrong:

ERRORS FROM PREVIOUS ATTEMPT:
{error_summary}

PREVIOUS SCORES (iteration trend):
{score_trend}

Now re-extract the ENTIRE score from scratch, being EXTRA careful about the specific issues listed above.

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

CRITICAL — PAY SPECIAL ATTENTION TO:
{focus_areas}

PITCH REFERENCE:
- TREBLE CLEF lines bottom to top: E4, G4, B4, D5, F5
- TREBLE CLEF spaces bottom to top: F4, A4, C5, E5
- BASS CLEF lines bottom to top: G2, B2, D3, F3, A3
- BASS CLEF spaces bottom to top: A2, C3, E3, G3
- Middle C = C4

DURATION MATH:
- divisions=1: whole=4, half=2, quarter=1
- divisions=2: whole=8, half=4, quarter=2, eighth=1
- Each measure must sum to (beats / beat_type) * 4 * divisions
- VERIFY each measure's duration sum before moving on.

After extraction, double-check every pitch by counting from the clef reference line."""


def encode_image(path: str) -> tuple[str, str]:
    """Encode an image to base64."""
    p = Path(path)
    suffix = p.suffix.lower()
    media_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
        suffix, "image/png"
    )
    with open(p, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode()
    return data, media_type


def fix_musicxml(
    musicxml_content: str,
    differences: list[dict],
    image_path: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250929",
) -> str:
    """Apply AI-driven fixes to MusicXML based on detected differences.

    Args:
        musicxml_content: Current MusicXML string
        differences: List of difference dicts from comparator
        image_path: Optional path to original sheet music image for visual verification
        model: Claude model to use for fixing

    Returns:
        Corrected MusicXML string
    """
    if not differences:
        return musicxml_content

    client = anthropic.Anthropic()
    diff_text = json.dumps(differences, indent=2)

    if image_path and Path(image_path).exists():
        # Image-aware fixing — much more accurate
        img_data, media_type = encode_image(image_path)
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
            {"type": "text", "text": FIX_PROMPT_WITH_IMAGE.format(
                differences=diff_text,
                musicxml=musicxml_content,
            )},
        ]
    else:
        # Text-only fixing (fallback)
        content = FIX_PROMPT.format(
            differences=diff_text,
            musicxml=musicxml_content,
        )

    message = client.messages.create(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text

    # Extract XML from response
    xml_str = response_text
    if "```xml" in xml_str:
        xml_str = xml_str.split("```xml")[1].split("```")[0]
    elif "```" in xml_str:
        xml_str = xml_str.split("```")[1].split("```")[0]

    return xml_str.strip()


def reextract_with_context(
    image_path: str,
    previous_errors: list[dict],
    score_trend: list[float],
    model: str = "claude-sonnet-4-5-20250929",
    use_thinking: bool = True,
) -> str:
    """Re-extract from scratch with knowledge of previous mistakes.

    This is the nuclear option — when iterative fixes plateau, we start
    fresh but armed with specific knowledge of what went wrong.

    Returns raw JSON string (caller must parse and build Score).
    """
    client = anthropic.Anthropic()
    img_data, media_type = encode_image(image_path)

    # Build focused error summary
    error_counts = {}
    error_details = []
    for err in previous_errors:
        etype = err.get("type", "unknown")
        error_counts[etype] = error_counts.get(etype, 0) + 1
        if len(error_details) < 10:  # Cap detail examples
            error_details.append(f"- Measure {err.get('measure', '?')}: {err.get('description', err.get('fix', str(err)))}")

    error_summary = "Error counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(error_counts.items(), key=lambda x: -x[1]))
    if error_details:
        error_summary += "\n\nSpecific examples:\n" + "\n".join(error_details)

    # Build focus areas from most common errors
    focus_areas = []
    if error_counts.get("wrong_pitch", 0) > 0:
        focus_areas.append("- PITCH ACCURACY: You made pitch errors before. Count EVERY note from the clef reference line. Double-check each one.")
    if error_counts.get("wrong_duration", 0) > 0:
        focus_areas.append("- DURATION ACCURACY: You made duration errors. Verify note heads (filled=quarter/shorter, open=half/whole) and flags/beams.")
    if error_counts.get("missing_note", 0) > 0:
        focus_areas.append("- MISSING NOTES: You missed notes before. Count every note and rest in every measure carefully.")
    if error_counts.get("extra_note", 0) > 0:
        focus_areas.append("- EXTRA NOTES: You added notes that aren't there. Only extract what you actually see.")
    if error_counts.get("wrong_key", 0) > 0:
        focus_areas.append("- KEY SIGNATURE: Count sharps/flats carefully. Remember the order: sharps=FCGDAEB, flats=BEADGCF")
    if error_counts.get("wrong_time", 0) > 0:
        focus_areas.append("- TIME SIGNATURE: Read the time signature numbers carefully.")
    if not focus_areas:
        focus_areas.append("- General accuracy across all dimensions")

    prompt_text = REEXTRACT_WITH_CONTEXT_PROMPT.format(
        error_summary=error_summary,
        score_trend=json.dumps(score_trend),
        focus_areas="\n".join(focus_areas),
    )

    api_kwargs = {
        "model": model,
        "max_tokens": 16000,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ],
    }

    # Use extended thinking if supported
    if use_thinking and "sonnet-4-5" in model:
        api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": 10000}
        api_kwargs["max_tokens"] = 32000

    # Stream to avoid timeouts
    with client.messages.stream(**api_kwargs) as stream:
        message = stream.get_final_message()

    # Extract text (skip thinking blocks)
    response_text = ""
    for block in message.content:
        if hasattr(block, "type") and block.type == "text":
            response_text = block.text
            break

    # Extract JSON
    if "```json" in response_text:
        return response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        return response_text.split("```")[1].split("```")[0].strip()
    return response_text.strip()
