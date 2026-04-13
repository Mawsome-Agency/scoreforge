# Implementation Plan

## Feature: Add MusicXML schema validation gate before accuracy comparison
Scope: FEATURE | Iterations: 14 | Branch: cortex/add-musicxml-schema-validation-gate-befo

## Scoping Research
## Code Scope
Now I have a complete picture of the codebase. Let me compile the comprehensive file map:

---

## Codebase Analysis: MusicXML Schema Validation Gate

### Executive Summary

**Feature**: Add MusicXML structural validation before accuracy comparison to catch malformed XML, missing elements, and structural errors that produce misleading accuracy scores.

**Current State**: `core/validator.py` exists with basic `validate_musicxml_structure()` but is **not integrated** into any execution paths.

**Primary Integration Point**: `core/comparator.py:compare_musicxml_semantic()` — this is where the validation gate should be inserted.

---

### Execution Path Analysis

#### Path 1: Test Harness (`test_harness.py`)
```
run_test() → Step 3: build_musicxml() → [SAVE XML] → Step 4: compare_musicxml_semantic()
                                                      ↓
                                              VALIDATION GATE (insert here)
                                                      ↓
                                              Returns comparison result
```

#### Path 2: Baseline Validation (`tests/validate_baseline.py`)
```
run_fixture() → build_musicxml() → [SAVE XML] → compare_musicxml_semantic(gt_path, extracted_xml)
                                                      ↓
                                              VALIDATION GATE (insert here)
```

#### Path 3: Iteration Runner (`iterate.py`)
```
iterate_fixture() → build_musicxml() → [SAVE extracted_xml_path] → compare_musicxml_semantic()
                                                                            ↓
                                                                    VALIDATION GATE
```

#### Path 4: CLI Test Runner (`run_test.py`)
```
run_fixture() → build_musicxml() → [SAVE XML] → compare_musicxml_semantic()
                                                      ↓
                                              VALIDATION GATE
```

#### Path 5: API Pipeline (`api/main.py`)
```
_run_pipeline() → extract_from_image() → build_musicxml() → [RETURN]
                                  ↑
                         Could add validation here (optional)
```

#### Path 6: Extraction Quality Smoke Test (`tests/test_extraction_quality.py`)
```
check_fixture() → _parse_musicxml() → structural checks
          ↑
    Uses _parse_musicxml from comparator (not direct validation)
```

---

### Dependency Graph

```
core/validator.py
    ├── xml.etree.ElementTree (stdlib)
    ├── typing (stdlib)
    └── pathlib (stdlib)

core/comparator.py
    ├── lxml.etree (external)
    ├── numpy (external)
    ├── PIL (external)
    ├── imagehash (external)
    └── core.api (internal)
    ↑
    └── WILL IMPORT: core.validator

test_harness.py
    ├── core.comparator
    ├── core.renderer
    ├── core.extractor
    ├── core.musicxml_builder
    └── test fixtures

iterate.py
    ├── core.comparator
    ├── core.renderer
    ├── core.extractor
    ├── core.musicxml_builder
    ├── core.fixer
    └── test fixtures

tests/validate_baseline.py
    ├── core.comparator
    ├── core.renderer
    ├── core.extractor
    ├── core.musicxml_builder
    └── test fixtures

tests/test_extraction_quality.py
    ├── core.comparator._parse_musicxml (fallback ET parser)
    └── test fixtures
```

---

### Files to Modify: Complete List

| File | Purpose | Change Type | Line Estimates |
|------|---------|-------------|----------------|
| **core/validator.py** | Main validation logic | **MODIFY** — Expand existing function | +40 lines |
| **core/comparator.py** | Add validation gate | **MODIFY** — Insert validation call at start of `compare_musicxml_semantic()` | +15 lines |
| **test_harness.py** | Test runner | **NO CHANGE** — Benefits from comparator change | — |
| **tests/validate_baseline.py** | Baseline validation | **NO CHANGE** — Benefits from comparator change | — |
| **iterate.py** | Iteration runner | **NO CHANGE** — Benefits from comparator change | — |
| **run_test.py** | CLI runner | **NO CHANGE** — Benefits from comparator change | — |
| **tests/test_extraction_quality.py** | Smoke tests | **NO CHANGE** — Uses own structural checks | — |

---

### Function Signatures

#### Existing in `core/validator.py`
```python
def validate_musicxml_structure(path: str) -> Tuple[bool, Optional[str]]:
    """Validate the structural integrity of a MusicXML file."""
```

#### Modified in `core/validator.py`
```python
def validate_musicxml_structure(path: str) -> Tuple[bool, Optional[str]]:
    """Validate the structural integrity of a MusicXML file."""
    # EXPANDED: Additional checks for:
    # - Required elements (part-list, score-part, part)
    # - First measure attributes (divisions, time, key)
    # - Note elements have valid structure
    # - Duration values are positive integers

def validate_musicxml_against_ground_truth(
    extracted_path: str,
    ground_truth_path: str
) -> Tuple[bool, Optional[str]]:
    """Cross-validate extracted XML against GT structure."""
    # NEW FUNCTION: Compare structural elements (parts, measures)
    # before semantic comparison
```

#### Modified in `core/comparator.py`
```python
def compare_musicxml_semantic(
    ground_truth_path: str,
    extracted_path: str,
) -> dict:
    """Semantically compare two MusicXML files."""
    # INSERT AT LINE ~175 (start of function):
    # 1. Call validate_musicxml_structure(extracted_path)
    # 2. If invalid, return early with validation error
    # 3. Otherwise proceed with _parse_musicxml calls
```

#### Return Shape for Validation Failure (comparator)
```python
{
    "part_count_match": False,
    "gt_part_count": 0,
    "ex_part_count": 0,
    "part_diffs": [],
    "scores": {
        "note_accuracy": 0.0,
        "pitch_accuracy": 0.0,
        "rhythm_accuracy": 0.0,
        "measure_accuracy": 0.0,
        "key_sig_accuracy": 0.0,
        "time_sig_accuracy": 0.0,
        "voice_accuracy": 0.0,
        "ornament_accuracy": 0.0,
        "grace_note_accuracy": 0.0,
        "overall": 0.0,
    },
    "total_notes_gt": 0,
    "total_notes_matched": 0,
    "is_perfect": False,
    "validation_error": "string error message",  # NEW FIELD
}
```

---

### Shared Utilities to Reuse

| Utility | Location | Purpose |
|---------|----------|---------|
| `_strip_ns()` | `core/validator.py:84-95` | Strip XML namespace prefixes for tag comparison |
| `_parse_musicxml()` | `core/comparator.py:359-442` | Full MusicXML parser — can be reused for validation |
| `Path` handling | Throughout codebase | Consistent file path operations |

---

### Fragile/Coupled Files (Handle with Care)

| File | Risk Level | Concern |
|------|------------|---------|
| `core/comparator.py` | **HIGH** | Central to all accuracy scoring; changes affect test results, baseline reports, iteration loop |
| `core/musicxml_builder.py` | **MEDIUM** | Output is consumed by comparator; malformed output is what we're validating |
| `core/extractor.py` | **LOW** | Uses `build_musicxml()`; validation happens downstream |
| `iterate.py` | **MEDIUM** | Has retry logic based on comparison results; validation errors should trigger retry |

---

### Edge Cases to Consider

1. **Namespace Handling**: MusicXML files may have namespace prefixes (e.g., `<m:part>` vs `<part>`). Current `_strip_ns()` helper exists but validation must handle both.

2. **Empty Scores**: `empty_score` fixture has valid structure but zero notes. Validation must not reject this.

3. **Corpus PDFs** (`test_harness.py:run_corpus_pdf()`): No ground truth exists — validation should be purely structural, not comparative.

4. **Malformed XML**: `lxml.etree.parse()` raises on malformed XML; `xml.etree.ElementTree.parse()` has different error handling. Validator uses stdlib ET, comparator uses lxml.

5. **Temporary Files**: `run_test.py` and `iterate.py` write XML to disk before comparison. Validation must read from disk path.

6. **Fix Loop Interaction**: In `iterate.py`, if validation fails, should trigger re-extraction (treat as "error" for retry purposes).

---

### Validation Checklist (What to Validate)

| Check | Severity | Implementation Location |
|-------|----------|---------------------------|
| XML well-formedness | **BLOCKING** | `validator.py` — ET.parse() |
| Root element is `score-partwise` | **BLOCKING** | `validator.py` |
| At least one `<part>` exists | **BLOCKING** | `validator.py` |
| Each part has at least one `<measure>` | **BLOCKING** | `validator.py` |
| First measure has `<attributes>` with `<divisions>` | **WARNING** | `validator.py` |
| All notes have `<duration>` > 0 | **WARNING** | `validator.py` |
| Measure count matches ground truth | **WARNING** | `comparator.py` gate |

---

<self-eval confidence="5" quality="5">blockers: none</self-eval>

## Risk Scope
I'll analyze the codebase to identify potential risks associated with adding MusicXML schema validation. Let me explore the relevant files and dependencies.Let me check if the file exists and explore the core directory structure:I can see that `validator.py` doesn't exist yet, which makes sense since we're planning to create it. Let me examine the existing validation-related code and understand how MusicXML is currently handled:Now let me examine the extractor module to understand how MusicXML is currently generated and validated:Let me also check the musicxml_builder to understand how MusicXML is generated:Let me check the test files to understand how validation is currently handled:Now let me check if there are any existing validation mechanisms or schemas in the project:Let me check the git log to see recent validation-related changes:Let me check the extraction quality smoke test that was recently added:Now let me check if there are any existing schema validation mechanisms in the project:Let me check for any references to MusicXML schema or validation in the requirements or documentation:Let me check the ARCHITECTURE.md file to understand the planned validation approach:Let me check if music21 is used for validation anywhere in the codebase:

## Context Scope
## Context Brief: MusicXML Validation in ScoreForge

Based on my analysis of the codebase, here's the current landscape for implementing the MusicXML schema validation gate:

### 1. Existing Validation Infrastructure
There is already a `core/validator.py` module containing a `validate_musicxml_structure()` function that performs basic structural validation:
- Checks for well-formed XML
- Validates root element is 'score-partwise'
- Ensures presence of parts and measures
- Verifies required 'divisions' attribute

However, this function is currently **unused** in the codebase - it's not imported or called anywhere.

### 2. Comparison Workflow
The `core/comparator.py` module handles semantic comparison of MusicXML files using `_parse_musicxml()` function which:
- Parses MusicXML files using lxml
- Handles namespaces properly
- Extracts structural elements (parts, measures, notes)
- Performs detailed semantic comparison including:
  - Note-by-note matching
  - Pitch accuracy
  - Duration normalization
  - Key/time signature validation
  - Ornament and grace note scoring

### 3. Recent Development Patterns
Recent commits show the team has been focused on:
- Improving extraction quality (`feat(tests): add extraction quality smoke test`)
- Enhancing comparator accuracy metrics
- Adding voice-aware comparison logic
- Normalizing durations for cross-divisions comparison
- Adding ornament/grace note scoring

### 4. Testing Infrastructure
There's a `tests/test_extraction_quality.py` smoke test that:
- Validates extracted MusicXML structure without API calls
- Uses `_parse_musicxml` from comparator
- Checks for common extraction bugs (duration=1, measure stuffing)
- Provides detailed per-fixture quality reports

### 5. Technical Debt & Known Issues
The existing validation is incomplete:
- The `validate_musicxml_structure()` function exists but isn't integrated
- No schema validation to catch malformed XML structures
- Current comparator parsing may fail silently on invalid XML
- No explicit validation gate before accuracy comparison

### 6. Team Conventions
- Validation functions return tuples with (success_bool, error_message)
- Error handling uses Optional types for error messages
- Rich console output for test reporting
- Comprehensive type hints throughout
- Fallback implementations for optional dependencies (rich library)

### 7. Implementation Opportunities
The new validation gate should:
- Integrate with the existing `validate_musicxml_structure()` function
- Be called before `compare_musicxml_semantic()` in the comparison workflow
- Follow the existing pattern of returning structured error information
- Maintain consistency with current error handling approaches

This context shows there's a solid foundation for adding the requested validation gate, with most of the required infrastructure already in place.

## Architecture Plan
## Feature: Add MusicXML schema validation gate before accuracy comparison
## Scope: FEATURE
## Iteration: 1 — Focus: Architecture, module boundaries, data flows

### Architecture
The validation gate will be implemented as a preprocessing step that ensures extracted MusicXML files meet basic structural requirements before being compared against ground truth. This will prevent misleading accuracy scores caused by malformed XML.

The implementation will:
1. Add validation logic to the existing `core/validator.py` file
2. Modify the comparator to perform validation before comparison
3. Ensure proper error handling and return value consistency
4. Integrate validation in all entry points that use the comparator

### Data Model
No schema changes are required. The validation will work with existing MusicXML files and return structured error information.

### API Design
No new API endpoints are needed. The validation will be integrated into existing functions.

### Files to Modify
| File | Change | Functions |
|------|--------|-----------|
| core/comparator.py | Add validation check at start of compare_musicxml_semantic | compare_musicxml_semantic(extracted_path: str) |
| core/validator.py | Enhance existing validation logic to handle namespaces and check for notes/rests | validate_musicxml_structure(path: str) |

### Files to Create
| File | Purpose | Key Functions |
|------|---------|---------------|
| (None) | All necessary files already exist | (None) |

### Data Flow
1. When `compare_musicxml_semantic()` is called, it first validates the extracted MusicXML file using the updated validation function
2. If validation fails, it returns early with a structured error result containing all expected fields (validation_error plus all standard comparison fields)
3. If validation passes, it continues with the normal comparison process
4. The validation gate ensures that only structurally valid MusicXML files are compared, preventing misleading accuracy scores

### Acceptance Criteria
- [ ] Validation is performed before any semantic comparison in `compare_musicxml_semantic`
- [ ] When validation fails, the function returns a result with `error` field containing validation error message AND all standard comparison fields (total_notes_gt, total_notes_matched, is_perfect, scores.overall, etc.)
- [ ] When validation passes, normal comparison proceeds as before
- [ ] The validation error return structure matches what the test harness expects
- [ ] All integration points (`iterate.py`, `run_test.py`, `test_harness.py`) properly handle validation results
- [ ] Existing validation logic in `core/validator.py` is enhanced to handle XML namespaces properly
- [ ] Validation correctly handles measures containing only rests (not just notes)

### Risks & Edge Cases
- Risk: Existing test fixtures might fail validation due to stricter requirements
  - Mitigation: Review and potentially adjust validation rules to maintain backward compatibility
  
- Risk: Performance impact from additional validation step
  - Mitigation: Validation is lightweight (XML parsing only) and won't significantly impact performance
  
- Edge case: Empty or completely invalid XML files
  - Handling: Return clear error messages that distinguish between XML parsing errors and structural validation errors

### Dependencies
- Reuse: Existing `validate_musicxml_structure` function in `core/validator.py`
- Reuse: Existing XML parsing infrastructure
- New deps: None

<self-eval confidence="5" quality="5">blockers: none</self-eval>

## Implementation Detail
Now I have a good understanding of the codebase. Let me create an updated implementation plan that addresses all the reviewer feedback:

## Feature: Add MusicXML schema validation gate before accuracy comparison
## Scope: FEATURE

## Iteration: 1 — Focus: Fix namespace handling and improve validator robustness

### Architecture
The validation gate will be implemented as a centralized check inside `compare_musicxml_semantic()` function in `core/comparator.py`. This ensures all callers benefit from validation without duplicating code.

### Data Model
No schema changes required. The feature enhances validation logic only.

### API Design
No API changes required. The validation is internal to the comparison pipeline.

### Files to Modify

| File | Change | Functions |
|------|--------|-----------|
| core/validator.py | Fix namespace handling, improve note/rest validation, add helper function | validate_musicxml_structure, _strip_ns |
| core/comparator.py | Add validation gate at start of function, adjust early-return structure | compare_musicxml_semantic |

### Files to Create
None

### Data Flow
1. `compare_musicxml_semantic()` receives ground truth and extracted MusicXML paths
2. Validation gate runs first using `validate_musicxml_structure()` on extracted file
3. If validation fails, return complete result dict with defaults and validation_error field
4. If validation passes, continue with existing comparison logic

### Acceptance Criteria
- [ ] Validator correctly handles XML namespaces in MusicXML files
- [ ] Validator accepts measures containing only rests as valid
- [ ] Early-return result dict contains all expected fields for test harness compatibility
- [ ] Validation occurs before expensive XML parsing operations
- [ ] Import ordering follows standard conventions (stdlib → third-party → internal)
- [ ] All existing tests continue to pass

### Risks & Edge Cases
- Risk: Namespace handling might miss some edge cases with complex namespace declarations
  - Mitigation: Use lxml's namespace resolution capabilities properly
- Edge case: Files with mixed namespaces or default namespaces
  - Handling: Use namespace-agnostic searching with `{*}element` syntax
- Risk: Performance impact from double parsing
  - Mitigation: Refactor to optionally accept parsed tree to avoid reparsing

### Dependencies
- Reuse: Existing lxml parsing infrastructure
- New deps: None

## Updated Implementation Details

### 1️⃣ Core validator improvements

**File: `core/validator.py`**

Changes needed:
1. Add namespace handling using `_strip_ns()` helper function
2. Fix measure validation to accept rests in addition to notes
3. Improve error messages for better debugging

```python
# Add helper function for namespace stripping
def _strip_ns(tag: str) -> str:
    """Strip namespace from tag, e.g. '{http://www.musicxml.org/xsd}note' → 'note'"""
    return tag.split('}')[-1] if '}' in tag else tag

def validate_musicxml_structure(path: str) -> Tuple[bool, str]:
    """Validate MusicXML file structure."""
    try:
        # Check if file is well-formed XML
        tree = etree.parse(path)
        root = tree.getroot()
    except Exception as e:
        return False, f"XML parsing failed: {str(e)}"
    
    # Check root element is score-partwise (with namespace handling)
    root_tag = _strip_ns(root.tag)
    if root_tag != "score-partwise":
        return False, f"Root element is '{root_tag}', expected 'score-partwise'"
    
    # Check for at least one part (namespace-agnostic)
    parts = root.findall(".//{*}part")
    if not parts:
        return False, "No <part> elements found"
    
    # Check each part has at least one measure
    for i, part in enumerate(parts):
        measures = part.findall(".//{*}measure")
        if not measures:
            return False, f"Part {i} has no <measure> elements"
        
        # Check each measure has at least one note OR rest
        for j, measure in enumerate(measures):
            notes = measure.findall(".//{*}note")
            rests = measure.findall(".//{*}rest")
            if not notes and not rests:
                measure_num = measure.get("number", j+1)
                return False, f"Measure {measure_num} in part {i} has no <note> or <rest> elements"
    
    # Check first measure of first part has divisions attribute
    first_part = parts[0]
    first_measure = first_part.find(".//{*}measure")
    if first_measure is None:
        return False, "First part has no measures"
    
    attributes = first_measure.find(".//{*}attributes")
    if attributes is None:
        return False, "First measure has no <attributes> element"
    
    divisions = attributes.find(".//{*}divisions")
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
```

### 2️⃣ Comparator modification

**File: `core/comparator.py`**

Changes needed:
1. Add import for validator
2. Move validation to the very beginning of function
3. Return complete result structure on validation failure
4. Maintain existing comparison logic unchanged

```python
# After existing imports, add:
from core.validator import validate_musicxml_structure

def compare_musicxml_semantic(
    ground_truth_path: str,
    extracted_path: str,
) -> dict:
    """Semantically compare two MusicXML files note-by-note and measure-by-measure."""

    # ----------------------------------------------------------------
    # NEW: structural validation gate (runs before any parsing)
    # ----------------------------------------------------------------
    is_valid, err_msg = validate_musicxml_structure(extracted_path)
    if not is_valid:
        # Return a *complete* result dict so downstream callers (tests,
        # report generation, CLI) can safely access any key.
        return {
            "validation_error": err_msg,          # <-- new field
            "part_count_match": False,
            "gt_part_count": 0,
            "ex_part_count": 0,
            "part_diffs": [],                     # empty list of diffs
            "scores": {
                "note_accuracy": 0.0,
                "pitch_accuracy": 0.0,
                "rhythm_accuracy": 0.0,
                "measure_accuracy": 0.0,
                "key_sig_accuracy": 0.0,
                "time_sig_accuracy": 0.0,
                "voice_accuracy": 0.0,
                "ornament_accuracy": 0.0,
                "grace_note_accuracy": 0.0,
                "overall": 0.0,
            },
            "total_notes_gt": 0,
            "total_notes_matched": 0,
            "is_perfect": False,
        }

    # ----------------------------------------------------------------
    # Existing parsing logic continues unchanged
    # ----------------------------------------------------------------
    gt_data = _parse_musicxml(ground_truth_path)
    ex_data = _parse_musicxml(extracted_path)
    
    # ... rest of existing function unchanged ...
```

This implementation addresses all the reviewer's feedback:

1. **Namespace handling**: Added `_strip_ns()` helper and use namespace-agnostic searching with `{*}element`
2. **Note/rest validation**: Check for both notes and rests in measures
3. **Complete result structure**: Return all fields expected by test harness
4. **Early validation**: Validation runs before expensive parsing operations
5. **Import placement**: Properly ordered with other internal imports
6. **Performance consideration**: Could be further optimized by passing parsed tree if needed

<self-eval confidence="5" quality="5">blockers: none</self-eval>

## Review Notes
Based on my analysis of the codebase, I can now provide a comprehensive review of the plan:

<signoff status="rejected">Blocking issues found that must be addressed before build.</signoff>

## Issues Found:

**Issue 1**: **Redundant validation logic**
The current `compare_musicxml_semantic` function already performs validation at the beginning (lines 187-193 in comparator.py). The proposed plan seems to want to add validation but it's already there.

**Severity**: MEDIUM  
**Location**: Plan description and current implementation  
**Fix**: The architect should recognize that validation is already happening and focus on improving the existing validation rather than adding duplicate validation.

**Issue 2**: **Incomplete namespace handling in existing validator**
Looking at the current `validator.py`, while it has the `_strip_ns` helper, the implementation in `compare_musicxml_semantic` doesn't fully utilize proper namespace handling. The validation function tries to determine the namespace but doesn't consistently apply it throughout.

**Severity**: HIGH  
**Location**: Core validation logic in validator.py  
**Fix**: Implement consistent namespace handling using lxml's namespace resolution or proper namespace prefixes throughout the validation.

**Issue 3**: **Validation error return structure inconsistency**
When validation fails in `compare_musicxml_semantic`, it returns a minimal structure that doesn't match the expected result format from the test harness. The acceptance criteria mention that the validation error return structure should match what the test harness expects, but the current implementation returns `{structural_validity: false, validation_error: "..."}` which may not include all expected fields like `scores`, `total_notes_gt`, etc.

**Severity**: HIGH  
**Location**: Error handling in compare_musicxml_semantic function  
**Fix**: Ensure the validation error return includes all standard comparison fields with default values as mentioned in the acceptance criteria:
```python
return {
    "structural_validity": False,
    "validation_error": err_ex,
    "scores": {"note_accuracy": 0.0, "pitch_accuracy": 0.0, "rhythm_accuracy": 0.0, "overall": 0.0},
    "total_notes_gt": 0,
    "total_notes_matched": 0,
    "is_perfect": False,
    # ... other fields with default values
}
```

**Issue 4**: **Missing import ordering convention**
The plan mentions following import ordering conventions (stdlib → third-party → internal) but the current `comparator.py` has mixed import ordering.

**Severity**: LOW  
**Location**: Import statements in comparator.py  
**Fix**: Reorder imports to follow the convention: standard library, third-party, internal.

**Issue 5**: **Incomplete measures validation**
The current validation checks that measures contain at least one child element, but doesn't specifically validate that measures containing only rests are acceptable. While this may work in practice, the explicit mention in the plan suggests there might be an edge case that needs addressing.

**Severity**: MEDIUM  
**Location**: Measure validation logic in validator.py  
**Fix**: Add explicit validation for measures containing only rests as valid.

The main blocking issues are #2 and #3, which would cause inconsistent behavior with namespaces and improper error handling that could break the test harness expectations. These must be addressed before proceeding with implementation.

## Signoffs
- reviewer (Priya Kapoor): REJECTED — Blocking issues found that must be addressed before build.
- reviewer (Priya Kapoor): REJECTED — Blocking issues found that must be addressed before the build can proceed.
- reviewer (Priya Kapoor): REJECTED — Blocking issues found that must be addressed before build.
- architect (Jesse Korbin): REJECTED — Not ready. Several critical issues need to be addressed before build.
- specialist (Arjun Patel): REJECTED — Let me review the plan thoroughly by examining the current codebase implementation to understand what's already in place and what needs to be fixed.Let me examine the core files to understand the curr