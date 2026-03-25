"""Render MusicXML back to images for visual comparison."""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def render_musicxml_to_image(
    musicxml_path: str,
    output_path: Optional[str] = None,
    dpi: int = 150,
) -> str:
    """Render MusicXML to a PNG image using MuseScore or Verovio.

    Returns the path to the rendered image.
    """
    musicxml_path = Path(musicxml_path)
    if not musicxml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    if output_path is None:
        output_path = str(musicxml_path.with_suffix(".png"))

    # Try MuseScore first (best quality)
    if _has_musescore():
        return _render_with_musescore(str(musicxml_path), output_path, dpi)

    # Try Verovio (lightweight, no GUI needed)
    if _has_verovio():
        return _render_with_verovio(str(musicxml_path), output_path)

    # Fallback: use music21 + lilypond
    if _has_lilypond():
        return _render_with_lilypond(str(musicxml_path), output_path)

    raise RuntimeError(
        "No rendering backend found. Install one of: "
        "musescore4, verovio (npm install verovio), or lilypond"
    )


def _has_musescore() -> bool:
    """Check if MuseScore is installed."""
    for cmd in ["musescore4", "musescore3", "mscore", "MuseScore4"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def _get_musescore_cmd() -> str:
    for cmd in ["musescore4", "musescore3", "mscore", "MuseScore4"]:
        try:
            subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError("MuseScore not found")


def _render_with_musescore(musicxml_path: str, output_path: str, dpi: int) -> str:
    """Render using MuseScore CLI."""
    cmd = _get_musescore_cmd()
    result = subprocess.run(
        [cmd, "-o", output_path, "-r", str(dpi), musicxml_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"MuseScore rendering failed: {result.stderr}")
    return output_path


def _has_verovio() -> bool:
    try:
        subprocess.run(["verovio", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _render_with_verovio(musicxml_path: str, output_path: str) -> str:
    """Render using Verovio CLI."""
    result = subprocess.run(
        ["verovio", musicxml_path, "-o", output_path, "--format", "png"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Verovio rendering failed: {result.stderr}")
    return output_path


def _has_lilypond() -> bool:
    try:
        subprocess.run(["lilypond", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _render_with_lilypond(musicxml_path: str, output_path: str) -> str:
    """Render using music21 -> LilyPond pipeline."""
    import music21
    score = music21.converter.parse(musicxml_path)
    lily = music21.lily.translate.LilypondConverter()
    lily.loadObjectFromScore(score)

    with tempfile.NamedTemporaryFile(suffix=".ly", delete=False) as f:
        ly_path = f.name
        f.write(lily.output.encode())

    try:
        result = subprocess.run(
            ["lilypond", "--png", "-o", output_path.replace(".png", ""), ly_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LilyPond rendering failed: {result.stderr}")
    finally:
        os.unlink(ly_path)

    return output_path


def get_available_renderer() -> str:
    """Return the name of the first available renderer."""
    if _has_musescore():
        return "musescore"
    if _has_verovio():
        return "verovio"
    if _has_lilypond():
        return "lilypond"
    return "none"
