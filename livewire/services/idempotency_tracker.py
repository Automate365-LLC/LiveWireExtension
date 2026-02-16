import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict

class IdempotencyTracker:
    def __init__(self, db_path: str = "livewire_idempotency.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crm_pushes (
                dedupe_key TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                artifact_type TEXT NOT NULL,
                artifact_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                attempts INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id 
            ON crm_pushes(session_id)
        """)
        
        conn.commit()
        conn.close()
    
    def generate_dedupe_key(self, session_id: str, artifact_type: str, artifact_id: str) -> str:
        return f"{session_id}:{artifact_type}:{artifact_id}"
    
    def check_duplicate(self, dedupe_key: str, payload: dict) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT status, completed_at, attempts, payload_hash
            FROM crm_pushes
            WHERE dedupe_key = ?
        """, (dedupe_key,))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            return None
        
        status, completed_at, attempts, stored_hash = result
        payload_hash = self._hash_payload(payload)
        
        if stored_hash != payload_hash:
            return {
                "duplicate": False,
                "reason": "payload_changed",
                "message": "Payload changed, allowing retry"
            }
        
        if status == "completed":
            return {
                "duplicate": True,
                "status": "completed",
                "completed_at": completed_at,
                "attempts": attempts,
                "message": "Already successfully pushed"
            }
        
        if status == "in_progress":
            return {
                "duplicate": False,
                "status": "in_progress",
                "attempts": attempts,
                "message": "Previous attempt incomplete, allowing retry"
            }
        
        return None
    
    def record_attempt(self, dedupe_key: str, session_id: str, artifact_type: str, 
                       artifact_id: str, payload: dict, status: str = "in_progress"):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        payload_hash = self._hash_payload(payload)
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO crm_pushes 
            (dedupe_key, session_id, artifact_type, artifact_id, payload_hash, 
             status, created_at, attempts)
            VALUES (?, ?, ?, ?, ?, ?, ?, 
                    COALESCE((SELECT attempts + 1 FROM crm_pushes WHERE dedupe_key = ?), 1))
        """, (dedupe_key, session_id, artifact_type, artifact_id, payload_hash, 
              status, now, dedupe_key))
        
        conn.commit()
        conn.close()
    
    def mark_completed(self, dedupe_key: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE crm_pushes
            SET status = 'completed', completed_at = ?
            WHERE dedupe_key = ?
        """, (datetime.now().isoformat(), dedupe_key))
        
        conn.commit()
        conn.close()
    
    def mark_failed(self, dedupe_key: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE crm_pushes
            SET status = 'failed'
            WHERE dedupe_key = ?
        """, (dedupe_key,))
        
        conn.commit()
        conn.close()
    
    def _hash_payload(self, payload: dict) -> str:
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()
    
    def cleanup_old_records(self, days: int = 30):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        cursor.execute("""
            DELETE FROM crm_pushes
            WHERE created_at < ?
        """, (cutoff,))
        
        conn.commit()
        conn.close()
