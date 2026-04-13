# Enhance Rhythm and Duration Extraction - Implementation Plan

## Overview
This plan details the implementation of the "Enhance rhythm and duration extraction" feature for the ScoreForge project. The focus is on improving accuracy for complex rhythms, tuplets, and compound meters by enhancing divisions handling and time modification elements processing.

## Current State Analysis

### Key Files Identified
1. **core/extractor.py** - Contains extraction logic and duration inference
2. **models/note.py** - Defines Note class with duration handling
3. **models/measure.py** - Defines Measure class including divisions attribute
4. **core/musicxml_builder.py** - Builds MusicXML output including time-modification elements
5. **tests/test_extraction_quality.py** - Tests for extraction quality assessment
6. **tests/test_multi_voice.py** - Tests for multi-voice scenarios

### Current Implementation Details
- **Duration Calculation**: Uses `_infer_duration()` function in extractor.py
- **Divisions Handling**: Currently hardcoded to 4 in `_build_score()` (line 619)
- **Tuplet Processing**: Supports tuplets via `tuplet_actual`, `tuplet_normal`, `tuplet_start`, `tuplet_stop` fields
- **Time Modification**: Built into MusicXML via `time-modification` elements in musicxml_builder.py
- **Limitations**: Fixed divisions=4 limits precision for complex rhythms and tuplets

## Enhancement Goals
1. Improve duration extraction accuracy for complex rhythms
2. Enhance tuplets handling (triplets, quintuplets, etc.)
3. Better support for compound meters (6/8, 9/8, etc.)
4. Dynamic division selection based on rhythmic complexity
5. Preserve existing functionality while extending capabilities

## Implementation Plan

### Phase 1: Dynamic Division Selection
**Objective**: Replace hardcoded divisions=4 with intelligent division selection based on detected rhythmic complexity.

**Changes Required**:
1. **core/extractor.py**:
   - Modify `_build_score()` function to calculate optimal divisions
   - Add function to analyze note types and determine required divisions
   - Update `_build_note()` to use dynamic divisions

2. **models/measure.py**:
   - Keep divisions attribute but allow dynamic assignment

**Acceptance Criteria**:
- Divisions automatically scale to accommodate smallest note value detected
- Minimum divisions = 1, maximum reasonable limit (e.g., 96 for 64th note triplets)
- Existing functionality preserved when complexity doesn't require higher divisions

### Phase 2: Enhanced Tuplet Processing
**Objective**: Improve tuplet detection and handling for various tuplet types and nested tuplets.

**Changes Required**:
1. **core/extractor.py**:
   - Enhance DETAIL_PROMPT to improve tuplet detection instructions
   - Add validation for tuplet ratios in `_build_note()`
   - Support for nested tuplet detection

2. **core/musicxml_builder.py**:
   - Verify proper time-modification element generation for complex tuplets

**Acceptance Criteria**:
- Correct handling of common tuplets: triplets (3:2), quintuplets (5:4), septuplets (7:4)
- Proper handling of nested tuplets when detected
- Validation that tuplet ratios produce musically correct durations

### Phase 3: Compound Meter Support
**Objective**: Improve handling of compound meters (6/8, 9/8, 12/8) through better beat subdivision understanding.

**Changes Required**:
1. **core/extractor.py**:
   - Enhance duration calculation logic for compound meters
   - Update STRUCTURE_PROMPT and DETAIL_PROMPT with compound meter guidance

2. **models/measure.py**:
   - No changes needed (time signature already supported)

**Acceptance Criteria**:
- Correct duration interpretation in compound meters
- Proper beat grouping recognition (e.g., 6/8 as two groups of three eighth notes)

### Phase 4: Duration Validation and Correction
**Objective**: Add post-processing validation to detect and correct duration errors.

**Changes Required**:
1. **core/extractor.py**:
   - Add duration validation pass after initial extraction
   - Implement correction algorithms for common rhythm errors
   - Add cross-verification with beat structure

**Acceptance Criteria**:
- Detect duration sums that don't match time signature expectations
- Apply corrections for common OCR misreads (e.g., misreading dotted rhythms)
- Maintain backward compatibility

## Risk Assessment and Mitigation

### Risks:
1. **Backward Compatibility**: Changes could break existing functionality
2. **Performance Impact**: More complex calculations could slow processing
3. **Over-engineering**: Complexity might not be needed for all use cases
4. **False Precision**: Higher divisions might not improve accuracy if OCR isn't precise enough

### Mitigation Strategies:
1. **Comprehensive Testing**: Ensure all existing tests pass before and after changes
2. **Gradual Implementation**: Implement phases separately with testing between each
3. **Configuration Options**: Allow disabling enhancements for simple use cases
4. **Performance Monitoring**: Benchmark key operations to ensure acceptable performance

## Edge Cases to Consider
1. Mixed tuplets and regular notes in same measure
2. Nested tuplets (tuplets within tuplets)
3. Complex rhythms with mixed note values (e.g., quintuplets with sixteenth notes)
4. Changing time signatures within a piece
5. Pickup measures (anacrusis)
6. Measures with only rests or incomplete beats
7. Extremely high division requirements (rare but possible)
8. Ambiguous tuplet notation that could be interpreted multiple ways

## Testing Strategy
1. **Unit Tests**: Test individual functions (_infer_duration, division calculation)
2. **Integration Tests**: Test end-to-end extraction with enhanced features
3. **Regression Tests**: Ensure existing functionality remains intact
4. **Edge Case Tests**: Specific tests for tuplets, compounders, complex rhythms
5. **Validation Tests**: Compare output against known good MusicXML files

## Implementation Sequence
1. Phase 1: Dynamic Division Selection
2. Phase 2: Enhanced Tuplet Processing  
3. Phase 3: Compound Meter Support
4. Phase 4: Duration Validation and Correction
5. Testing and Validation
6. Documentation Updates

## Success Metrics
1. Improved accuracy on complex rhythm test cases
2. Maintained or improved performance on simple cases
3. All existing tests continue to pass
4. Successful handling of edge cases identified in testing
5. Proper MusicXML output validation
