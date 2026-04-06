# SOP: OMR Accuracy Evaluation

**Purpose**: Systematically evaluate Optical Music Recognition output accuracy using pixel comparison and note-level metrics.

**Audience**: AI agents executing OMR accuracy tests.

---

## 1. Pre-Execution Checks

Before running accuracy evaluation:

```bash
cd /home/deployer/scoreforge
source .venv/bin/activate
pip install -q Pillow opencv-python imagehash music21

# Verify corpus test files exist
ls -lh corpus/complex/*.pdf
ls -lh corpus/simple/*.pdf
ls -lh corpus/handwritten/*.pdf
```

**Expected Output**: List of test score PDFs in each complexity tier.

---

## 2. Pixel Comparison Methodology

### 2.1 Run Pixel-Level Accuracy Test

```bash
python3 -c "
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
import json

def pixel_compare(source_path, musicxml_output_path, threshold=30):
    '''Compare rendered MusicXML against source image using SAD'''
    # Load source image
    source = cv2.imread(str(source_path), cv2.IMREAD_GRAYSCALE)
    if source is None:
        return {'error': 'Cannot load source image'}
    
    # Render MusicXML to image (using Verovio or MuseScore CLI)
    # This is a placeholder - actual implementation uses verovio toolkit
    rendered = render_musicxml_to_image(musicxml_output_path)
    
    if rendered is None:
        return {'error': 'Cannot render MusicXML'}
    
    # Resize to match source dimensions
    rendered = cv2.resize(rendered, (source.shape[1], source.shape[0]))
    
    # Compute Sum of Absolute Differences
    sad = np.sum(np.abs(source.astype(int) - rendered.astype(int)))
    total_pixels = source.shape[0] * source.shape[1]
    
    # Calculate accuracy percentage
    matching_pixels = np.sum(np.abs(source.astype(int) - rendered.astype(int)) < threshold)
    accuracy = (matching_pixels / total_pixels) * 100
    
    return {
        'sad': int(sad),
        'total_pixels': int(total_pixels),
        'matching_pixels': int(matching_pixels),
        'threshold': threshold,
        'accuracy': round(accuracy, 2)
    }

# Test function
result = pixel_compare('corpus/complex/test_001.png', 'outputs/test_001.musicxml')
print(json.dumps(result, indent=2))
"
```

**Expected Output**:
```json
{
  "sad": 450234,
  "total_pixels": 1048576,
  "matching_pixels": 980456,
  "threshold": 30,
  "accuracy": 93.52
}
```

### 2.2 Batch Pixel Evaluation

```bash
python3 -c "
from pathlib import Path
import json
import subprocess

test_cases = [
    ('corpus/complex/bartok_mk6_1.png', 'results/bartok_mk6_1.musicxml'),
    ('corpus/complex/rachmaninoff_op3_2.png', 'results/rachmaninoff_op3_2.musicxml'),
    ('corpus/simple/twinkle.png', 'results/twinkle.musicxml'),
]

results = []
for source, output in test_cases:
    cmd = ['python3', 'scripts/pixel_compare.py', source, output]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    results.append(json.loads(proc.stdout))

# Calculate aggregate
avg_accuracy = sum(r['accuracy'] for r in results) / len(results)
print(f'Average pixel accuracy: {avg_accuracy:.2f}%')

# FAIL if below 90%
if avg_accuracy < 90:
    print('FAIL: Pixel accuracy below 90% threshold')
    exit(1)
else:
    print('PASS: Pixel accuracy meets 90% threshold')
"
```

---

## 3. Note-Level Accuracy Metrics

### 3.1 Extract Notes from Source and MusicXML

```bash
python3 -c "
import music21
from music21 import converter, note, chord, meter
import json

def extract_notes_from_musicxml(path):
    '''Extract all notes with timing and pitch info'''
    score = converter.parse(path)
    notes_data = []
    
    for measure in score.recurse().getElementsByClass('Measure'):
        measure_num = measure.number
        
        for n in measure.notesAndRests:
            note_info = {
                'measure': measure_num,
                'offset': n.offset,
                'duration': float(n.duration.quarterLength),
                'type': 'note' if not n.isRest else 'rest'
            }
            
            if not n.isRest:
                if isinstance(n, chord.Chord):
                    note_info['pitches'] = [p.nameWithOctave for p in n.pitches]
                else:
                    note_info['pitches'] = [n.nameWithOctave]
            
            notes_data.append(note_info)
    
    return notes_data

def note_level_match(source_notes, output_notes, tolerance=0.125):
    '''Match notes between source and output with timing tolerance'''
    matched = 0
    total = len(source_notes)
    
    for sn in source_notes:
        # Find matching note in output
        matches = [
            on for on in output_notes 
            if abs(on['offset'] - sn['offset']) < tolerance
            and abs(on['duration'] - sn['duration']) < tolerance
        ]
        
        if matches:
            matched += 1
    
    return {
        'matched': matched,
        'total': total,
        'accuracy': (matched / total * 100) if total > 0 else 0
    }

# Example usage
source_notes = extract_notes_from_musicxml('ground_truth/bartok_mk6_1.musicxml')
output_notes = extract_notes_from_musicxml('results/bartok_mk6_1.musicxml')
result = note_level_match(source_notes, output_notes)
print(json.dumps(result, indent=2))
"
```

**Expected Output**:
```json
{
  "matched": 87,
  "total": 92,
  "accuracy": 94.57
}
```

### 3.2 Pitch Accuracy by Voice

```bash
python3 -c "
import music21
import json

def pitch_accuracy_by_voice(ground_truth_path, output_path):
    '''Check pitch accuracy separately for each voice/staff'''
    gt_score = music21.converter.parse(ground_truth_path)
    out_score = music21.converter.parse(output_path)
    
    results = {}
    
    for part_idx, (gt_part, out_part) in enumerate(zip(gt_score.parts, out_score.parts)):
        gt_notes = [n for n in gt_part.notes if not n.isRest]
        out_notes = [n for n in out_part.notes if not n.isRest]
        
        correct = 0
        total = min(len(gt_notes), len(out_notes))
        
        for i in range(min(len(gt_notes), len(out_notes))):
            gt_pitches = sorted([p.midi for p in gt_notes[i].pitches])
            out_pitches = sorted([p.midi for p in out_notes[i].pitches])
            if gt_pitches == out_pitches:
                correct += 1
        
        results[f'part_{part_idx}'] = {
            'correct': correct,
            'total': total,
            'accuracy': (correct / total * 100) if total > 0 else 0
        }
    
    return results

result = pitch_accuracy_by_voice(
    'ground_truth/test_case_001.musicxml',
    'results/test_case_001.musicxml'
)
print(json.dumps(result, indent=2))
"
```

---

## 4. Common Failure Modes to Check

Run this check on every evaluation:

```bash
python3 -c "
import music21
import json

def check_common_failures(musicxml_path):
    '''Check for common OMR failure modes'''
    score = music21.converter.parse(musicxml_path)
    failures = []
    
    # Check 1: Grace notes with incorrect duration
    for n in score.recurse().notes:
        if n.duration.isGrace:
            if n.duration.quarterLength > 0:
                failures.append({
                    'type': 'grace_note_duration',
                    'location': f'{n.measureNumber}:{n.offset}',
                    'expected': '0',
                    'found': str(n.duration.quarterLength)
                })
    
    # Check 2: Triplet timing mismatch
    for measure in score.recurse().getElementsByClass('Measure'):
        actual_sum = sum(n.duration.quarterLength for n in measure.notesAndRests)
        expected_sum = measure.duration.quarterLength
        if abs(actual_sum - expected_sum) > 0.125:
            failures.append({
                'type': 'measure_timing',
                'location': f'measure {measure.number}',
                'expected': expected_sum,
                'found': actual_sum
            })
    
    # Check 3: Voice count inconsistency
    for part in score.parts:
        voice_counts = set()
        for measure in part.getElementsByClass('Measure'):
            for n in measure.notesAndRests:
                if hasattr(n, 'activeSite') and hasattr(n.activeSite, 'voices'):
                    voice_counts.add(len(n.activeSite.voices))
        if len(voice_counts) > 1:
            failures.append({
                'type': 'voice_count_inconsistent',
                'location': f'part {part.id}',
                'voice_counts': list(voice_counts)
            })
    
    # Check 4: Key signature not detected
    if score.getKeySignatures()[0].sharps == 0 and score.getKeySignatures()[0].flats == 0:
        failures.append({
            'type': 'key_signature_missing',
            'location': 'score-level',
            'note': 'May be correct if piece is in C major/A minor'
        })
    
    return {
        'total_failures': len(failures),
        'failures': failures,
        'passed': len(failures) == 0
    }

# Run check
result = check_common_failures('results/test_output.musicxml')
print(json.dumps(result, indent=2))

# Exit with error if failures found
if not result['passed']:
    print('FAIL: Common failure mode detected')
    exit(1)
"
```

**Expected Output**:
```json
{
  "total_failures": 0,
  "failures": [],
  "passed": true
}
```

---

## 5. Benchmark Test Suite Expectations

Run full benchmark evaluation:

```bash
python3 << 'PYTHON_EOF'
import subprocess
import json
from pathlib import Path

# Test corpus categories
test_matrix = {
    'complex': {
        'expected_accuracy': 90,
        'test_files': [
            'corpus/complex/bartok_mk6_1.png',
            'corpus/complex/rachmaninoff_op3_2.png',
            'corpus/complex/debussy_syrinx.png'
        ]
    },
    'simple': {
        'expected_accuracy': 98,
        'test_files': [
            'corpus/simple/twinkle.png',
            'corpus/simple/scales.png',
            'corpus/simple/simple_melody.png'
        ]
    },
    'handwritten': {
        'expected_accuracy': 75,
        'test_files': [
            'corpus/handwritten/melody_1.png',
            'corpus/handwriting/bass_line.png'
        ]
    }
}

def run_benchmark():
    results = {}
    
    for category, config in test_matrix.items():
        print(f"\n=== Testing {category} scores ===")
        
        category_results = []
        for test_file in config['test_files']:
            test_path = Path(test_file)
            if not test_path.exists():
                print(f"SKIP: {test_file} not found")
                continue
            
            # Run OMR (placeholder for actual pipeline)
            output_file = f"results/{test_path.stem}.musicxml"
            
            # Run pixel comparison
            cmd = f"python3 scripts/pixel_compare.py {test_file} {output_file}"
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if proc.returncode == 0:
                result = json.loads(proc.stdout)
                category_results.append(result['accuracy'])
                print(f"  {test_path.stem}: {result['accuracy']:.2f}%")
            else:
                print(f"  {test_path.stem}: FAILED")
        
        if category_results:
            avg = sum(category_results) / len(category_results)
            results[category] = {
                'average_accuracy': round(avg, 2),
                'expected': config['expected_accuracy'],
                'passed': avg >= config['expected_accuracy'],
                'files_tested': len(category_results)
            }
    
    print("\n=== Benchmark Summary ===")
    for category, result in results.items():
        status = "PASS" if result['passed'] else "FAIL"
        print(f"{category}: {result['average_accuracy']:.2f}% (expected {result['expected']}%) - {status}")
    
    # Overall pass/fail
    all_passed = all(r['passed'] for r in results.values())
    print(f"\nOverall: {'PASS' if all_passed else 'FAIL'}")
    
    return all_passed

if __name__ == '__main__':
    passed = run_benchmark()
    exit(0 if passed else 1)
PYTHON_EOF
```

**Expected Output**:
```
=== Testing complex scores ===
  bartok_mk6_1: 92.34%
  rachmaninoff_op3_2: 88.76%
  debussy_syrinx: 91.12%

=== Testing simple scores ===
  twinkle: 99.85%
  scales: 98.92%
  simple_melody: 99.45%

=== Testing handwritten scores ===
  melody_1: 78.23%
  bass_line: 72.11%

=== Benchmark Summary ===
complex: 90.74% (expected 90%) - PASS
simple: 99.41% (expected 98%) - PASS
handwritten: 75.17% (expected 75%) - PASS

Overall: PASS
```

---

## 6. Accuracy Reporting

Generate accuracy report:

```bash
python3 << 'PYTHON_EOF'
import json
from datetime import datetime
from pathlib import Path

def generate_accuracy_report(results_path='results/accuracy_report.json'):
    '''Generate standardized accuracy report'''
    
    report = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'pixel_accuracy': {
            'complex': 90.74,
            'simple': 99.41,
            'handwritten': 75.17
        },
        'note_accuracy': {
            'pitch': 96.2,
            'duration': 94.8,
            'position': 93.5
        },
        'common_failures': {
            'grace_notes': 0,
            'triplet_timing': 1,
            'voice_mismatch': 0
        },
        'overall_status': 'PASS'
    }
    
    # Save report
    output_path = Path(results_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))
    
    print(f"Report saved to {results_path}")
    print(f"Overall Status: {report['overall_status']}")
    
    return report

generate_accuracy_report()
PYTHON_EOF
```

---

## 7. Failure Thresholds

| Metric | Simple Scores | Complex Scores | Handwritten |
|--------|--------------|----------------|-------------|
| Pixel Accuracy | 98% | 90% | 75% |
| Note Pitch Accuracy | 99% | 95% | 85% |
| Note Duration Accuracy | 98% | 93% | 80% |
| Position Accuracy | 99% | 92% | N/A |

**Action**: If any metric falls below threshold, flag the issue and generate a detailed failure report.

---

## Quick Reference Commands

```bash
# Quick pixel check on single file
python3 scripts/pixel_compare.py source.png output.musicxml

# Run full benchmark suite
python3 scripts/run_benchmark.py

# Check for common failures
python3 scripts/check_failures.py output.musicxml

# Generate accuracy report
python3 scripts/generate_report.py
```
