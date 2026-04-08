"""AI-powered MusicXML correction based on comparison results."""
import base64
import json
from pathlib import Path

from core import api


FIX_PROMPT = """You are an expert MusicXML editor. Given a MusicXML document and a list of differences found between the original sheet music and the rendered output, produce a corrected MusicXML document.

DIFFERENCES FOUND:
{differences}

CURRENT MUSICXML:
```xml
{musicxml}
```

RULES:
1. Fix ONLY the issues listed in the differences. Do not change anything else.
2. Maintain valid MusicXML 4.0 structure.
3. Ensure note durations still add up correctly per measure.
4. Preserve all existing correct elements.
5. Output the COMPLETE corrected MusicXML document (not just the changes).

Output ONLY the corrected XML, wrapped in ```xml ... ``` tags. No explanations."""

REEXTRACT_PROMPT = """You are an expert music notation reader. Re-extract this sheet music image with focused context.

PREVIOUS EXTRACTION ATTEMPTS HAD THESE ISSUES:
{error_context}

SCORE ACCURACY TREND: {score_trend}

Your task: Extract the music notation PRECISELY, paying special attention to fixing the errors listed above.
Do NOT repeat the mistakes from previous attempts.

Output ONLY a valid JSON object with this structure (no markdown, no explanation):
{{
  "title": "string or null",
  "composer": "string or null",
  "parts": [
    {{
      "id": "P1",
      "name": "string",
      "staves": 1,
      "measures": [
        {{
          "number": 1,
          "time_signature": {{"beats": 4, "beat_type": 4}},
          "key_signature": {{"fifths": 0, "mode": "major"}},
          "clef": {{"sign": "G", "line": 2}},
          "divisions": 4,
          "notes": [
            {{
              "type": "note",
              "pitch": {{"step": "C", "octave": 4, "alter": 0}},
              "duration": 4,
              "note_type": "quarter",
              "is_chord": false,
              "voice": 1
            }}
          ]
        }}
      ]
    }}
  ]
}}

CRITICAL: Fix the specific errors mentioned. Output ONLY valid JSON starting with {{."""


def fix_musicxml(musicxml_content: str, differences: list[dict]) -> str:
    """Apply AI-driven fixes to MusicXML based on detected differences.

    Args:
        musicxml_content: Current MusicXML string
        differences: List of difference dicts from comparator

    Returns:
        Corrected MusicXML string
    """
    if not differences:
        return musicxml_content



    diff_text = json.dumps(differences, indent=2)

    message = api.create_message(
        model="claude-sonnet-4-5-20250929",
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": FIX_PROMPT.format(
                    differences=diff_text,
                    musicxml=musicxml_content,
                ),
            }
        ],
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
    errors: list[dict],
    score_trend: list[float],
    model: str = "claude-sonnet-4-5-20250929",
    use_thinking: bool = False,
) -> str:
    """Re-extract music notation from image using previous errors as context.

    Claude sees the original image AND a list of what went wrong before,
    enabling it to focus on problematic areas for improved accuracy.

    Args:
        image_path: Path to the original sheet music image.
        errors: List of error dicts from previous iterations
                (each with 'measure' and 'description' keys, or diff region dicts).
        score_trend: Accuracy scores from previous iterations e.g. [42, 67, 80].
        model: Claude model to use.
        use_thinking: Whether to enable extended thinking (increases latency/cost).

    Returns:
        JSON string of the re-extracted score structure.
    """
    # Build human-readable error context (limit to 20 most significant)
    error_lines = []
    for e in errors[:20]:
        if isinstance(e, dict):
            if "measure" in e and "description" in e:
                error_lines.append(f"  - Measure {e['measure']}: {e['description']}")
            elif "type" in e and "fix" in e:
                error_lines.append(f"  - {e['type']}: {e.get('fix', '')}")
            elif "severity" in e:
                loc = f"({e.get('x', '?')},{e.get('y', '?')})"
                error_lines.append(f"  - Visual diff region at {loc}, severity={e['severity']}")
            else:
                error_lines.append(f"  - {json.dumps(e)}")

    error_context = "\n".join(error_lines) if error_lines else "  - No specific errors recorded; general quality issues."
    trend_str = " → ".join(f"{s:.1f}%" for s in score_trend) if score_trend else "no prior scores"

    # Encode image
    image_path = Path(image_path)
    suffix = image_path.suffix.lower().lstrip(".")
    media_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
    media_type = media_map.get(suffix, "image/png")
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode()

    content = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_data},
        },
        {
            "type": "text",
            "text": REEXTRACT_PROMPT.format(
                error_context=error_context,
                score_trend=trend_str,
            ),
        },
    ]

    kwargs: dict = {
        "model": model,
        "max_tokens": 32000,
        "messages": [{"role": "user", "content": content}],
    }

    if use_thinking:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": 8000}

    message = api.create_message(**kwargs)
    return message.content[0].text if message.content else "{}"
