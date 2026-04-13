"""Validation utilities for MusicXML files."""

from typing import Tuple
from lxml import etree

# Helper to strip namespace from tags for comparison and error messages
def _strip_ns(tag: str) -> str:
    """Return the local tag name without any namespace.

    lxml represents a namespaced tag as "{uri}local". This function removes the
    ``{uri}`` part so callers can work with plain tag names.
    """
    if tag.startswith('{'):
        return tag.split('}', 1)[1]
    return tag


def validate_musicxml_structure(path: str) -> Tuple[bool, str]:
    """Validate MusicXML file structure.
    
    Validates:
    1. Well-formed XML (parseable by lxml.etree.parse())
    2. Root element is <score-partwise>
    3. At least one <part> exists
    4. Each <part> has at least one <measure>
    5. Each <measure> contains at least one child element (note, rest, attributes, etc.)
    6. First <measure> has <attributes><divisions> attribute
    
    Args:
        path: Path to the MusicXML file to validate
        
    Returns:
        Tuple of (is_valid: bool, error_message: str)
        If valid, error_message is empty string.
    """
    try:
        # Check if file is well-formed XML
        tree = etree.parse(path)
        root = tree.getroot()
    except Exception as e:
        return False, f"XML parsing failed: {str(e)}"
    
    # Determine namespace (if any) from the root tag
    ns = ""
    if root.tag.startswith('{'):
        ns = root.tag.split('}')[0] + '}'
    
    # Check root element is score-partwise (ignoring namespace)
    if _strip_ns(root.tag) != "score-partwise":
        return False, f"Root element is '{_strip_ns(root.tag)}', expected 'score-partwise'"
    
    # Find parts using the resolved namespace
    parts = root.findall(f"{ns}part")
    if not parts:
        return False, "No <part> elements found"
    
    # Check each part has at least one measure and each measure has any child
    for i, part in enumerate(parts):
        measures = part.findall(f"{ns}measure")
        if not measures:
            return False, f"Part {i} has no <measure> elements"
        
        for j, measure in enumerate(measures):
            # A valid measure must contain at least one element (note, rest, attributes, direction, etc.)
            if len(list(measure)) == 0:
                # Use the measure number attribute if present for clearer messages
                m_num = measure.get('number', j + 1)
                return False, f"Measure {m_num} in part {i} has no child elements"
    
    # Check first measure of first part has divisions attribute
    first_part = parts[0]
    first_measure = first_part.find(f"{ns}measure")
    if first_measure is None:
        return False, "First part has no measures"
    
    attributes = first_measure.find(f"{ns}attributes")
    if attributes is None:
        return False, "First measure has no <attributes> element"
    
    divisions = attributes.find(f"{ns}divisions")
    if divisions is None:
        return False, "First measure has no <divisions> element in <attributes>"
    
    if divisions.text is None or not divisions.text.strip():
        return False, "First measure has empty <divisions> element"
    
    # Try to parse divisions as integer
    try:
        int(divisions.text.strip())
    except ValueError:
        return False, f"First measure has invalid divisions value: '{divisions.text}'"
    
    return True, ""
