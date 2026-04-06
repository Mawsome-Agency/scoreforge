"""AI-powered MusicXML correction based on comparison results."""
import json

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

FIX_PROMPT_RANGE_ADDENDUM = """
INSTRUMENT RANGE VIOLATIONS DETECTED:
The following pitches are outside the instrument's standard playable range.
These are almost certainly ledger-line miscounts, not real pitches.
For each violation, recount staff positions carefully using the reference points below.

{range_hints}

LEDGER LINE REFERENCE:
  TREBLE CLEF above staff:
    F5 = top staff line  |  G5 = space above top line (NO ledger)
    A5 = 1st ledger line above staff  |  B5 = space above 1st ledger  |  C6 = 2nd ledger
  BASS CLEF near bottom:
    G2 = bottom staff line  |  A2 = 1st space  |  B2 = 2nd line
    F2 = space below bottom line  |  E2 = 1st ledger below staff

  KEY RULE: Accidentals (sharp/flat) change ALTER only — never the staff-position letter.
  G# is step="G" alter=1. Bb is step="B" alter=-1. They do NOT occupy different line/space positions.
"""


def fix_musicxml(
    musicxml_content: str,
    differences: list[dict],
    range_hints: list[str] | None = None,
) -> str:
    """Apply AI-driven fixes to MusicXML based on detected differences.

    Args:
        musicxml_content: Current MusicXML string
        differences: List of difference dicts from comparator

    Returns:
        Corrected MusicXML string
    """
    if not differences and not range_hints:
        return musicxml_content

    diff_text = json.dumps(differences, indent=2)

    # Build prompt — append range violation addendum when violations exist
    prompt = FIX_PROMPT.format(
        differences=diff_text,
        musicxml=musicxml_content,
    )
    if range_hints:
        hints_block = "\n".join(f"  • {h}" for h in range_hints)
        prompt += FIX_PROMPT_RANGE_ADDENDUM.format(range_hints=hints_block)

    message = api.create_message(
        model="claude-sonnet-4-6",
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": prompt,
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
