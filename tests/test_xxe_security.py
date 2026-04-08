"""Security test: XXE (XML External Entity) injection protection.

Verifies that _parse_musicxml() does NOT resolve external entities,
preventing file read, SSRF, and Billion Laughs attacks via crafted MusicXML.
"""
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"
XXE_PAYLOAD = FIXTURES / "xxe_payload.musicxml"


def test_xxe_payload_fixture_exists():
    """Fixture file must be present for the security test to be meaningful."""
    assert XXE_PAYLOAD.exists(), f"XXE payload fixture not found at {XXE_PAYLOAD}"


def test_parse_musicxml_rejects_or_sanitises_xxe():
    """_parse_musicxml() must not leak /etc/passwd contents via XXE."""
    from core.comparator import _parse_musicxml

    # The call should either raise an XMLSyntaxError (entity undefined/blocked)
    # or return a result where no element text contains passwd-style content.
    try:
        result = _parse_musicxml(str(XXE_PAYLOAD))
        # If parsing succeeded, make sure no resolved entity content leaked.
        # /etc/passwd always contains "root:" — that string must not appear.
        result_str = str(result)
        assert "root:" not in result_str, (
            "XXE vulnerability: /etc/passwd content appeared in parsed output"
        )
    except etree.XMLSyntaxError:
        # lxml raised an error because the entity was blocked — this is the
        # preferred secure outcome (entity reference to undefined entity).
        pass


def test_safe_xml_parser_constant_exists():
    """SAFE_XML_PARSER module constant must be defined in comparator."""
    from core import comparator
    assert hasattr(comparator, "SAFE_XML_PARSER"), (
        "SAFE_XML_PARSER constant is missing from core/comparator.py"
    )
    parser = comparator.SAFE_XML_PARSER
    assert isinstance(parser, etree.XMLParser), (
        "SAFE_XML_PARSER must be an lxml.etree.XMLParser instance"
    )


def test_billion_laughs_does_not_exhaust_memory():
    """Recursive entity expansion (Billion Laughs) must be blocked."""
    billion_laughs = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<score-partwise>&lol4;</score-partwise>"""

    import tempfile, os
    from core import comparator

    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as f:
        f.write(billion_laughs)
        tmp_path = f.name

    try:
        try:
            result = comparator._parse_musicxml(tmp_path)
            # If it parsed, entities must not have been expanded
            assert "lol" * 1000 not in str(result), (
                "Billion Laughs entity expansion was NOT blocked"
            )
        except etree.XMLSyntaxError:
            pass  # Blocked — correct
    finally:
        os.unlink(tmp_path)
