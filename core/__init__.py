"""Core ScoreForge modules."""

from .extractor import extract_from_image
from .musicxml_builder import build_musicxml
from .renderer import (
    render_musicxml_to_image,
    render_musicxml_to_svg,
    get_available_renderer,
)
from .comparator import compare_images, compare_musicxml_semantic, ai_compare
from .fixer import fix_musicxml, reextract_with_context
from .report import generate_report
from .timesig_extractor import (
    extract_time_signature,
    inject_time_signature_constraint,
    TimeSignatureResult,
    create_cropped_debug_image,
)

__all__ = [
    "extract_from_image",
    "build_musicxml",
    "render_musicxml_to_image",
    "render_musicxml_to_svg",
    "get_available_renderer",
    "compare_images",
    "compare_musicxml_semantic",
    "ai_compare",
    "fix_musicxml",
    "reextract_with_context",
    "extract_time_signature",
    "inject_time_signature_constraint",
    "TimeSignatureResult",
    "create_cropped_debug_image",
]
