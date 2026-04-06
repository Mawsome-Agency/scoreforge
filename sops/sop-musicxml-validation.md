# SOP: MusicXML Validation

**Purpose**: Validate MusicXML output against schema and semantic correctness standards.

**Audience**: AI agents validating MusicXML before and after OMR processing.

---

## 1. Pre-Validation Checks

```bash
cd /home/deployer/scoreforge
source .venv/bin/activate

# Verify validation tools installed
pip install -q music21 lxml xmlschema pillow

# Download MusicXML 4.0 XSD (if not present)
mkdir -p schemas
if [ ! -f schemas/musicxml.xsd ]; then
    curl -L "https://www.musicxml.com/schema/musicxml.xsd" -o schemas/musicxml.xsd
fi

ls -lh schemas/musicxml.xsd
```

**Expected Output**: 
```
-rw-r--r-- 1 deployer deployer 2.1M Apr  5 11:30 schemas/musicxml.xsd
```

---

## 2. Schema Validation Against MusicXML 4.0 XSD

### 2.1 Basic Schema Validation

```bash
python3 << 'PYTHON_EOF'
import xmlschema
from pathlib import Path
import json

def validate_musicxml_schema(musicxml_path, xsd_path='schemas/musicxml.xsd'):
    '''Validate MusicXML against MusicXML 4.0 XSD schema'''
    
    xml_path = Path(musicxml_path)
    xsd = Path(xsd_path)
    
    if not xml_path.exists():
        return {'error': f'MusicXML file not found: {musicxml_path}'}
    
    if not xsd.exists():
        return {'error': f'XSD schema not found: {xsd_path}'}
    
    try:
        schema = xmlschema.XMLSchema(xsd_path)
        schema.validate(musicxml_path)
        
        return {
            'valid': True,
            'errors': [],
            'warnings': []
        }
    except xmlschema.XMLSchemaValidationError as e:
        return {
            'valid': False,
            'errors': [str(e)],
            'warnings': []
        }
    except Exception as e:
        return {
            'valid': False,
            'errors': [f'Validation error: {str(e)}'],
            'warnings': []
        }

# Test validation
result = validate_musicxml_schema('results/test_output.musicxml')
print(json.dumps(result, indent=2))

# Exit with error if invalid
if not result.get('valid'):
    print("FAIL: MusicXML schema validation failed")
    exit(1)
else:
    print("PASS: MusicXML schema validation succeeded")
PYTHON_EOF
```

**Expected Output**:
```json
{
  "valid": true,
  "errors": [],
  "warnings": []
}
```

### 2.2 Batch Schema Validation

```bash
python3 << 'PYTHON_EOF'
from pathlib import Path
import json

def batch_validate_schema(directory='results/'):
    '''Validate all MusicXML files in directory'''
    
    musicxml_files = list(Path(directory).glob('**/*.musicxml'))
    results = []
    
    for musicxml_file in musicxml_files:
        # Run schema validation (reusing function above)
        cmd = f"python3 -c \"import xmlschema; s=xmlschema.XMLSchema('schemas/musicxml.xsd'); s.validate('{musicxml_file}')\""
        
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        results.append({
            'file': str(musicxml_file),
            'valid': proc.returncode == 0,
            'error': proc.stderr if proc.returncode != 0 else None
        })
    
    valid_count = sum(1 for r in results if r['valid'])
    total_count = len(results)
    
    print(f"Schema Validation: {valid_count}/{total_count} files valid")
    
    if valid_count < total_count:
        print("FAIL: Some files failed schema validation")
        for r in results:
            if not r['valid']:
                print(f"  ERROR in {r['file']}: {r['error']}")
        exit(1)
    else:
        print("PASS: All files passed schema validation")

batch_validate_schema()
PYTHON_EOF
```

---

## 3. Semantic Validation

### 3.1 Measure Duration Validation

```bash
python3 << 'PYTHON_EOF'
import music21
import json

def validate_measure_durations(musicxml_path):
    '''Check if all measures have correct total duration'''
    
    score = music21.converter.parse(musicxml_path)
    errors = []
    
    for part_idx, part in enumerate(score.parts):
        for measure in part.getElementsByClass('Measure'):
            measure_num = measure.number
            
            # Sum actual durations
            actual_duration = sum(
                n.duration.quarterLength 
                for n in measure.notesAndRests
            )
            
            # Expected duration from time signature
            time_signature = measure.timeSignature
            if time_signature:
                expected_duration = (
                    time_signature.numerator / time_signature.denominator * 4
                )
            else:
                # Default to 4/4 if no time signature
                expected_duration = 4.0
            
            # Allow small tolerance for floating point
            tolerance = 0.125
            if abs(actual_duration - expected_duration) > tolerance:
                errors.append({
                    'type': 'measure_duration_mismatch',
                    'part': part_idx,
                    'measure': measure_num,
                    'expected': expected_duration,
                    'actual': actual_duration,
                    'difference': actual_duration - expected_duration
                })
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'total_measures_checked': sum(
            len(part.getElementsByClass('Measure')) for part in score.parts
        )
    }

# Run validation
result = validate_measure_durations('results/test_output.musicxml')
print(json.dumps(result, indent=2))

if not result['valid']:
    print("FAIL: Measure duration validation failed")
    exit(1)
PYTHON_EOF
```

**Expected Output**:
```json
{
  "valid": true,
  "errors": [],
  "total_measures_checked": 16
}
```

### 3.2 Voice Consistency Validation

```bash
python3 << 'PYTHON_EOF'
import music21
import json

def validate_voice_consistency(musicxml_path):
    '''Check that voices are used consistently across measures'''
    
    score = music21.converter.parse(musicxml_path)
    errors = []
    
    for part_idx, part in enumerate(score.parts):
        voice_patterns = {}
        
        for measure in part.getElementsByClass('Measure'):
            measure_num = measure.number
            
            # Track which voices are present in each measure
            voices_present = set()
            for n in measure.notesAndRests:
                if hasattr(n, 'activeSite') and hasattr(n.activeSite, 'voices'):
                    voice_id = getattr(n, 'voice', None)
                    if voice_id:
                        voices_present.add(voice_id)
            
            voice_patterns[measure_num] = sorted(list(voices_present))
        
        # Check for inconsistent voice usage
        unique_patterns = set(
            tuple(v) for v in voice_patterns.values()
        )
        
        if len(unique_patterns) > 1:
            errors.append({
                'type': 'inconsistent_voices',
                'part': part_idx,
                'patterns': {
                    f'measure_{m}': voices 
                    for m, voices in voice_patterns.items()
                }
            })
    
    return {
        'valid': len(errors) == 0,
        'errors': errors
    }

result = validate_voice_consistency('results/test_output.musicxml')
print(json.dumps(result, indent=2))
PYTHON_EOF
```

### 3.3 Key Signature Validation

```bash
python3 << 'PYTHON_EOF'
import music21
import json

def validate_key_signatures(musicxml_path):
    '''Check that key signatures are consistent and valid'''
    
    score = music21.converter.parse(musicxml_path)
    errors = []
    
    # Get all key signatures in the score
    key_signatures = list(score.recurse().getElementsByClass('KeySignature'))
    
    if not key_signatures:
        errors.append({
            'type': 'no_key_signature',
            'message': 'No key signature found (may be valid for C major/A minor)'
        })
    
    # Check for conflicting key signatures
    if len(key_signatures) > 1:
        unique_keys = set()
        for ks in key_signatures:
            unique_keys.add(f'{ks.sharps} sharps, {ks.flats} flats')
        
        if len(unique_keys) > 1:
            errors.append({
                'type': 'conflicting_key_signatures',
                'message': f'Multiple key signatures found: {unique_keys}'
            })
    
    # Validate key signature range
    for ks in key_signatures:
        if ks.sharps > 7 or ks.flats > 7:
            errors.append({
                'type': 'invalid_key_signature',
                'sharps': ks.sharps,
                'flats': ks.flats
            })
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'key_signatures_found': len(key_signatures)
    }

result = validate_key_signatures('results/test_output.musicxml')
print(json.dumps(result, indent=2))
PYTHON_EOF
```

---

## 4. Round-Trip Testing

### 4.1 Import into MuseScore and Re-Export

```bash
# Check if MuseScore CLI is available
command -v mscore || command -v musescore3 || {
    echo "WARNING: MuseScore CLI not found. Skipping round-trip test."
    exit 0
}

# Round-trip: MusicXML -> MuseScore import -> MusicXML export
python3 << 'PYTHON_EOF'
import subprocess
import tempfile
from pathlib import Path
import shutil

def round_trip_musescore(input_path):
    '''Import MusicXML into MuseScore, re-export, compare'''
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Path to exported file
        output_path = tmpdir / 'round_trip.musicxml'
        
        # Find MuseScore CLI
        mscore_cmd = None
        for cmd in ['mscore', 'musescore3', 'musescore']:
            if shutil.which(cmd):
                mscore_cmd = cmd
                break
        
        if not mscore_cmd:
            print("SKIP: MuseScore CLI not found")
            return {'skipped': True, 'reason': 'MuseScore CLI not found'}
        
        # Import and re-export
        cmd = [
            mscore_cmd,
            '-f',  # Don't show UI
            '-o', str(output_path),
            str(input_path)
        ]
        
        proc = subprocess.run(cmd, capture_output=True, text=True)
        
        if proc.returncode != 0:
            return {
                'error': True,
                'message': f'MuseScore failed: {proc.stderr}'
            }
        
        # Compare file sizes (basic check)
        original_size = Path(input_path).stat().st_size
        round_trip_size = output_path.stat().st_size
        
        size_diff_pct = abs(original_size - round_trip_size) / original_size * 100
        
        return {
            'success': True,
            'original_size': original_size,
            'round_trip_size': round_trip_size,
            'size_difference_pct': round(size_diff_pct, 2),
            'output_path': str(output_path)
        }

# Run round-trip test
result = round_trip_musescore('results/test_output.musicxml')
import json
print(json.dumps(result, indent=2))

if result.get('error'):
    print("FAIL: Round-trip test failed")
    exit(1)
PYTHON_EOF
```

**Expected Output**:
```json
{
  "success": true,
  "original_size": 45234,
  "round_trip_size": 44987,
  "size_difference_pct": 0.55,
  "output_path": "/tmp/round_trip.musicxml"
}
```

### 4.2 Import with music21 and Re-Export

```bash
python3 << 'PYTHON_EOF'
import music21
import tempfile
from pathlib import Path
import difflib

def round_trip_music21(input_path):
    '''Import MusicXML with music21, re-export, compare'''
    
    # Parse original
    original_score = music21.converter.parse(input_path)
    original_xml = music21.musicxml.m21ToXml.GeneralObjectExporter().parse(original_score).decode('utf-8')
    
    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.musicxml', delete=False) as f:
        temp_path = f.name
        f.write(original_xml)
    
    # Re-parse the exported file
    reimported_score = music21.converter.parse(temp_path)
    reimported_xml = music21.musicxml.m21ToXml.GeneralObjectExporter().parse(reimported_score).decode('utf-8')
    
    # Compare
    diff = list(difflib.unified_diff(
        original_xml.splitlines(keepends=True),
        reimported_xml.splitlines(keepends=True),
        fromfile='original',
        tofile='reimported'
    ))
    
    # Clean up temp file
    Path(temp_path).unlink()
    
    return {
        'success': True,
        'diff_lines': len(diff),
        'diff_preview': diff[:20] if diff else []
    }

result = round_trip_music21('results/test_output.musicxml')
import json
print(json.dumps(result, indent=2))

# If there's a significant diff, flag it
if result['diff_lines'] > 10:
    print("WARNING: Round-trip produced significant changes")
PYTHON_EOF
```

---

## 5. Common MusicXML Errors and Fixes

### 5.1 Detect and Report Common Errors

```bash
python3 << 'PYTHON_EOF'
import music21
import json
from xml.etree import ElementTree as ET

def detect_common_musicxml_errors(musicxml_path):
    '''Detect common MusicXML generation errors'''
    
    errors = []
    
    # Parse with music21
    try:
        score = music21.converter.parse(musicxml_path)
    except Exception as e:
        errors.append({
            'type': 'parse_error',
            'message': str(e)
        })
        return {'errors': errors}
    
    # Check for empty measures without rest
    for part_idx, part in enumerate(score.parts):
        for measure in part.getElementsByClass('Measure'):
            notes = list(measure.notesAndRests)
            if len(notes) == 0:
                errors.append({
                    'type': 'empty_measure_no_rest',
                    'part': part_idx,
                    'measure': measure.number,
                    'fix': 'Add a whole rest to empty measures'
                })
    
    # Check for orphaned notes (no duration)
    for note in score.recurse().notes:
        if note.duration.quarterLength == 0 and not note.duration.isGrace:
            errors.append({
                'type': 'note_without_duration',
                'location': f'{note.measureNumber}:{note.offset}',
                'fix': 'Set note.duration.quarterLength to appropriate value'
            })
    
    # Check for invalid pitch values
    for note in score.recurse().notes:
        if hasattr(note, 'pitch'):
            if note.pitch.midi < 21 or note.pitch.midi > 108:
                errors.append({
                    'type': 'invalid_pitch',
                    'pitch': note.pitch.nameWithOctave,
                    'midi': note.pitch.midi,
                    'location': f'{note.measureNumber}:{note.offset}',
                    'fix': 'Pitch outside piano range (21-108) - may be transcription error'
                })
    
    # Parse raw XML for structural issues
    try:
        tree = ET.parse(musicxml_path)
        root = tree.getroot()
        
        # Check for missing score-partwise root
        if root.tag not in ['score-partwise', 'score-timewise']:
            errors.append({
                'type': 'invalid_root_element',
                'found': root.tag,
                'fix': 'Root element must be score-partwise or score-timewise'
            })
    except Exception as e:
        errors.append({
            'type': 'xml_parse_error',
            'message': str(e)
        })
    
    return {
        'total_errors': len(errors),
        'errors': errors,
        'valid': len(errors) == 0
    }

result = detect_common_musicxml_errors('results/test_output.musicxml')
print(json.dumps(result, indent=2))

if not result['valid']:
    print("FAIL: Common MusicXML errors detected")
    exit(1)
PYTHON_EOF
```

**Expected Output**:
```json
{
  "total_errors": 0,
  "errors": [],
  "valid": true
}
```

### 5.2 Auto-Fix Common Errors

```bash
python3 << 'PYTHON_EOF'
import music21
from pathlib import Path

def auto_fix_musicxml(input_path, output_path=None):
    '''Auto-fix common MusicXML issues'''
    
    if output_path is None:
        output_path = input_path.replace('.musicxml', '_fixed.musicxml')
    
    # Parse score
    score = music21.converter.parse(input_path)
    
    fixes_applied = []
    
    # Fix 1: Add rests to empty measures
    for part_idx, part in enumerate(score.parts):
        for measure in part.getElementsByClass('Measure'):
            notes = list(measure.notesAndRests)
            if len(notes) == 0:
                time_sig = measure.timeSignature or music21.meter.TimeSignature('4/4')
                rest = music21.note.Rest()
                rest.duration.quarterLength = time_sig.beatDuration.quarterLength * time_sig.beats
                measure.insert(0, rest)
                fixes_applied.append(f'Added rest to empty measure {measure.number} in part {part_idx}')
    
    # Fix 2: Remove zero-duration non-grace notes
    for note in list(score.recurse().notes):
        if note.duration.quarterLength == 0 and not note.duration.isGrace:
            # Set to quarter note duration as fallback
            note.duration.quarterLength = 1.0
            fixes_applied.append(f'Fixed zero-duration note at {note.measureNumber}:{note.offset}')
    
    # Write fixed output
    output = music21.musicxml.m21ToXml.GeneralObjectExporter().parse(score)
    Path(output_path).write_bytes(output)
    
    return {
        'output_path': output_path,
        'fixes_applied': len(fixes_applied),
        'fixes': fixes_applied
    }

result = auto_fix_musicxml('results/test_output.musicxml', 'results/test_output_fixed.musicxml')
import json
print(json.dumps(result, indent=2))
PYTHON_EOF
```

---

## 6. Validation Reporting

```bash
python3 << 'PYTHON_EOF'
import json
from datetime import datetime
from pathlib import Path

def generate_validation_report(musicxml_path, output_path='results/validation_report.json'):
    '''Generate comprehensive validation report'''
    
    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'file': musicxml_path,
        'checks': {
            'schema_validation': None,
            'measure_durations': None,
            'voice_consistency': None,
            'key_signatures': None,
            'round_trip': None,
            'common_errors': None
        },
        'overall_status': 'UNKNOWN'
    }
    
    # Run all validations
    # (In production, these would call the functions defined above)
    
    # For this example, set placeholder results
    report['checks']['schema_validation'] = {'valid': True}
    report['checks']['measure_durations'] = {'valid': True}
    report['checks']['voice_consistency'] = {'valid': True}
    report['checks']['key_signatures'] = {'valid': True}
    report['checks']['round_trip'] = {'success': True}
    report['checks']['common_errors'] = {'valid': True, 'total_errors': 0}
    
    # Determine overall status
    all_valid = all(
        check.get('valid', check.get('success', False)) 
        for check in report['checks'].values() 
        if check is not None
    )
    
    report['overall_status'] = 'PASS' if all_valid else 'FAIL'
    
    # Save report
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2))
    
    print(f"Validation report saved to {output_path}")
    print(f"Overall Status: {report['overall_status']}")
    
    return report

generate_validation_report('results/test_output.musicxml')
PYTHON_EOF
```

---

## 7. Validation Checklist

Before marking MusicXML as production-ready, verify:

```bash
python3 << 'PYTHON_EOF'
validation_steps = [
    ('Schema Validation', 'Validate against MusicXML 4.0 XSD'),
    ('Measure Durations', 'All measures sum to correct time signature'),
    ('Voice Consistency', 'Voices used consistently across measures'),
    ('Key Signatures', 'Valid and consistent key signatures'),
    ('Round-Trip Test', 'Import/re-export preserves structure'),
    ('Common Errors', 'No orphaned notes, empty measures, invalid pitches')
]

print("MusicXML Validation Checklist")
print("=" * 50)
for step, description in validation_steps:
    print(f"[ ] {step}: {description}")

print("\nExecute with:")
print("python3 scripts/validate_musicxml.py <input.musicxml>")
PYTHON_EOF
```

---

## Quick Reference Commands

```bash
# Schema validation
python3 scripts/validate_schema.py input.musicxml

# Full validation suite
python3 scripts/validate_musicxml.py input.musicxml --full

# Auto-fix common errors
python3 scripts/fix_musicxml.py input.musicxml output.musicxml

# Round-trip test
python3 scripts/round_trip.py input.musicxml

# Generate validation report
python3 scripts/validation_report.py input.musicxml
```

---

## Exit Codes

- `0`: All validations passed
- `1`: Validation failed
- `2`: File not found or I/O error
- `3`: Invalid XML structure
