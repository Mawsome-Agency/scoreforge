"""Vision-based music extraction using Claude CLI (no API key needed)."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from models.score import Score, Part
from models.measure import Measure, KeySignature, TimeSignature, Clef, Barline
from models.note import Note, NoteType, Pitch, Accidental


# Import prompts and model-building from the main extractor
from core.extractor import (
    STRUCTURE_PROMPT,
    DETAIL_PROMPT,
    _build_score,
    _extract_json_from_response,
)


def extract_from_image_cli(
    image_path: str,
    model: str = "sonnet",
    two_pass: bool = True,
) -> Score:
    """Extract musical score from an image using Claude CLI.

    Uses `claude` CLI with --print flag for non-interactive output.
    No API key needed — uses CLI authentication.
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if two_pass:
        return _extract_two_pass_cli(str(image_path), model)
    else:
        return _extract_single_pass_cli(str(image_path), model)


def _run_claude_cli(prompt: str, image_path: Optional[str] = None, model: str = "sonnet") -> str:
    """Run Claude CLI and return the text response.

    Args:
        prompt: The text prompt to send.
        image_path: Optional path to an image file to include.
        model: Model name for CLI (sonnet, opus, haiku).

    Returns:
        The text response from Claude.
    """
    # Build the prompt with image reference
    if image_path:
        full_prompt = f"Look at this image: {image_path}\n\n{prompt}"
    else:
        full_prompt = prompt

    # Write prompt to temp file to avoid shell escaping issues
    fd, prompt_file = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(prompt_file, "w") as f:
        f.write(full_prompt)

    try:
        cmd = [
            "claude",
            "--print",           # non-interactive, outputs response as text
            "--model", model,
            "--max-turns", "1",
        ]

        # Pipe the prompt via stdin
        result = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "CLAUDE_CODE_ENTRYPOINT": "cli"},
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude CLI failed (exit {result.returncode}):\n"
                f"stderr: {result.stderr[:500]}"
            )

        return result.stdout.strip()
    finally:
        os.unlink(prompt_file)


def _extract_two_pass_cli(image_path: str, model: str) -> Score:
    """Two-pass extraction using Claude CLI."""

    # Pass 1: Structure
    structure_response = _run_claude_cli(
        STRUCTURE_PROMPT,
        image_path=image_path,
        model=model,
    )

    structure_json_str = _extract_json_from_response(structure_response)
    structure_data = json.loads(structure_json_str)

    # Pass 2: Detailed notes
    detail_prompt = DETAIL_PROMPT.format(
        structure_json=json.dumps(structure_data, indent=2)
    )

    detail_response = _run_claude_cli(
        detail_prompt,
        image_path=image_path,
        model=model,
    )

    json_str = _extract_json_from_response(detail_response)
    data = json.loads(json_str)

    return _build_score(data)


def _extract_single_pass_cli(image_path: str, model: str) -> Score:
    """Single-pass extraction using Claude CLI."""
    placeholder = {"note": "Structure not pre-analyzed. Extract everything from the image."}
    detail_prompt = DETAIL_PROMPT.format(
        structure_json=json.dumps(placeholder, indent=2)
    )

    response = _run_claude_cli(
        detail_prompt,
        image_path=image_path,
        model=model,
    )

    json_str = _extract_json_from_response(response)
    data = json.loads(json_str)

    return _build_score(data)
