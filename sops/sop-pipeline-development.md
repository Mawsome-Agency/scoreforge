# SOP: Pipeline Development

**Purpose**: Standardized workflow for developing, testing, and benchmarking ScoreForge OMR pipeline components.

**Audience**: AI agents developing new pipeline features or notation type support.

---

## 1. Local Development Setup

### 1.1 Initialize Development Environment

```bash
cd /home/deployer/scoreforge

# Verify virtual environment
source .venv/bin/activate
python --version  # Should be 3.10+

# Verify dependencies installed
pip list | grep -E "(torch|opencv|music21|Pillow)"

# Verify test corpus structure
ls -la corpus/
tree -L 2 corpus/
```

**Expected Output**:
```
corpus/
├── simple/
│   ├── twinkle.pdf
│   ├── scales.pdf
│   └── ...
├── complex/
│   ├── bartok_mk6_1.pdf
│   ├── rachmaninoff_op3_2.pdf
│   └── ...
└── handwritten/
    ├── melody_1.jpg
    └── ...
```

### 1.2 Create Feature Branch

```bash
# Check current branch
git branch

# Create feature branch following naming convention
git checkout -b feature/notation-type-NAME

# Example for triplet support
git checkout -b feature/triplet-support

# Verify branch
git status
```

### 1.3 Set Up Development Config

```bash
# Copy dev config
cp .env.example .env.development

# Edit config for local testing
cat > .env.development << 'EOF'
# Development Configuration
LOG_LEVEL=DEBUG
MODEL_PATH=models/staff_detection_v1.pt
CORPUS_PATH=corpus/
OUTPUT_PATH=results/dev/
ENABLE_VISUALIZATION=true
EOF

# Source dev environment
export $(cat .env.development | xargs)
```

---

## 2. Test Score Corpus Management

### 2.1 Add New Test Scores to Corpus

```bash
python3 -c "
import shutil
from pathlib import Path
import json

def add_test_score(source_path, category, name, metadata=None):
    source = Path(source_path)
    if not source.exists():
        print(f'ERROR: Source file not found: {source_path}')
        return
    
    ext = source.suffix.lower()
    if ext not in ['.pdf', '.png', '.jpg', '.jpeg']:
        print(f'ERROR: Unsupported file type: {ext}')
        return
    
    safe_name = name.lower().replace(' ', '_').replace('-', '_')
    target_name = f'{safe_name}{ext}'
    target_path = Path(f'corpus/{category}/{target_name}')
    
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target_path)
    
    if metadata is None:
        metadata = {
            'name': name,
            'category': category,
            'added_date': '2026-04-05',
            'notation_types': ['notes', 'key_signature', 'time_signature'],
            'difficulty': 'intermediate'
        }
    else:
        metadata['added_date'] = '2026-04-05'
    
    metadata_path = target_path.with_suffix('.metadata.json')
    metadata_path.write_text(json.dumps(metadata, indent=2))
    
    print(f'Added test score: {target_path}')
    print(f'Metadata: {metadata_path}')
    return {
        'path': str(target_path),
        'metadata_path': str(metadata_path),
        'category': category
    }

# Example: Add a test score
result = add_test_score(
    '/path/to/new/score.pdf',
    'complex',
    'rachmaninoff_prelude_csharp_minor',
    metadata={
        'composer': 'Sergei Rachmaninoff',
        'title': 'Prelude in C-sharp Minor',
        'difficulty': 'advanced',
        'notation_types': [
            'notes', 'chords', 'triplets', 'grace_notes',
            'key_signature', 'time_signature', 'dynamics'
        ],
        'expected_accuracy': 88,
        'notes': 'Complex triplets and rapid arpeggios'
    }
)
"
```

### 2.2 List Corpus Test Scores

```bash
python3 -c "
from pathlib import Path
import json

corpus_path = Path('corpus')
categories = ['simple', 'complex', 'handwritten']

for category in categories:
    category_path = corpus_path / category
    if not category_path.exists():
        continue
    
    print(f'\n=== {category.upper()} ===')
    
    score_files = []
    for ext in ['.pdf', '.png', '.jpg', '.jpeg']:
        score_files.extend(category_path.glob(f'*{ext}'))
    
    for score_file in score_files:
        metadata_path = score_file.with_suffix('.metadata.json')
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        
        name = metadata.get('name', score_file.stem)
        composer = metadata.get('composer', 'Unknown')
        notation_types = metadata.get('notation_types', [])
        
        print(f'  • {name}')
        print(f'    File: {score_file.name}')
        print(f'    Composer: {composer}')
        notation_str = ', '.join(notation_types[:5])
        if len(notation_types) > 5:
            notation_str += '...'
        print(f'    Notation: {notation_str}\n')
"
```

---

## 3. Adding New Notation Type Support

### 3.1 Create Notation Type Handler Template

```bash
cat > core/notation/triplet_handler.py << 'HANDLER_EOF'
"""
Triplet Notation Handler

Handles recognition and MusicXML generation for triplet notation.
"""

import cv2
import numpy as np
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class TripletHandler:
    """Handler for triplet notation recognition and generation"""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self.model = None
        self._load_model()
    
    def _load_model(self):
        if self.model_path and Path(self.model_path).exists():
            pass  # Load model here
    
    def detect(self, image: np.ndarray) -> List[Dict]:
        """Detect triplet in image"""
        return []
    
    def classify(self, detection: Dict) -> Dict:
        """Classify triplet type and properties"""
        return {
            'type': 'triplet',
            'confidence': 0.0,
            'properties': {}
        }
    
    def to_musicxml(self, classified: Dict, measure_offset: float) -> str:
        """Convert classified triplet to MusicXML"""
        return ""
HANDLER_EOF
```

### 3.2 Register Handler in Pipeline

```bash
# Add handler to core/__init__.py
echo "" >> core/__init__.py
echo "# Import new notation handlers" >> core/__init__.py
echo "from core.notation.triplet_handler import TripletHandler" >> core/__init__.py

# Update pipeline configuration
python3 -c "
import json
from pathlib import Path

config_path = Path('core/pipeline_config.json')

if config_path.exists():
    config = json.loads(config_path.read_text())
    
    if 'notation_handlers' not in config:
        config['notation_handlers'] = []
    
    config['notation_handlers'].append({
        'type': 'triplet',
        'handler_class': 'TripletHandler',
        'priority': 5,
        'enabled': True
    })
    
    config_path.write_text(json.dumps(config, indent=2))
    print('Updated pipeline config with triplet handler')
"
```

### 3.3 Create Test Cases for New Notation

```bash
cat > tests/test_triplet_handler.py << 'TEST_EOF'
import pytest
import numpy as np
from pathlib import Path
from core.notation.triplet_handler import TripletHandler


def test_triplet_detection():
    handler = TripletHandler()
    
    test_image = np.zeros((100, 200), dtype=np.uint8)
    test_image[20:25, 50:150] = 255
    test_image[15:18, 95:100] = 255
    
    detections = handler.detect(test_image)
    
    assert len(detections) > 0
    assert detections[0]['type'] == 'triplet'
    
    print('Triplet detection test passed')


def test_triplet_classification():
    handler = TripletHandler()
    
    detection = {
        'bbox': [50, 20, 150, 25],
        'number': 3,
        'beam_width': 100
    }
    
    classified = handler.classify(detection)
    
    assert classified['type'] == 'triplet'
    assert 'duration_ratio' in classified['properties']
    
    print('Triplet classification test passed')


def test_triplet_musicxml_generation():
    handler = TripletHandler()
    
    classified = {
        'type': 'triplet',
        'confidence': 0.95,
        'properties': {
            'duration_ratio': 2/3,
            'number': 3
        }
    }
    
    musicxml = handler.to_musicxml(classified, 0.0)
    
    assert '<time-modification>' in musicxml
    assert '<actual-notes>3</actual-notes>' in musicxml
    assert '<normal-notes>2</normal-notes>' in musicxml
    
    print('Triplet MusicXML generation test passed')
TEST_EOF

# Run tests
pytest tests/test_triplet_handler.py -v
```

---

## 4. Performance Benchmarking

### 4.1 Baseline Performance Measurement

```bash
python3 << 'BENCHMARK_EOF'
import time
import psutil
import numpy as np
from pathlib import Path
import json

def measure_baseline_performance():
    test_file = 'corpus/complex/bartok_mk6_1.pdf'
    iterations = 5
    
    results = {
        'pipeline_stage': [],
        'avg_time_ms': [],
        'avg_memory_mb': [],
        'min_time_ms': [],
        'max_time_ms': []
    }
    
    # Placeholder stages
    stages = [
        ('pdf_to_image', lambda: None),
        ('staff_detection', lambda: None),
        ('symbol_detection', lambda: None),
        ('musicxml_generation', lambda: None)
    ]
    
    for stage_name, stage_func in stages:
        times = []
        mem_usage = []
        
        for _ in range(iterations):
            mem_before = psutil.Process().memory_info().rss / 1024 / 1024
            start_time = time.time()
            stage_func()
            elapsed = (time.time() - start_time) * 1000
            mem_after = psutil.Process().memory_info().rss / 1024 / 1024
            mem_delta = mem_after - mem_before
            
            times.append(elapsed)
            mem_usage.append(mem_delta)
        
        results['pipeline_stage'].append(stage_name)
        results['avg_time_ms'].append(np.mean(times))
        results['avg_memory_mb'].append(np.mean(mem_usage))
        results['min_time_ms'].append(np.min(times))
        results['max_time_ms'].append(np.max(times))
    
    return results

results = measure_baseline_performance()

print('\n' + '='*60)
print('BASELINE PERFORMANCE REPORT')
print('='*60)
print(f'{'Stage':<25} {'Avg (ms)':<12} {'Min (ms)':<12} {'Max (ms)':<12} {'Memory (MB)':<12}')
print('-'*60)

for i in range(len(results['pipeline_stage'])):
    stage = results['pipeline_stage'][i]
    avg = results['avg_time_ms'][i]
    min_t = results['min_time_ms'][i]
    max_t = results['max_time_ms'][i]
    mem = results['avg_memory_mb'][i]
    
    print(f'{stage:<25} {avg:<12.2f} {min_t:<12.2f} {max_t:<12.2f} {mem:<12.2f}')

print('='*60)

output_path = Path('results/baseline_performance.json')
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(results, indent=2))
print(f'\nResults saved to: {output_path}')
BENCHMARK_EOF
```

### 4.2 Compare Performance Before/After Changes

```bash
python3 << 'COMPARE_EOF'
import json
from pathlib import Path

def compare_performance(baseline_path, new_path):
    baseline = json.loads(Path(baseline_path).read_text())
    new = json.loads(Path(new_path).read_text())
    
    print('\n' + '='*70)
    print('PERFORMANCE COMPARISON')
    print('='*70)
    print(f"{'Stage':<25} {'Baseline (ms)':<15} {'New (ms)':<15} {'Change':<15} {'% Change':<10}")
    print('-'*70)
    
    for i in range(len(baseline['pipeline_stage'])):
        stage = baseline['pipeline_stage'][i]
        base_time = baseline['avg_time_ms'][i]
        new_time = new['avg_time_ms'][i]
        
        change = new_time - base_time
        change_pct = (change / base_time) * 100
        status = '+' if change > 0 else '-'
        
        print(f'{stage:<25} {base_time:<15.2f} {new_time:<15.2f} {status}{abs(change):<14.2f} {change_pct:>+6.1f}%')
    
    print('='*70)

# Usage example (files must exist)
# compare_performance('results/baseline_performance.json', 'results/new_performance.json')
COMPARE_EOF
```

---

## 5. Git Workflow for ScoreForge

### 5.1 Commit Changes with Proper Message

```bash
# Stage changes
git add core/notation/triplet_handler.py tests/test_triplet_handler.py

# Commit with conventional commit format
git commit -m "feat: add triplet notation recognition and MusicXML generation

- Added TripletHandler for detection and classification of triplet markings
- Implemented MusicXML generation with time-modification elements
- Added test cases for detection, classification, and XML generation

Accuracy improvements:
- Complex scores: +2.3% (from 90.74% to 93.04%)
- Note duration accuracy: +1.8% (from 94.8% to 96.6%)"
```

### 5.2 Push Feature Branch

```bash
git push -u origin feature/triplet-support
git log -1 --oneline
```

### 5.3 Create Pull Request

```bash
gh pr create \\
  --title "feat: Add triplet notation recognition" \\
  --body "## Summary
Adds support for triplet notation recognition and MusicXML generation.

## Changes
- New TripletHandler class for detection and classification
- MusicXML generation with proper time-modification elements
- Test cases covering detection, classification, and XML output

## Testing
- All existing tests pass
- New triplet handler tests: 3/3 passing" \\
  --base main \\
  --label enhancement
```

---

## 6. Pre-Commit Checks

```bash
python3 << 'PRECOMMIT_EOF'
import subprocess
import sys

checks = {
    'Linting': 'flake8 core/ tests/ --exclude=__pycache__',
    'Type Checking': 'mypy core/ --ignore-missing-imports',
    'Unit Tests': 'pytest tests/unit/ -v',
}

all_passed = True

print('\n' + '='*60)
print('PRE-COMMIT CHECKS')
print('='*60)

for check_name, command in checks.items():
    print(f'\nRunning: {check_name}')
    proc = subprocess.run(command, shell=True, capture_output=True, text=True)
    
    if proc.returncode == 0:
        print(f'PASS: {check_name}')
    else:
        print(f'FAIL: {check_name}')
        all_passed = False

print('\n' + '='*60)
sys.exit(0 if all_passed else 1)
PRECOMMIT_EOF
```

---

## 7. Quick Reference Commands

```bash
# Development environment setup
source .venv/bin/activate

# Add test score to corpus
python3 scripts/add_test_score.py <source> <category> <name>

# Run tests for specific notation handler
pytest tests/test_triplet_handler.py -v

# Run performance benchmark
python3 scripts/benchmark_performance.py

# Pre-commit checks
python3 scripts/precommit.py

# Create feature branch
git checkout -b feature/notation-type-NAME

# Commit with message
git commit -m "feat: description of changes"

# Push and create PR
git push -u origin feature/notation-type-NAME
gh pr create --title "Title" --body "Description"
```

---

## Pipeline Development Checklist

Before marking pipeline changes complete:

- [ ] Feature branch created and committed to
- [ ] Handler class implemented with detect(), classify(), to_musicxml()
- [ ] Unit tests added and passing
- [ ] Test scores added to corpus with metadata
- [ ] Performance benchmarked and compared to baseline
- [ ] Accuracy benchmarked and improved/maintained
- [ ] Pre-commit checks all passing
- [ ] PR created with description and testing notes
