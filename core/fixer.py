"""AI-powered MusicXML correction based on comparison results."""
import json

import anthropic


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

    client = anthropic.Anthropic()

    diff_text = json.dumps(differences, indent=2)

    message = client.messages.create(
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
