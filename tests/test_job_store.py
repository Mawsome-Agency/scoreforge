"""Tests for JobStore class (memory and SQLite backends)."""
import os
import tempfile
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.job_store import JobStore


def test_memory_store():
    """Test in-memory job store."""
    store = JobStore(store_type="memory")
    
    # Test set and get
    job_id = "test-1"
    job_data = {
        "id": job_id,
        "status": "pending",
        "filename": "test.png",
        "measure_count": None,
        "part_count": None,
        "musicxml": None,
        "error": None,
    }
    store.set(job_id, job_data)
    
    retrieved = store.get(job_id)
    assert retrieved is not None
    assert retrieved["id"] == job_id
    assert retrieved["status"] == "pending"
    
    # Test update
    job_data["status"] = "completed"
    job_data["measure_count"] = 8
    store.set(job_id, job_data)
    
    retrieved = store.get(job_id)
    assert retrieved["status"] == "completed"
    assert retrieved["measure_count"] == 8
    
    # Test list_all
    all_jobs = store.list_all()
    assert job_id in all_jobs
    assert len(all_jobs) >= 1
    
    # Test delete
    deleted = store.delete(job_id)
    assert deleted is True
    
    retrieved = store.get(job_id)
    assert retrieved is None
    
    print("✓ Memory store tests passed")


def test_sqlite_store():
    """Test SQLite job store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_jobs.db"
        store = JobStore(store_type="sqlite", db_path=str(db_path))
        
        # Test set and get
        job_id = "test-2"
        job_data = {
            "id": job_id,
            "status": "pending",
            "filename": "test.png",
            "measure_count": None,
            "part_count": None,
            "musicxml": None,
            "error": None,
        }
        store.set(job_id, job_data)
        
        retrieved = store.get(job_id)
        assert retrieved is not None
        assert retrieved["id"] == job_id
        assert retrieved["status"] == "pending"
        assert "created_at" in retrieved  # Auto-added
        
        # Test persistence across instances
        store2 = JobStore(store_type="sqlite", db_path=str(db_path))
        retrieved = store2.get(job_id)
        assert retrieved is not None
        assert retrieved["status"] == "pending"
        
        # Test musicxml serialization
        job_data["musicxml"] = "<musicxml><note/></musicxml>"
        job_data["status"] = "completed"
        store.set(job_id, job_data)
        
        retrieved = store.get(job_id)
        assert retrieved["musicxml"] == "<musicxml><note/></musicxml>"
        assert retrieved["status"] == "completed"
        
        # Test list_all
        all_jobs = store.list_all()
        assert job_id in all_jobs
        
        # Test count_by_status
        store.set("test-3", {"id": "test-3", "status": "pending", "filename": "test.png"})
        pending_count = store.count_by_status("pending")
        assert pending_count >= 1
        
        completed_count = store.count_by_status("completed")
        assert completed_count >= 1
        
        print("✓ SQLite store tests passed")


if __name__ == "__main__":
    test_memory_store()
    test_sqlite_store()
    print("\n✅ All JobStore tests passed!")
