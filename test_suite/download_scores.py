#!/usr/bin/env python3
"""
Download public domain scores to fill test suite gaps.
Prioritizes: cross-staff beaming, ossia, polyrhythms, percussion.
"""

import os
import urllib.request
from pathlib import Path

# Create directories
test_suite = Path("test_suite")
categories = {
    "cross_staff_beaming": test_suite / "cross_staff_beaming",
    "ossia_cue_notes": test_suite / "ossia_cue_notes", 
    "polyrhythms": test_suite / "polyrhythms",
    "percussion_notation": test_suite / "percussion_notation",
    "guitar_tablature": test_suite / "guitar_tablature",
    "chord_symbols": test_suite / "chord_symbols",
    "figured_bass": test_suite / "figured_bass"
}

for path in categories.values():
    path.mkdir(parents=True, exist_ok=True)

# Target scores from Mutopia (direct PDF links, no auth needed)
# Note: These URLs are examples - actual Mutopia URLs need verification
targets = [
    {
        "category": "cross_staff_beaming",
        "url": "https://www.mutopiaproject.org/ftp/ChopinFF/O10/Chop-10-3/",
        "filename": "chopin-etude-op10-3-a4.pdf",
        "description": "Chopin Etude Op. 10 No. 3 - Tristesse",
        "composer": "Frédéric Chopin"
    },
    {
        "category": "cross_staff_beaming", 
        "url": "https://www.mutopiaproject.org/ftp/ChopinFF/O25/Chop-25-1/",
        "filename": "chopin-etude-op25-1-a4.pdf",
        "description": "Chopin Etude Op. 25 No. 1 - Aeolian Harp",
        "composer": "Frédéric Chopin"
    },
    {
        "category": "cross_staff_beaming",
        "url": "https://www.mutopiaproject.org/ftp/BrahmsJ/O118/Brah-118-2/",
        "filename": "brahms-intermezzo-op118-2-a4.pdf",
        "description": "Brahms Intermezzo Op. 118 No. 2 in A major",
        "composer": "Johannes Brahms"
    },
    {
        "category": "cross_staff_beaming",
        "url": "https://www.mutopiaproject.org/ftp/RachmaninoffS/O23/Rach-23-5/",
        "filename": "rachmaninoff-prelude-op23-5-a4.pdf", 
        "description": "Rachmaninoff Prelude Op. 23 No. 5 in G minor",
        "composer": "Sergei Rachmaninoff"
    },
    {
        "category": "polyrhythms",
        "url": "https://www.mutopiaproject.org/ftp/BartokB/Sz91/Bart-4-5/",
        "filename": "bartok-quartet4-mvt5-a4.pdf",
        "description": "Bartok String Quartet No. 4 - 5th movement",
        "composer": "Béla Bartók"
    },
    {
        "category": "polyrhythms",
        "url": "https://www.mutopiaproject.org/ftp/StravinskyI/Strav-Octet/",
        "filename": "stravinsky-octet-winds-a4.pdf",
        "description": "Stravinsky Octet for Winds",
        "composer": "Igor Stravinsky"
    },
    {
        "category": "figured_bass",
        "url": "https://www.mutopiaproject.org/ftp/CorelliA/O1-3/Core-1-1/",
        "filename": "corelli-trio-sonata-op1-3-a4.pdf",
        "description": "Corelli Trio Sonata Op. 1 No. 3 - with figured bass",
        "composer": "Arcangelo Corelli"
    },
    {
        "category": "figured_bass",
        "url": "https://www.mutopiaproject.org/ftp/HandelGF/HWV56/Han-56-1/",
        "filename": "handel-concerto-grosso-op6-1-a4.pdf",
        "description": "Handel Concerto Grosso Op. 6 No. 1",
        "composer": "George Frideric Handel"
    }
]

def download_file(url, dest_path, description):
    """Download file from URL to destination path."""
    try:
        print(f"Downloading: {description}")
        print(f"  From: {url}")
        print(f"  To: {dest_path}")
        
        urllib.request.urlretrieve(url, dest_path)
        size = os.path.getsize(dest_path)
        print(f"  ✓ Downloaded ({size} bytes)")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False

def main():
    print("ScoreForge Test Suite - Score Downloader")
    print("=" * 60)
    print(f"Targets: {len(targets)} scores")
    print()
    
    downloaded = 0
    failed = 0
    
    for target in targets:
        dest_path = categories[target["category"]] / target["filename"]
        if dest_path.exists():
            print(f"Skipping {target['filename']} - already exists")
            downloaded += 1
            continue
        
        # Note: Actual Mutopia URLs follow a pattern
        # The base URL points to directory, we need to construct PDF URL
        # For now, this creates placeholder entries
        print(f"\n[PLACEHOLDER] {target['description']}")
        print(f"  Category: {target['category']}")
        print(f"  Composer: {target['composer']}")
        print(f"  Mutopia URL: {target['url']}")
        print(f"  Note: Manual download required - verify Mutopia URL structure")
        
        failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {downloaded} existing, {len(targets)-downloaded} need manual download")
    print()
    print("Note: Mutopia URLs need verification. Manual download recommended:")
    print("1. Visit https://www.mutopiaproject.org/")
    print("2. Search for composer/work")
    print("3. Download PDF")
    print("4. Place in appropriate test_suite/[category] directory")

if __name__ == "__main__":
    main()
