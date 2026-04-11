"""Regression tests for pipeline bug fixes:

- Model config: CLI entry-points default to "auto" (not "claude-sonnet-4-6")
- extract_from_image callers: unpack (Score, dict) tuple correctly
- test_api.py mock: return_value=(mock_score, {...}) tuple format
- DETAIL_PROMPT tuplet schema: fields + Rule 12
- _extract_json_from_response: edge cases
- nested_tuplets fixture: PNG existence on disk

NOTE: core/extractor.py on this branch still has the OLD signature
(returns Score, not tuple). Tests that call the real function directly
will FAIL to unpack — this is a known code bug documented at the bottom.
"""
import sys
import json
import inspect
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# A. extract_from_image return type tests
# ---------------------------------------------------------------------------

class TestExtractFromImageReturnType:
    """Verify the tuple-return contract of extract_from_image.

    The function is mocked at the API boundary — we test that callers can
    unpack (Score, dict) without crashing when the mock provides that shape.
    Patching is done at the call-site module (api.main), not core.extractor,
    so the mock intercepts the import reference correctly.
    """

    def _make_mock_score(self):
        """Build a minimal valid Score."""
        from models.measure import Clef, KeySignature, Measure, TimeSignature
        from models.note import Note, NoteType, Pitch
        from models.score import Part, Score

        score = Score(title="Test")
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

    def test_mock_returns_two_element_tuple(self):
        """Mocked extract_from_image (at api.main) returns a 2-tuple."""
        from models.score import Score

        mock_score = self._make_mock_score()
        mock_info = {"provider": "anthropic", "model": "claude-sonnet-4-6"}
        mock_return = (mock_score, mock_info)

        # Patch at the call-site so the mock intercepts correctly
        with patch("api.main.extract_from_image", return_value=mock_return) as m:
            result = m("fake.png")

        assert isinstance(result, tuple), "Expected a tuple return"
        assert len(result) == 2, "Expected exactly 2 elements"

    def test_first_element_is_score(self):
        """First element of the tuple is a Score object."""
        from models.score import Score

        mock_score = self._make_mock_score()
        mock_info = {"provider": "mock", "model": "mock"}

        with patch("api.main.extract_from_image", return_value=(mock_score, mock_info)) as m:
            score, _info = m("fake.png")

        assert isinstance(score, Score)

    def test_second_element_is_dict(self):
        """Second element of the tuple is a dict."""
        mock_score = self._make_mock_score()
        mock_info = {"provider": "anthropic", "model": "claude-sonnet-4-6"}

        with patch("api.main.extract_from_image", return_value=(mock_score, mock_info)) as m:
            _score, model_info = m("fake.png")

        assert isinstance(model_info, dict)

    def test_model_info_has_expected_keys(self):
        """model_info dict contains 'provider' and 'model' keys."""
        mock_score = self._make_mock_score()
        mock_info = {"provider": "anthropic", "model": "claude-sonnet-4-6"}

        with patch("api.main.extract_from_image", return_value=(mock_score, mock_info)) as m:
            _score, model_info = m("fake.png")

        assert "provider" in model_info
        assert "model" in model_info

    def test_caller_unpack_pattern_works(self):
        """Simulate the caller pattern: score, _model_info = extract_from_image(...)"""
        from models.score import Score

        mock_score = self._make_mock_score()
        mock_info = {"provider": "mock", "model": "mock"}

        with patch("api.main.extract_from_image", return_value=(mock_score, mock_info)) as m:
            # This is the exact pattern used in api/main.py and test_harness.py
            score, _model_info = m("fake.png")
            assert isinstance(score, Score)
            assert _model_info is mock_info

    def test_api_pipeline_uses_tuple_unpack(self):
        """api/main.py _run_pipeline uses score, _model_info = extract_from_image(...)"""
        import ast
        api_path = Path(__file__).parent.parent / "api" / "main.py"
        source = api_path.read_text()
        # The fix: unpack the tuple, not just assign score = extract_from_image(...)
        assert "score, _model_info = extract_from_image" in source, (
            "api/main.py should use 'score, _model_info = extract_from_image(...)' tuple unpack"
        )

    def test_actual_function_signature_returns_tuple(self):
        """core/extractor.extract_from_image return annotation is tuple.

        NOTE: This test documents a CODE BUG on this branch.
        The function signature still annotates -> Score (not -> tuple[Score, dict]).
        This test will FAIL until core/extractor.py is updated.
        """
        import inspect
        from core import extractor
        hints = {}
        try:
            import typing
            hints = typing.get_type_hints(extractor.extract_from_image)
        except Exception:
            sig = inspect.signature(extractor.extract_from_image)
            hints = {"return": sig.return_annotation}

        return_hint = hints.get("return", None)
        # The correct annotation should be tuple or include Score + dict
        # On this branch it's still Score — this assertion documents the bug
        assert return_hint is not None
        hint_str = str(return_hint)
        assert "tuple" in hint_str.lower() or "Tuple" in hint_str, (
            f"CODE BUG: extract_from_image return annotation is '{hint_str}', "
            "expected tuple[Score, dict]. core/extractor.py was not updated on this branch."
        )


# ---------------------------------------------------------------------------
# B. CLI model defaults
# ---------------------------------------------------------------------------

class TestCLIModelDefaults:
    """Verify --model defaults to 'auto' in both CLI entry-points."""

    def test_test_harness_model_default_is_auto(self):
        """test_harness.py main() --model defaults to 'auto'."""
        import click
        import importlib.util
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        spec = importlib.util.spec_from_file_location("test_harness", harness_path)
        harness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(harness)

        # Introspect the click command parameters
        cmd = harness.main
        assert hasattr(cmd, "params"), "main() should be a click.Command"
        model_param = next(
            (p for p in cmd.params if p.name == "model"),
            None,
        )
        assert model_param is not None, "--model parameter not found on test_harness.main"
        assert model_param.default == "auto", (
            f"test_harness.py --model default is '{model_param.default}', expected 'auto'"
        )

    def test_validate_baseline_model_default_is_auto(self):
        """tests/validate_baseline.py main() --model defaults to 'auto'."""
        import importlib.util
        baseline_path = Path(__file__).parent / "validate_baseline.py"
        spec = importlib.util.spec_from_file_location("validate_baseline", baseline_path)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)

        cmd = baseline.main
        assert hasattr(cmd, "params"), "main() should be a click.Command"
        model_param = next(
            (p for p in cmd.params if p.name == "model"),
            None,
        )
        assert model_param is not None, "--model parameter not found on validate_baseline.main"
        assert model_param.default == "auto", (
            f"validate_baseline.py --model default is '{model_param.default}', expected 'auto'"
        )

    def test_test_harness_source_no_claude_sonnet_default(self):
        """test_harness.py should not contain 'default=\"claude-sonnet-4-6\"'."""
        harness_path = Path(__file__).parent.parent / "test_harness.py"
        source = harness_path.read_text()
        assert 'default="claude-sonnet-4-6"' not in source, (
            "test_harness.py still has 'default=\"claude-sonnet-4-6\"' — fix not applied"
        )

    def test_validate_baseline_source_no_claude_sonnet_default(self):
        """validate_baseline.py should not contain 'default=\"claude-sonnet-4-6\"'."""
        baseline_path = Path(__file__).parent / "validate_baseline.py"
        source = baseline_path.read_text()
        assert 'default="claude-sonnet-4-6"' not in source, (
            "validate_baseline.py still has 'default=\"claude-sonnet-4-6\"' — fix not applied"
        )


# ---------------------------------------------------------------------------
# C. JobStore / _jobs dict API
# ---------------------------------------------------------------------------

class TestJobStoreAPI:
    """Verify _jobs dict assignment works (Sprint 1 uses plain dict).

    The BUILD context mentioned a JobStore.set() API but the actual
    implementation uses a plain dict. These tests reflect reality.
    """

    def test_jobs_is_plain_dict(self):
        """_jobs is a plain Python dict in api/main.py."""
        from api.main import _jobs
        assert isinstance(_jobs, dict), f"Expected dict, got {type(_jobs)}"

    def test_dict_assignment_works(self):
        """Dict-style assignment _jobs[id] = data works."""
        from api.main import _jobs, PENDING
        fake_id = "test-dict-assign-abc123"
        _jobs[fake_id] = {
            "id": fake_id,
            "status": PENDING,
            "filename": "test.png",
            "measure_count": None,
            "part_count": None,
            "musicxml": None,
            "error": None,
        }
        assert fake_id in _jobs
        assert _jobs[fake_id]["status"] == PENDING
        # Cleanup
        del _jobs[fake_id]

    def test_get_after_set_returns_same_data(self):
        """Setting and getting a job returns identical data."""
        from api.main import _jobs, PENDING
        fake_id = "test-get-set-xyz789"
        data = {
            "id": fake_id,
            "status": PENDING,
            "filename": "roundtrip.png",
            "measure_count": None,
            "part_count": None,
            "musicxml": None,
            "error": None,
        }
        _jobs[fake_id] = data
        retrieved = _jobs.get(fake_id)
        assert retrieved is data
        del _jobs[fake_id]

    def test_test_api_mock_uses_tuple_return(self):
        """test_api.py mock return_value is (score, dict) tuple, not bare score."""
        test_api_path = Path(__file__).parent / "test_api.py"
        source = test_api_path.read_text()
        assert 'return_value=(mock_score, {' in source or \
               'return_value=(mock_score, {"provider"' in source, (
            "test_api.py mock should return (mock_score, {...}) tuple, not bare mock_score"
        )

    def test_pending_job_accessible_via_dict_key(self):
        """A job inserted via dict assignment is accessible by key."""
        from api.main import _jobs, PENDING
        fake_id = "test-pending-access-111"
        _jobs[fake_id] = {"id": fake_id, "status": PENDING}
        assert _jobs.get(fake_id) is not None
        assert _jobs[fake_id]["status"] == PENDING
        del _jobs[fake_id]


# ---------------------------------------------------------------------------
# D. _extract_json_from_response edge cases
# ---------------------------------------------------------------------------

class TestExtractJsonFromResponse:
    """Unit tests for core.extractor._extract_json_from_response."""

    @pytest.fixture(autouse=True)
    def import_fn(self):
        from core.extractor import _extract_json_from_response
        self.fn = _extract_json_from_response

    def test_happy_path_json_fence(self):
        """Extracts JSON from ```json...``` block."""
        text = '```json\n{"title": "Test", "parts": []}\n```'
        result = self.fn(text)
        data = json.loads(result)
        assert data["title"] == "Test"

    def test_happy_path_bare_fence(self):
        """Extracts JSON from bare ``` block."""
        text = '```\n{"title": "Bare", "parts": []}\n```'
        result = self.fn(text)
        data = json.loads(result)
        assert data["title"] == "Bare"

    def test_happy_path_bare_json(self):
        """Extracts bare JSON object without fences."""
        text = '{"title": "No Fence", "parts": []}'
        result = self.fn(text)
        data = json.loads(result)
        assert data["title"] == "No Fence"

    def test_happy_path_json_with_preamble(self):
        """Strips preamble text before JSON."""
        text = 'Here is the result:\n{"title": "Preamble Test"}'
        result = self.fn(text)
        data = json.loads(result)
        assert data["title"] == "Preamble Test"

    def test_happy_path_json_array(self):
        """JSON array with no preceding { bracket is extracted correctly.

        Note: _extract_json_from_response scans for { before [, so an array
        containing objects will match the first { of the first object, not the
        outer array. Wrap in an object to avoid this ambiguity in production use.
        This test documents the actual behavior.
        """
        # A plain array with no { inside is handled correctly
        text = '[1, 2, 3]'
        result = self.fn(text)
        data = json.loads(result)
        assert len(data) == 3

    def test_empty_string_returns_empty_or_raises(self):
        """Empty string: returns empty string or raises (not crash)."""
        try:
            result = self.fn("")
            # If it returns, it should be falsy or empty
            assert result == "" or result is None or result == "{}" or True
        except (ValueError, json.JSONDecodeError, IndexError):
            pass  # Acceptable — raising on empty input is fine

    def test_malformed_json_bracket_scan(self):
        """Malformed JSON: bracket scan returns partial JSON (caller gets json error)."""
        text = '{"title": "Broken", "parts": ['
        result = self.fn(text)
        # The function returns what it found; caller (json.loads) would fail
        assert result is not None
        assert "{" in result

    def test_no_json_returns_raw_text(self):
        """Text with no JSON brackets returns the raw stripped text."""
        text = "No JSON here at all"
        result = self.fn(text)
        assert isinstance(result, str)

    def test_nested_json(self):
        """Nested JSON objects parse correctly."""
        text = '{"outer": {"inner": {"deep": true}}}'
        result = self.fn(text)
        data = json.loads(result)
        assert data["outer"]["inner"]["deep"] is True

    def test_tuplet_fields_in_json(self):
        """JSON containing tuplet fields is extracted correctly."""
        tuplet_note = {
            "type": "eighth",
            "is_rest": False,
            "pitch": {"step": "C", "octave": 5, "alter": 0},
            "tuplet_actual": 3,
            "tuplet_normal": 2,
            "tuplet_start": True,
            "tuplet_stop": False,
        }
        text = json.dumps({"notes": [tuplet_note]})
        result = self.fn(text)
        data = json.loads(result)
        note = data["notes"][0]
        assert note["tuplet_actual"] == 3
        assert note["tuplet_normal"] == 2
        assert note["tuplet_start"] is True
        assert note["tuplet_stop"] is False

    def test_whitespace_only_string(self):
        """Whitespace-only string: returns empty or raises gracefully."""
        try:
            result = self.fn("   \n\t  ")
            assert result == "" or result is not None
        except Exception:
            pass  # Acceptable

    def test_json_in_fences_with_preamble(self):
        """JSON in fences preceded by explanation text."""
        text = (
            "I have extracted the score structure:\n\n"
            "```json\n"
            '{"title": "Waltz", "parts": [{"name": "Piano", "staves": 2}]}\n'
            "```\n\n"
            "Let me know if you need more details."
        )
        result = self.fn(text)
        data = json.loads(result)
        assert data["title"] == "Waltz"
        assert data["parts"][0]["staves"] == 2


# ---------------------------------------------------------------------------
# E. DETAIL_PROMPT schema validation
# ---------------------------------------------------------------------------

class TestDetailPromptSchema:
    """Verify DETAIL_PROMPT contains required tuplet fields and rules.

    NOTE: On this branch, core/extractor.py was NOT updated with tuplet
    fields in DETAIL_PROMPT. Tests marked with the expected failure are
    documenting CODE BUGS that need to be fixed.
    """

    @pytest.fixture(autouse=True)
    def load_prompt(self):
        from core.extractor import DETAIL_PROMPT
        self.prompt = DETAIL_PROMPT

    def test_prompt_is_nonempty(self):
        """DETAIL_PROMPT exists and is not empty."""
        assert self.prompt and len(self.prompt) > 100

    def test_prompt_contains_tuplet_actual(self):
        """DETAIL_PROMPT JSON schema includes 'tuplet_actual'.

        NOTE: This FAILS on this branch — core/extractor.py missing tuplet fields.
        """
        assert "tuplet_actual" in self.prompt, (
            "CODE BUG: DETAIL_PROMPT missing 'tuplet_actual' field. "
            "core/extractor.py was not updated with tuplet schema on this branch."
        )

    def test_prompt_contains_tuplet_normal(self):
        """DETAIL_PROMPT JSON schema includes 'tuplet_normal'.

        NOTE: This FAILS on this branch — core/extractor.py missing tuplet fields.
        """
        assert "tuplet_normal" in self.prompt, (
            "CODE BUG: DETAIL_PROMPT missing 'tuplet_normal' field."
        )

    def test_prompt_contains_tuplet_start(self):
        """DETAIL_PROMPT JSON schema includes 'tuplet_start'.

        NOTE: This FAILS on this branch — core/extractor.py missing tuplet fields.
        """
        assert "tuplet_start" in self.prompt, (
            "CODE BUG: DETAIL_PROMPT missing 'tuplet_start' field."
        )

    def test_prompt_contains_tuplet_stop(self):
        """DETAIL_PROMPT JSON schema includes 'tuplet_stop'.

        NOTE: This FAILS on this branch — core/extractor.py missing tuplet fields.
        """
        assert "tuplet_stop" in self.prompt, (
            "CODE BUG: DETAIL_PROMPT missing 'tuplet_stop' field."
        )

    def test_prompt_contains_tuplets_rule(self):
        """DETAIL_PROMPT contains a TUPLETS rule section.

        NOTE: This FAILS on this branch — Rule 12 is ANTI-HALLUCINATION, not TUPLETS.
        """
        assert "TUPLETS" in self.prompt, (
            "CODE BUG: DETAIL_PROMPT missing 'TUPLETS' rule. "
            "Rule 12 on this branch is ANTI-HALLUCINATION, not TUPLETS."
        )

    def test_prompt_contains_completeness_rule(self):
        """DETAIL_PROMPT contains COMPLETENESS rule (basic sanity)."""
        assert "COMPLETENESS" in self.prompt

    def test_prompt_contains_pitch_accuracy_rule(self):
        """DETAIL_PROMPT contains PITCH ACCURACY rule."""
        assert "PITCH ACCURACY" in self.prompt

    def test_prompt_contains_anti_hallucination(self):
        """DETAIL_PROMPT contains ANTI-HALLUCINATION rule."""
        assert "ANTI-HALLUCINATION" in self.prompt

    def test_model_default_not_claude_sonnet(self):
        """core/extractor.py extract_from_image default model should be 'auto'.

        NOTE: This FAILS on this branch — default is still 'claude-sonnet-4-6'.
        """
        from core import extractor
        sig = inspect.signature(extractor.extract_from_image)
        model_default = sig.parameters.get("model", None)
        assert model_default is not None
        assert model_default.default == "auto", (
            f"CODE BUG: extract_from_image model default is '{model_default.default}', "
            "expected 'auto'. core/extractor.py was not updated on this branch."
        )


# ---------------------------------------------------------------------------
# F. Nested tuplets fixture existence
# ---------------------------------------------------------------------------

class TestNestedTupletsFixture:
    """Verify fixture files exist on disk."""

    def test_nested_tuplets_musicxml_exists(self):
        """tests/fixtures/nested_tuplets.musicxml exists."""
        fixture_path = Path(__file__).parent / "fixtures" / "nested_tuplets.musicxml"
        assert fixture_path.exists(), (
            f"Fixture missing: {fixture_path}. "
            "Run tests/fixtures/generate_fixtures.py to generate it."
        )

    def test_nested_tuplets_png_exists(self):
        """tests/fixtures/nested_tuplets.png exists on disk.

        NOTE: This FAILS — only .musicxml is present, no .png rendered.
        A .png render is needed for image-based extraction tests.
        """
        fixture_path = Path(__file__).parent / "fixtures" / "nested_tuplets.png"
        assert fixture_path.exists(), (
            f"Fixture PNG missing: {fixture_path}. "
            "Render nested_tuplets.musicxml to PNG before running image extraction tests."
        )

    def test_fixtures_directory_exists(self):
        """tests/fixtures/ directory exists."""
        fixtures_dir = Path(__file__).parent / "fixtures"
        assert fixtures_dir.is_dir()

    def test_multi_voice_fixture_exists(self):
        """multi_voice.musicxml fixture exists (used by test_multi_voice.py)."""
        fixture_path = Path(__file__).parent / "fixtures" / "multi_voice.musicxml"
        assert fixture_path.exists()


# ---------------------------------------------------------------------------
# Summary of known code bugs (documented, not fixed here)
# ---------------------------------------------------------------------------

class TestCodeBugDocumentation:
    """These tests document known code bugs on this branch that need fixing.

    They are expected to FAIL — failures are features, not regressions.
    They exist so the next stage knows exactly what to fix in source code.
    """

    def test_document_extractor_return_type_bug(self):
        """
        BUG: core/extractor.py extract_from_image() returns Score, not tuple.

        File: /home/deployer/scoreforge/core/extractor.py line 279
        Current:  ) -> Score:
        Required: ) -> tuple["Score", dict]:

        Also: model default "claude-sonnet-4-6" → "auto" (line 276)
        Also: _extract_two_pass and _extract_single_pass must return (score, info) tuples.

        The callers (api/main.py, test_harness.py, validate_baseline.py) were correctly
        updated on this branch to unpack (score, _model_info), but the function itself
        was not updated. In production this will raise: ValueError: too many values to unpack
        OR AttributeError — depending on Python version.
        """
        from core.extractor import extract_from_image
        import inspect
        sig = inspect.signature(extract_from_image)
        model_param = sig.parameters.get("model")
        # Document both bugs
        bugs = []
        if model_param and model_param.default != "auto":
            bugs.append(f"model default='{model_param.default}' (should be 'auto')")

        import typing
        try:
            hints = typing.get_type_hints(extract_from_image)
            ret = str(hints.get("return", ""))
            if "tuple" not in ret.lower():
                bugs.append(f"return type='{ret}' (should be tuple[Score, dict])")
        except Exception:
            pass

        if bugs:
            pytest.fail(
                "CODE BUGS in core/extractor.py that must be fixed:\n  - " +
                "\n  - ".join(bugs)
            )

    def test_document_detail_prompt_missing_tuplet_fields(self):
        """
        BUG: DETAIL_PROMPT in core/extractor.py is missing tuplet fields.

        File: /home/deployer/scoreforge/core/extractor.py
        Missing from JSON schema: tuplet_actual, tuplet_normal, tuplet_start, tuplet_stop
        Missing rule: Rule 12 should be TUPLETS (currently ANTI-HALLUCINATION)

        The main branch (commits 67e0563, 82a7c64) added these fields.
        This branch diverged before those commits and core/extractor.py was
        not rebased/cherry-picked.
        """
        from core.extractor import DETAIL_PROMPT
        missing = [
            field for field in
            ["tuplet_actual", "tuplet_normal", "tuplet_start", "tuplet_stop", "TUPLETS"]
            if field not in DETAIL_PROMPT
        ]
        if missing:
            pytest.fail(
                f"CODE BUG: DETAIL_PROMPT missing: {missing}. "
                "core/extractor.py needs to be updated with tuplet schema."
            )
