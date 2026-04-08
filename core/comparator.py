"""Comparison tools: visual (pixel) comparison and semantic MusicXML comparison."""
import base64
import json
from pathlib import Path
from typing import Optional

import numpy as np
from lxml import etree
from PIL import Image
import imagehash
from core import api


# ============================================================================
# Visual (pixel/hash) comparison
# ============================================================================

def compare_images(original_path: str, rendered_path: str) -> dict:
    """Compare original sheet music with re-rendered version.

    Returns a dict with:
    - match_score: 0-100 (100 = perfect match)
    - phash_distance: perceptual hash distance (0 = identical)
    - pixel_diff_pct: percentage of pixels that differ
    - diff_regions: list of bounding boxes where diffs occur
    """
    orig = Image.open(original_path).convert("L")  # grayscale
    rend = Image.open(rendered_path).convert("L")

    # Resize rendered to match original dimensions for comparison
    if orig.size != rend.size:
        rend = rend.resize(orig.size, Image.LANCZOS)

    # Perceptual hash comparison
    orig_hash = imagehash.phash(orig, hash_size=16)
    rend_hash = imagehash.phash(rend, hash_size=16)
    phash_distance = orig_hash - rend_hash

    # Pixel-level comparison
    orig_arr = np.array(orig, dtype=np.float32) / 255.0
    rend_arr = np.array(rend, dtype=np.float32) / 255.0
    diff = np.abs(orig_arr - rend_arr)
    pixel_diff_pct = (diff > 0.3).mean() * 100  # threshold at 30% brightness diff

    # Find diff regions (simple grid-based)
    diff_regions = _find_diff_regions(diff, threshold=0.3)

    # Composite match score
    phash_score = max(0, 100 - phash_distance * 2)
    pixel_score = max(0, 100 - pixel_diff_pct * 2)
    match_score = int(phash_score * 0.4 + pixel_score * 0.6)

    return {
        "match_score": match_score,
        "phash_distance": phash_distance,
        "pixel_diff_pct": round(pixel_diff_pct, 2),
        "diff_regions": diff_regions,
        "is_perfect": match_score >= 95,
    }


def _find_diff_regions(diff: np.ndarray, threshold: float = 0.3) -> list[dict]:
    """Find rectangular regions where differences exceed threshold."""
    binary = (diff > threshold).astype(np.uint8)
    h, w = binary.shape

    cell_h = max(1, h // 10)
    cell_w = max(1, w // 10)
    regions = []

    for row in range(0, h, cell_h):
        for col in range(0, w, cell_w):
            cell = binary[row:row + cell_h, col:col + cell_w]
            if cell.mean() > 0.05:
                regions.append({
                    "x": col,
                    "y": row,
                    "width": min(cell_w, w - col),
                    "height": min(cell_h, h - row),
                    "severity": round(float(cell.mean()), 3),
                })

    return regions


# ============================================================================
# AI-based visual comparison
# ============================================================================

def ai_compare(original_path: str, rendered_path: str) -> dict:
    """Use Claude Vision to compare original and rendered sheet music."""


    def encode(path):
        suffix = Path(path).suffix.lower()
        media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
            suffix.lstrip("."), "image/png"
        )
        with open(path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode(), media_type

    orig_data, orig_type = encode(original_path)
    rend_data, rend_type = encode(rendered_path)

    message = api.create_message(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Image 1 is the ORIGINAL sheet music. Image 2 is a re-rendered version from extracted MusicXML."},
                    {"type": "image", "source": {"type": "base64", "media_type": orig_type, "data": orig_data}},
                    {"type": "image", "source": {"type": "base64", "media_type": rend_type, "data": rend_data}},
                    {"type": "text", "text": """Compare these two images measure by measure. For EACH difference found, output a JSON array:

[
  {
    "measure": 1,
    "type": "missing_note|wrong_pitch|wrong_duration|wrong_key|wrong_time|missing_rest|extra_note|wrong_accidental|missing_dynamic|missing_slur|missing_tie|other",
    "description": "Detailed description of the difference",
    "severity": "critical|major|minor",
    "fix": "Specific fix instruction for the MusicXML"
  }
]

If the images match perfectly, return an empty array: []

Be EXTREMELY thorough. Check:
- Every note pitch and duration
- Key and time signatures
- Accidentals
- Rests
- Ties, slurs, beams
- Dynamics and articulations
- Clef changes
- Barlines (repeats, double bars)
- Lyrics if present"""},
                ],
            }
        ],
    )

    response_text = message.content[0].text

    json_str = response_text
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]

    try:
        differences = json.loads(json_str.strip())
    except json.JSONDecodeError:
        differences = [{"type": "parse_error", "description": response_text, "severity": "critical"}]

    return {
        "differences": differences,
        "diff_count": len(differences),
        "is_perfect": len(differences) == 0,
        "critical_count": sum(1 for d in differences if d.get("severity") == "critical"),
        "major_count": sum(1 for d in differences if d.get("severity") == "major"),
        "minor_count": sum(1 for d in differences if d.get("severity") == "minor"),
    }


# ============================================================================
# Semantic MusicXML comparison
# ============================================================================

def compare_musicxml_semantic(
    ground_truth_path: str,
    extracted_path: str,
) -> dict:
    """Semantically compare two MusicXML files note-by-note and measure-by-measure.

    Args:
        ground_truth_path: Path to the known-correct MusicXML file.
        extracted_path: Path to the extracted/reconstructed MusicXML file.

    Returns:
        Structured comparison result with per-measure and per-note diffs,
        plus aggregate accuracy scores.
    """
    gt_data = _parse_musicxml(ground_truth_path)
    ex_data = _parse_musicxml(extracted_path)

    result = {
        "part_count_match": gt_data["part_count"] == ex_data["part_count"],
        "gt_part_count": gt_data["part_count"],
        "ex_part_count": ex_data["part_count"],
        "part_diffs": [],
        "scores": {},
    }

    # Compare parts pairwise
    total_notes_correct = 0
    total_notes = 0
    total_pitches_correct = 0
    total_pitches = 0
    total_durations_correct = 0
    total_measures_correct = 0
    total_measures = 0
    total_key_correct = 0
    total_key_checks = 0
    total_time_correct = 0
    total_time_checks = 0

    min_parts = min(gt_data["part_count"], ex_data["part_count"])
    for pi in range(min_parts):
        gt_part = gt_data["parts"][pi]
        ex_part = ex_data["parts"][pi]

        part_diff = {
            "part_index": pi,
            "gt_name": gt_part.get("name", ""),
            "ex_name": ex_part.get("name", ""),
            "gt_measure_count": len(gt_part["measures"]),
            "ex_measure_count": len(ex_part["measures"]),
            "measure_diffs": [],
        }

        min_measures = min(len(gt_part["measures"]), len(ex_part["measures"]))
        for mi in range(min_measures):
            gt_m = gt_part["measures"][mi]
            ex_m = ex_part["measures"][mi]

            m_diff = _compare_measures(gt_m, ex_m, mi + 1)
            part_diff["measure_diffs"].append(m_diff)

            total_measures += 1
            if m_diff["is_perfect"]:
                total_measures_correct += 1

            total_notes += m_diff["gt_note_count"]
            total_notes_correct += m_diff["notes_matched"]
            total_pitches += m_diff["gt_pitch_count"]
            total_pitches_correct += m_diff["pitches_correct"]
            total_durations_correct += m_diff["durations_correct"]

            if m_diff["key_checked"]:
                total_key_checks += 1
                if m_diff["key_correct"]:
                    total_key_correct += 1

            if m_diff["time_checked"]:
                total_time_checks += 1
                if m_diff["time_correct"]:
                    total_time_correct += 1

        # Flag missing/extra measures
        if len(gt_part["measures"]) > len(ex_part["measures"]):
            for mi in range(len(ex_part["measures"]), len(gt_part["measures"])):
                part_diff["measure_diffs"].append({
                    "measure_number": mi + 1,
                    "error": "missing_measure",
                    "is_perfect": False,
                    "gt_note_count": len(gt_part["measures"][mi]["notes"]),
                    "notes_matched": 0,
                    "pitches_correct": 0,
                    "durations_correct": 0,
                    "gt_pitch_count": 0,
                    "key_checked": False, "key_correct": False,
                    "time_checked": False, "time_correct": False,
                    "diffs": [{"type": "missing_measure", "description": f"Measure {mi + 1} missing from extraction"}],
                })
                total_measures += 1
                total_notes += len(gt_part["measures"][mi]["notes"])

        elif len(ex_part["measures"]) > len(gt_part["measures"]):
            for mi in range(len(gt_part["measures"]), len(ex_part["measures"])):
                part_diff["measure_diffs"].append({
                    "measure_number": mi + 1,
                    "error": "extra_measure",
                    "is_perfect": False,
                    "gt_note_count": 0,
                    "notes_matched": 0,
                    "pitches_correct": 0,
                    "durations_correct": 0,
                    "gt_pitch_count": 0,
                    "key_checked": False, "key_correct": False,
                    "time_checked": False, "time_correct": False,
                    "diffs": [{"type": "extra_measure", "description": f"Extra measure {mi + 1} in extraction"}],
                })

        result["part_diffs"].append(part_diff)

    # Aggregate scores (0-100)
    result["scores"] = {
        "note_accuracy": _pct(total_notes_correct, total_notes),
        "pitch_accuracy": _pct(total_pitches_correct, total_pitches),
        "rhythm_accuracy": _pct(total_durations_correct, total_notes),
        "measure_accuracy": _pct(total_measures_correct, total_measures),
        "key_sig_accuracy": _pct(total_key_correct, total_key_checks),
        "time_sig_accuracy": _pct(total_time_correct, total_time_checks),
        "overall": _pct(
            total_pitches_correct + total_durations_correct + total_key_correct + total_time_correct,
            total_pitches + total_notes + total_key_checks + total_time_checks,
        ),
    }

    result["total_notes_gt"] = total_notes
    result["total_notes_matched"] = total_notes_correct
    result["is_perfect"] = (
        total_notes_correct == total_notes
        and total_pitches_correct == total_pitches
        and total_durations_correct == total_notes
        and result["part_count_match"]
    )

    return result


# ---------------------------------------------------------------------------
# Internal: MusicXML parsing for semantic comparison
# ---------------------------------------------------------------------------

def _parse_musicxml(path: str) -> dict:
    """Parse a MusicXML file into a simplified dict for comparison."""
    tree = etree.parse(path)
    root = tree.getroot()

    # Handle namespace if present
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    parts = root.findall(f"{ns}part")

    result = {
        "part_count": len(parts),
        "parts": [],
    }

    part_list = root.find(f"{ns}part-list")
    part_names = {}
    if part_list is not None:
        for sp in part_list.findall(f"{ns}score-part"):
            pid = sp.get("id", "")
            name_el = sp.find(f"{ns}part-name")
            part_names[pid] = name_el.text if name_el is not None and name_el.text else pid

    for part_el in parts:
        pid = part_el.get("id", "")
        part_data = {
            "id": pid,
            "name": part_names.get(pid, pid),
            "measures": [],
        }

        current_divisions = 1
        current_key = None
        current_time = None

        for measure_el in part_el.findall(f"{ns}measure"):
            m_num = measure_el.get("number", "0")

            # Parse attributes
            attr_el = measure_el.find(f"{ns}attributes")
            if attr_el is not None:
                div_el = attr_el.find(f"{ns}divisions")
                if div_el is not None and div_el.text:
                    current_divisions = int(div_el.text)

                key_el = attr_el.find(f"{ns}key")
                if key_el is not None:
                    fifths_el = key_el.find(f"{ns}fifths")
                    mode_el = key_el.find(f"{ns}mode")
                    current_key = {
                        "fifths": int(fifths_el.text) if fifths_el is not None and fifths_el.text else 0,
                        "mode": mode_el.text if mode_el is not None and mode_el.text else "major",
                    }

                time_el = attr_el.find(f"{ns}time")
                if time_el is not None:
                    beats_el = time_el.find(f"{ns}beats")
                    bt_el = time_el.find(f"{ns}beat-type")
                    current_time = {
                        "beats": int(beats_el.text) if beats_el is not None and beats_el.text else 4,
                        "beat_type": int(bt_el.text) if bt_el is not None and bt_el.text else 4,
                    }

            # Parse notes
            notes = []
            for note_el in measure_el.findall(f"{ns}note"):
                note_data = _parse_note_element(note_el, ns, current_divisions)
                if note_data is not None:
                    notes.append(note_data)

            m_data = {
                "number": int(m_num) if m_num.isdigit() else 0,
                "divisions": current_divisions,
                "key": dict(current_key) if current_key else None,
                "time": dict(current_time) if current_time else None,
                "notes": notes,
            }
            part_data["measures"].append(m_data)

        result["parts"].append(part_data)

    return result


def _parse_note_element(note_el, ns: str, divisions: int) -> Optional[dict]:
    """Parse a single <note> element into a comparison dict."""
    # Skip forward/backup elements
    is_rest = note_el.find(f"{ns}rest") is not None
    is_chord = note_el.find(f"{ns}chord") is not None
    is_grace = note_el.find(f"{ns}grace") is not None

    # Parse pitch
    pitch = None
    pitch_el = note_el.find(f"{ns}pitch")
    if pitch_el is not None:
        step_el = pitch_el.find(f"{ns}step")
        oct_el = pitch_el.find(f"{ns}octave")
        alter_el = pitch_el.find(f"{ns}alter")
        pitch = {
            "step": step_el.text if step_el is not None else "C",
            "octave": int(oct_el.text) if oct_el is not None and oct_el.text else 4,
            "alter": int(float(alter_el.text)) if alter_el is not None and alter_el.text else 0,
        }

    # Parse duration
    dur_el = note_el.find(f"{ns}duration")
    duration = int(dur_el.text) if dur_el is not None and dur_el.text else divisions

    # Normalize duration to quarter-note units for cross-divisions comparison.
    # MusicXML allows any divisions value (music21 uses 10080, hand-crafted
    # fixtures often use 1). A quarter note at divisions=10080 has duration=10080;
    # at divisions=1 it has duration=1. Both are semantically one quarter note.
    # Comparing raw integers always fails when divisions differ, so we store
    # a normalized float (quarter_note_units = duration / divisions).
    duration_normalized = duration / divisions if divisions > 0 else float(duration)

    # Parse type
    type_el = note_el.find(f"{ns}type")
    note_type = type_el.text if type_el is not None else None

    # Parse dots
    dot_count = len(note_el.findall(f"{ns}dot"))

    # Parse voice
    voice_el = note_el.find(f"{ns}voice")
    voice = int(voice_el.text) if voice_el is not None and voice_el.text else 1

    # Parse staff
    staff_el = note_el.find(f"{ns}staff")
    staff = int(staff_el.text) if staff_el is not None and staff_el.text else 1

    # Parse ties
    tie_start = False
    tie_stop = False
    for tie_el in note_el.findall(f"{ns}tie"):
        if tie_el.get("type") == "start":
            tie_start = True
        elif tie_el.get("type") == "stop":
            tie_stop = True

    return {
        "is_rest": is_rest,
        "is_chord": is_chord,
        "is_grace": is_grace,
        "pitch": pitch,
        "duration": duration,
        "duration_normalized": duration_normalized,
        "type": note_type,
        "dot_count": dot_count,
        "voice": voice,
        "staff": staff,
        "tie_start": tie_start,
        "tie_stop": tie_stop,
    }


# ---------------------------------------------------------------------------
# Internal: Measure-level comparison
# ---------------------------------------------------------------------------

def _compare_measures(gt_m: dict, ex_m: dict, measure_num: int) -> dict:
    """Compare two parsed measures and return structured diff."""
    diffs = []
    key_checked = gt_m.get("key") is not None
    key_correct = False
    time_checked = gt_m.get("time") is not None
    time_correct = False

    # Compare key signature
    if key_checked:
        if ex_m.get("key") is not None:
            key_correct = (
                gt_m["key"]["fifths"] == ex_m["key"]["fifths"]
                and gt_m["key"].get("mode", "major") == ex_m["key"].get("mode", "major")
            )
        if not key_correct and ex_m.get("key") is not None:
            diffs.append({
                "type": "wrong_key",
                "measure": measure_num,
                "expected": gt_m["key"],
                "got": ex_m.get("key"),
            })
        elif not key_correct:
            diffs.append({
                "type": "missing_key",
                "measure": measure_num,
                "expected": gt_m["key"],
                "got": None,
            })

    # Compare time signature
    if time_checked:
        if ex_m.get("time") is not None:
            time_correct = (
                gt_m["time"]["beats"] == ex_m["time"]["beats"]
                and gt_m["time"]["beat_type"] == ex_m["time"]["beat_type"]
            )
        if not time_correct and ex_m.get("time") is not None:
            diffs.append({
                "type": "wrong_time",
                "measure": measure_num,
                "expected": gt_m["time"],
                "got": ex_m.get("time"),
            })
        elif not time_correct:
            diffs.append({
                "type": "missing_time",
                "measure": measure_num,
                "expected": gt_m["time"],
                "got": None,
            })

    # Compare notes
    gt_notes = gt_m["notes"]
    ex_notes = ex_m["notes"]

    # Match notes by position (index), comparing pitch, duration, type
    notes_matched = 0
    pitches_correct = 0
    durations_correct = 0
    gt_pitch_count = 0

    max_notes = max(len(gt_notes), len(ex_notes))

    for ni in range(max_notes):
        if ni >= len(gt_notes):
            diffs.append({
                "type": "extra_note",
                "measure": measure_num,
                "position": ni,
                "description": f"Extra note at position {ni}: {_note_str(ex_notes[ni])}",
            })
            continue

        if ni >= len(ex_notes):
            diffs.append({
                "type": "missing_note",
                "measure": measure_num,
                "position": ni,
                "description": f"Missing note at position {ni}: expected {_note_str(gt_notes[ni])}",
            })
            continue

        gt_n = gt_notes[ni]
        ex_n = ex_notes[ni]

        note_ok = True

        # Compare rest vs. note
        if gt_n["is_rest"] != ex_n["is_rest"]:
            diffs.append({
                "type": "wrong_note_type",
                "measure": measure_num,
                "position": ni,
                "description": f"Position {ni}: expected {'rest' if gt_n['is_rest'] else 'note'}, got {'rest' if ex_n['is_rest'] else 'note'}",
            })
            note_ok = False
        else:
            notes_matched += 1

        # Compare pitch (only for non-rests)
        if not gt_n["is_rest"] and gt_n["pitch"]:
            gt_pitch_count += 1
            if ex_n.get("pitch"):
                pitch_match = (
                    gt_n["pitch"]["step"] == ex_n["pitch"]["step"]
                    and gt_n["pitch"]["octave"] == ex_n["pitch"]["octave"]
                    and gt_n["pitch"].get("alter", 0) == ex_n["pitch"].get("alter", 0)
                )
                if pitch_match:
                    pitches_correct += 1
                else:
                    diffs.append({
                        "type": "wrong_pitch",
                        "measure": measure_num,
                        "position": ni,
                        "expected": gt_n["pitch"],
                        "got": ex_n["pitch"],
                    })
                    note_ok = False
            else:
                diffs.append({
                    "type": "missing_pitch",
                    "measure": measure_num,
                    "position": ni,
                    "expected": gt_n["pitch"],
                    "got": None,
                })
                note_ok = False

        # Compare duration using normalized quarter-note units so that fixtures
        # with non-standard divisions (e.g. music21's divisions=10080) compare
        # correctly against extractions that use divisions=1.
        gt_dur_norm = gt_n.get("duration_normalized", gt_n["duration"])
        ex_dur_norm = ex_n.get("duration_normalized", ex_n["duration"])
        if abs(gt_dur_norm - ex_dur_norm) < 0.001:
            durations_correct += 1
        else:
            diffs.append({
                "type": "wrong_duration",
                "measure": measure_num,
                "position": ni,
                "expected_duration": gt_n["duration"],
                "got_duration": ex_n["duration"],
                "expected_type": gt_n.get("type"),
                "got_type": ex_n.get("type"),
            })
            note_ok = False

        # Compare ties
        if gt_n.get("tie_start") != ex_n.get("tie_start"):
            diffs.append({
                "type": "wrong_tie",
                "measure": measure_num,
                "position": ni,
                "description": f"tie_start: expected {gt_n.get('tie_start')}, got {ex_n.get('tie_start')}",
            })
        if gt_n.get("tie_stop") != ex_n.get("tie_stop"):
            diffs.append({
                "type": "wrong_tie",
                "measure": measure_num,
                "position": ni,
                "description": f"tie_stop: expected {gt_n.get('tie_stop')}, got {ex_n.get('tie_stop')}",
            })

    is_perfect = (
        len(diffs) == 0
        and len(gt_notes) == len(ex_notes)
    )

    return {
        "measure_number": measure_num,
        "is_perfect": is_perfect,
        "gt_note_count": len(gt_notes),
        "ex_note_count": len(ex_notes),
        "notes_matched": notes_matched,
        "pitches_correct": pitches_correct,
        "durations_correct": durations_correct,
        "gt_pitch_count": gt_pitch_count,
        "key_checked": key_checked,
        "key_correct": key_correct,
        "time_checked": time_checked,
        "time_correct": time_correct,
        "diffs": diffs,
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _note_str(note: dict) -> str:
    """Human-readable string for a parsed note dict."""
    if note.get("is_rest"):
        return f"Rest({note.get('type', '?')})"
    p = note.get("pitch", {})
    alter_str = ""
    alter = p.get("alter", 0)
    if alter == 1:
        alter_str = "#"
    elif alter == -1:
        alter_str = "b"
    elif alter == 2:
        alter_str = "##"
    elif alter == -2:
        alter_str = "bb"
    return f"{p.get('step', '?')}{alter_str}{p.get('octave', '?')}({note.get('type', '?')})"


def _pct(correct: int, total: int) -> float:
    """Calculate percentage, handling division by zero."""
    if total == 0:
        return 100.0
    return round(correct / total * 100, 1)
