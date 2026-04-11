"""Job storage abstraction for ScoreForge API.

Supports in-memory (dev) and SQLite (production) backends.
Configured via JOB_STORE_TYPE environment variable.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


class JobStore:
    """Abstract job storage with in-memory and SQLite backends."""
    
    def __init__(self, store_type: str = "memory", db_path: Optional[str] = None):
        """Initialize job store.
        
        Args:
            store_type: "memory" for in-memory dict, "sqlite" for SQLite database
            db_path: Path to SQLite database (required for sqlite type)
        """
        self.store_type = store_type
        self._lock = threading.Lock()
        
        if store_type == "memory":
            self._memory_store: Dict[str, Dict] = {}
        elif store_type == "sqlite":
            if not db_path:
                raise ValueError("db_path required for sqlite store type")
            self.db_path = Path(db_path)
            self._init_sqlite()
        else:
            raise ValueError(f"Invalid store_type: {store_type}")
    
    def _init_sqlite(self) -> None:
        """Initialize SQLite database and create jobs table."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                filename TEXT,
                measure_count INTEGER,
                part_count INTEGER,
                musicxml TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()
    
    def get(self, job_id: str) -> Optional[Dict]:
        """Retrieve job data by ID."""
        with self._lock:
            if self.store_type == "memory":
                return self._memory_store.get(job_id)
            else:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.execute(
                    "SELECT * FROM jobs WHERE id = ?",
                    (job_id,)
                )
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return {
                        "id": row[0],
                        "status": row[1],
                        "filename": row[2],
                        "measure_count": row[3],
                        "part_count": row[4],
                        "musicxml": json.loads(row[5]) if row[5] else None,
                        "error": row[6],
                        "created_at": row[7],
                    }
                return None
    
    def set(self, job_id: str, data: Dict) -> None:
        """Store or update job data."""
        with self._lock:
            # Ensure created_at is set
            if "created_at" not in data:
                data["created_at"] = datetime.now(timezone.utc).isoformat()
            
            if self.store_type == "memory":
                self._memory_store[job_id] = data
            else:
                musicxml_json = json.dumps(data["musicxml"]) if data.get("musicxml") else None
                conn = sqlite3.connect(self.db_path)
                conn.execute("""
                    INSERT OR REPLACE INTO jobs 
                    (id, status, filename, measure_count, part_count, musicxml, error, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["id"],
                    data["status"],
                    data.get("filename"),
                    data.get("measure_count"),
                    data.get("part_count"),
                    musicxml_json,
                    data.get("error"),
                    data["created_at"],
                ))
                conn.commit()
                conn.close()
    
    def delete(self, job_id: str) -> bool:
        """Delete job by ID. Returns True if deleted, False if not found."""
        with self._lock:
            if self.store_type == "memory":
                if job_id in self._memory_store:
                    del self._memory_store[job_id]
                    return True
                return False
            else:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.execute(
                    "DELETE FROM jobs WHERE id = ?",
                    (job_id,)
                )
                deleted = cursor.rowcount > 0
                conn.commit()
                conn.close()
                return deleted
    
    def list_all(self) -> Dict[str, Dict]:
        """Return all jobs as a dict mapping job_id to job data."""
        with self._lock:
            if self.store_type == "memory":
                return self._memory_store.copy()
            else:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.execute("SELECT * FROM jobs")
                jobs = {}
                for row in cursor.fetchall():
                    jobs[row[0]] = {
                        "id": row[0],
                        "status": row[1],
                        "filename": row[2],
                        "measure_count": row[3],
                        "part_count": row[4],
                        "musicxml": json.loads(row[5]) if row[5] else None,
                        "error": row[6],
                        "created_at": row[7],
                    }
                conn.close()
                return jobs
    
    def count_by_status(self, status: str) -> int:
        """Count jobs with given status."""
        if self.store_type == "memory":
            return sum(1 for job in self._memory_store.values() if job.get("status") == status)
        else:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = ?",
                (status,)
            )
            count = cursor.fetchone()[0]
            conn.close()
            return count
