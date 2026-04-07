"""Render MusicXML back to images for visual comparison."""
import glob
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image


# Verovio CLI path — prefer the known homebrew location
VEROVIO_BIN = "/opt/homebrew/bin/verovio"
RSVG_BIN = "/opt/local/bin/rsvg-convert"


def render_musicxml_to_image(
    musicxml_path: str,
    output_path: Optional[str] = None,
    dpi: int = 150,
    scale: int = 100,
) -> str:
    """Render MusicXML to a PNG image using Verovio.

    Tries CLI first, then falls back to verovio Python package.
    Verovio renders to SVG, then rsvg-convert (or cairosvg) converts to PNG.

    Returns the path to the rendered PNG image.
    """
    musicxml_path = Path(musicxml_path)
    if not musicxml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    if output_path is None:
        output_path = str(musicxml_path.with_suffix(".png"))

    verovio_cli = _find_verovio()
    if verovio_cli is not None:
        # Use CLI path
        svg_path = _render_to_svg(verovio_cli, str(musicxml_path), scale=scale)
        _svg_to_png(svg_path, output_path, dpi=dpi)
        _cleanup_svgs(svg_path)
    else:
        # Fall back to verovio Python package
        _render_with_python_verovio(str(musicxml_path), output_path, scale=scale, dpi=dpi)

    return output_path


def render_musicxml_to_svg(
    musicxml_path: str,
    output_path: Optional[str] = None,
    scale: int = 100,
) -> str:
    """Render MusicXML to SVG using Verovio CLI or Python package.

    Returns the path to the SVG file (first page if multi-page).
    """
    musicxml_path = Path(musicxml_path)
    if not musicxml_path.exists():
        raise FileNotFoundError(f"MusicXML file not found: {musicxml_path}")

    if output_path is None:
        output_path = str(musicxml_path.with_suffix(".svg"))

    verovio_cli = _find_verovio()
    if verovio_cli is not None:
        return _render_to_svg(verovio_cli, str(musicxml_path), output_path, scale=scale)

    # Fall back to Python verovio
    try:
        import verovio as verovio_pkg
        tk = verovio_pkg.toolkit()
        with open(musicxml_path, "r", encoding="utf-8") as f:
            xml_content = f.read()
        tk.loadData(xml_content)
        svg_data = tk.renderToSVG(1)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_data)
        return output_path
    except ImportError:
        raise RuntimeError("Verovio not found. Install via: brew install verovio or pip install verovio")


def _render_with_python_verovio(
    musicxml_path: str,
    output_path: str,
    scale: int = 100,
    dpi: int = 150,
) -> None:
    """Render MusicXML to PNG using the verovio Python package + cairosvg."""
    try:
        import verovio as verovio_pkg
    except ImportError:
        raise RuntimeError("verovio Python package not found. Install via: pip install verovio")

    tk = verovio_pkg.toolkit()
    with open(musicxml_path, "r", encoding="utf-8") as f:
        xml_content = f.read()
    tk.loadData(xml_content)

    # Render all pages and combine vertically
    page_count = tk.getPageCount()
    page_images = []

    for page_num in range(1, page_count + 1):
        svg_data = tk.renderToSVG(page_num)
        fd, tmp_svg = tempfile.mkstemp(suffix=".svg")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(svg_data)
            # Convert SVG -> PNG via cairosvg or rsvg-convert
            fd2, tmp_png = tempfile.mkstemp(suffix=".png")
            os.close(fd2)
            rsvg = _find_rsvg()
            if rsvg:
                result = subprocess.run(
                    [rsvg, tmp_svg, "-o", tmp_png, f"--dpi-x={dpi}", f"--dpi-y={dpi}"],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"rsvg-convert failed: {result.stderr}")
            else:
                import cairosvg
                cairosvg.svg2png(url=tmp_svg, write_to=tmp_png, dpi=dpi)
            page_images.append(Image.open(tmp_png).copy())
        finally:
            try:
                os.unlink(tmp_svg)
            except OSError:
                pass

    if not page_images:
        raise RuntimeError("No pages rendered by verovio.")

    if len(page_images) == 1:
        page_images[0].save(output_path)
    else:
        total_width = max(img.width for img in page_images)
        total_height = sum(img.height for img in page_images)
        combined = Image.new("RGBA", (total_width, total_height), (255, 255, 255, 255))
        y_offset = 0
        for img in page_images:
            combined.paste(img, (0, y_offset))
            y_offset += img.height
        combined.save(output_path)


def _find_verovio() -> Optional[str]:
    """Find the verovio binary."""
    # Check the known homebrew path first
    if os.path.isfile(VEROVIO_BIN) and os.access(VEROVIO_BIN, os.X_OK):
        return VEROVIO_BIN

    # Fallback: search PATH
    try:
        result = subprocess.run(
            ["which", "verovio"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _find_rsvg() -> Optional[str]:
    """Find the rsvg-convert binary."""
    if os.path.isfile(RSVG_BIN) and os.access(RSVG_BIN, os.X_OK):
        return RSVG_BIN

    try:
        result = subprocess.run(
            ["which", "rsvg-convert"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def _render_to_svg(
    verovio_bin: str,
    musicxml_path: str,
    output_path: Optional[str] = None,
    scale: int = 100,
) -> str:
    """Render MusicXML to SVG using verovio CLI.

    Args:
        verovio_bin: Path to verovio binary.
        musicxml_path: Path to input MusicXML file.
        output_path: Path for output SVG. If None, uses a temp file.
        scale: Rendering scale percentage (100 = normal).

    Returns:
        Path to the output SVG file.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".svg")
        os.close(fd)

    cmd = [
        verovio_bin,
        musicxml_path,
        "-f", "xml",          # input format: MusicXML
        "-o", output_path,
        "--all-pages",         # render all pages into a single SVG
        "-s", str(scale),
        "--adjust-page-height",  # fit content height
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Verovio rendering failed (exit {result.returncode}):\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stderr: {result.stderr.strip()}"
        )

    # Verovio may produce multi-page SVGs as name_001.svg, name_002.svg, etc.
    # For --all-pages with a single output file, it typically creates one file.
    # Check if the output exists at the expected path.
    if not os.path.isfile(output_path):
        # Try the _001 variant
        stem = Path(output_path).stem
        parent = Path(output_path).parent
        page1 = parent / f"{stem}_001.svg"
        if page1.exists():
            return str(page1)
        raise RuntimeError(f"Verovio did not produce expected output at: {output_path}")

    return output_path


def _svg_to_png(svg_path: str, png_path: str, dpi: int = 150) -> str:
    """Convert SVG to PNG.

    Uses rsvg-convert if available, otherwise falls back to Pillow.
    Handles multi-page SVGs (stacks them vertically).
    """
    # Collect all SVG pages
    svg_pages = _collect_svg_pages(svg_path)

    rsvg = _find_rsvg()

    page_images = []
    for svg_page in svg_pages:
        if rsvg:
            # Use rsvg-convert for high-quality rendering
            fd, tmp_png = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            result = subprocess.run(
                [rsvg, svg_page, "-o", tmp_png, f"--dpi-x={dpi}", f"--dpi-y={dpi}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"rsvg-convert failed: {result.stderr}")
            page_images.append(Image.open(tmp_png))
        else:
            # Fallback: try cairosvg if installed, otherwise error
            try:
                import cairosvg
                fd, tmp_png = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                cairosvg.svg2png(url=svg_page, write_to=tmp_png, dpi=dpi)
                page_images.append(Image.open(tmp_png))
            except ImportError:
                raise RuntimeError(
                    "No SVG-to-PNG converter found. Install rsvg-convert "
                    "(brew install librsvg) or cairosvg (pip install cairosvg)."
                )

    if not page_images:
        raise RuntimeError("No SVG pages were rendered.")

    # If single page, save directly
    if len(page_images) == 1:
        page_images[0].save(png_path)
    else:
        # Stack pages vertically
        total_width = max(img.width for img in page_images)
        total_height = sum(img.height for img in page_images)
        combined = Image.new("RGBA", (total_width, total_height), (255, 255, 255, 255))
        y_offset = 0
        for img in page_images:
            combined.paste(img, (0, y_offset))
            y_offset += img.height
        combined.save(png_path)

    return png_path


def _collect_svg_pages(svg_path: str) -> list[str]:
    """Collect all SVG page files.

    Verovio may output:
    - Single file: output.svg
    - Multi-page: output_001.svg, output_002.svg, etc.
    """
    if os.path.isfile(svg_path):
        return [svg_path]

    # Check for numbered pages
    stem = Path(svg_path).stem
    parent = Path(svg_path).parent
    pattern = str(parent / f"{stem}_*.svg")
    pages = sorted(glob.glob(pattern))
    if pages:
        return pages

    raise FileNotFoundError(f"SVG not found at {svg_path} or as numbered pages")


def _cleanup_svgs(svg_path: str):
    """Remove temporary SVG files."""
    pages = []
    if os.path.isfile(svg_path):
        pages.append(svg_path)

    stem = Path(svg_path).stem
    parent = Path(svg_path).parent
    pattern = str(parent / f"{stem}_*.svg")
    pages.extend(glob.glob(pattern))

    for page in pages:
        try:
            os.unlink(page)
        except OSError:
            pass


def get_available_renderer() -> str:
    """Return the name of the available renderer."""
    if _find_verovio():
        return "verovio-cli"
    try:
        import verovio  # noqa: F401
        return "verovio-python"
    except ImportError:
        pass
    return "none"
