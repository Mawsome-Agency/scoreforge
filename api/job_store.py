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
        # Create table with all required columns including model tracking and upload source
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                filename TEXT,
                measure_count INTEGER,
                part_count INTEGER,
                musicxml TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds INTEGER,
                model_provider TEXT,
                model_name TEXT,
                upload_source TEXT
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
                        "completed_at": row[8],
                        "duration_seconds": row[9],
                        "model_provider": row[10],
                        "model_name": row[11],
                        "upload_source": row[12],
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
                    (id, status, filename, measure_count, part_count, musicxml, error, created_at,
                     completed_at, duration_seconds, model_provider, model_name, upload_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    data["id"],
                    data["status"],
                    data.get("filename"),
                    data.get("measure_count"),
                    data.get("part_count"),
                    musicxml_json,
                    data.get("error"),
                    data["created_at"],
                    data.get("completed_at"),
                    data.get("duration_seconds"),
                    data.get("model_provider"),
                    data.get("model_name"),
                    data.get("upload_source"),
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
                cursor = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC")
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
                        "completed_at": row[8],
                        "duration_seconds": row[9],
                        "model_provider": row[10],
                        "model_name": row[11],
                        "upload_source": row[12],
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

    def get_stats(self) -> Dict:
        """Get summary statistics for all jobs."""
        jobs = self.list_all()
        total = len(jobs)

        if total == 0:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "pending": 0,
                "running": 0,
                "pass_rate": 0.0,
                "avg_duration": 0.0,
                "model_breakdown": {},
            }

        completed = sum(1 for job in jobs.values() if job.get("status") == "completed")
        failed = sum(1 for job in jobs.values() if job.get("status") == "failed")
        pending = sum(1 for job in jobs.values() if job.get("status") == "pending")
        running = sum(1 for job in jobs.values() if job.get("status") == "running")

        # Pass rate (completed / (completed + failed))
        pass_rate = completed / (completed + failed) if (completed + failed) > 0 else 0.0

        # Average duration for completed jobs
        completed_jobs = [job for job in jobs.values() if job.get("status") == "completed"]
        durations = [job.get("duration_seconds") for job in completed_jobs if job.get("duration_seconds")]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        # Model performance breakdown
        model_breakdown = {}
        for job in jobs.values():
            provider = job.get("model_provider") or "unknown"
            model = job.get("model_name") or "unknown"
            key = f"{provider}:{model}"
            if key not in model_breakdown:
                model_breakdown[key] = {"total": 0, "completed": 0, "failed": 0}
            model_breakdown[key]["total"] += 1
            if job.get("status") == "completed":
                model_breakdown[key]["completed"] += 1
            elif job.get("status") == "failed":
                model_breakdown[key]["failed"] += 1

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "running": running,
            "pass_rate": round(pass_rate * 100, 2),
            "avg_duration": round(avg_duration, 2),
            "model_breakdown": model_breakdown,
        }

    def list_filtered(self, status: Optional[str] = None,
                      model_provider: Optional[str] = None,
                      upload_source: Optional[str] = None,
                      limit: Optional[int] = None,
                      offset: int = 0) -> list:
        """List jobs with optional filtering and pagination."""
        jobs = self.list_all()

        # Apply filters
        filtered = []
        for job in jobs.values():
            if status and job.get("status") != status:
                continue
            if model_provider and job.get("model_provider") != model_provider:
                continue
            if upload_source and upload_source.lower() not in (job.get("upload_source") or "").lower():
                continue
            filtered.append(job)

        # Apply pagination
        if offset > 0:
            filtered = filtered[offset:]
        if limit is not None:
            filtered = filtered[:limit]

        return filtered
