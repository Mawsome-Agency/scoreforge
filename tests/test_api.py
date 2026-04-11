"""Sprint 1 API integration tests.

The extractor is mocked so tests run without hitting the Claude API.
For a real end-to-end run (requires ANTHROPIC_API_KEY), use tests/roundtrip.py.
"""
import io
import re
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# Project root must be on sys.path so api.main can find core.* / models.*
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.main import _jobs, PENDING, app

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def client():
    """Reusable synchronous test client."""
    return TestClient(app)


@pytest.fixture(scope="session")
def blank_png() -> bytes:
    """Minimal valid PNG — 200×80 white pixels."""
    img = Image.new("RGB", (200, 80), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _simple_score():
    """Return a minimal Score containing one C4 quarter note.

    Used as the mock return value for extract_from_image so tests don't
    depend on the Claude API.
    """
    from models.measure import Clef, KeySignature, Measure, TimeSignature
    from models.note import Note, NoteType, Pitch
    from models.score import Part, Score

    score = Score(title="Test Score")
    part = Part(id="P1", name="Piano")

    measure = Measure(number=1)
    measure.divisions = 1
    measure.key_signature = KeySignature(fifths=0, mode="major")
    measure.time_signature = TimeSignature(beats=4, beat_type=4)
    measure.clef = Clef(sign="G", line=2)
    measure.notes.append(
        Note(
            note_type=NoteType.QUARTER,
            duration=1,
            is_rest=False,
            pitch=Pitch(step="C", octave=4, alter=0),
        )
    )

    part.measures.append(measure)
    score.parts.append(part)
    return score


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_convert_requires_file(client):
    """POST /convert without a file body → 422 Unprocessable Entity."""
    resp = client.post("/convert")
    assert resp.status_code == 422


def test_convert_rejects_wrong_content_type(client, blank_png):
    """POST /convert with text/plain → 415 Unsupported Media Type."""
    resp = client.post(
        "/convert",
        files={"file": ("notes.txt", blank_png, "text/plain")},
    )
    assert resp.status_code == 415


def test_job_not_found(client):
    """GET /job/<unknown-id> → 404."""
    resp = client.get("/job/does-not-exist")
    assert resp.status_code == 404


def test_result_job_not_found(client):
    """GET /job/<unknown-id>/result → 404."""
    resp = client.get("/job/does-not-exist/result")
    assert resp.status_code == 404


def test_result_not_ready(client):
    """GET /job/<id>/result when job is still pending → 409 Conflict."""
    fake_id = f"pending-test-{id(test_result_not_ready)}"
    _jobs[fake_id] = {
        "id": fake_id,
        "status": PENDING,
        "filename": "test.png",
        "measure_count": None,
        "part_count": None,
        "musicxml": None,
        "error": None,
    }
    resp = client.get(f"/job/{fake_id}/result")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# End-to-end: upload → poll → download MusicXML
# ---------------------------------------------------------------------------


def test_convert_and_download_musicxml(client, blank_png):
    """Full happy-path: upload a PNG, wait for completion, verify MusicXML.

    The extractor is mocked to return a single C4 quarter note so the test
    is deterministic and runs without any API key.
    """
    mock_score = _simple_score()

    with patch("api.main.extract_from_image", return_value=(mock_score, {"provider": "mock", "model": "mock"})):
        post_resp = client.post(
            "/convert",
            files={"file": ("sheet.png", blank_png, "image/png")},
        )

    assert post_resp.status_code == 202
    body = post_resp.json()
    assert "job_id" in body
    job_id = body["job_id"]

    # Background tasks in Starlette's TestClient run before the response
    # is returned to the caller, but poll briefly in case of timing edge cases.
    final_status = None
    for _ in range(30):
        status_resp = client.get(f"/job/{job_id}")
        assert status_resp.status_code == 200
        final_status = status_resp.json()["status"]
        if final_status in ("completed", "failed"):
            break
        time.sleep(0.1)

    assert final_status == "completed", (
        f"Job ended with status '{final_status}'. "
        f"Error: {client.get(f'/job/{job_id}').json().get('error')}"
    )

    # Status response must NOT leak the raw MusicXML (can be large)
    status_body = client.get(f"/job/{job_id}").json()
    assert "musicxml" not in status_body
    assert status_body["measure_count"] == 1
    assert status_body["part_count"] == 1

    # Download the MusicXML
    result_resp = client.get(f"/job/{job_id}/result")
    assert result_resp.status_code == 200
    assert "musicxml" in result_resp.headers["content-type"]
    assert 'filename="sheet.musicxml"' in result_resp.headers.get(
        "content-disposition", ""
    )

    xml_text = result_resp.text

    # Strip DOCTYPE before parsing (stdlib ET chokes on external DTD refs)
    xml_clean = re.sub(r"<!DOCTYPE[^>]*>", "", xml_text, flags=re.DOTALL)

    from lxml import etree

    root = etree.fromstring(
        xml_clean.encode(),
        parser=etree.XMLParser(resolve_entities=False, load_dtd=False),
    )

    # Root must be a partwise score
    assert "score-partwise" in root.tag, f"Unexpected root tag: {root.tag}"

    # Must contain at least one <note>
    notes = root.findall(".//note")
    assert len(notes) >= 1, "MusicXML output contains no <note> elements"

    # Must contain at least one <pitch>
    pitches = root.findall(".//pitch")
    assert len(pitches) >= 1, "MusicXML output contains no <pitch> elements"

    # The mocked score has C4 — verify step and octave round-trip correctly
    step_el = root.find(".//step")
    octave_el = root.find(".//octave")
    assert step_el is not None and step_el.text == "C", (
        f"Expected step 'C', got '{step_el.text if step_el is not None else None}'"
    )
    assert octave_el is not None and octave_el.text == "4", (
        f"Expected octave '4', got '{octave_el.text if octave_el is not None else None}'"
    )
