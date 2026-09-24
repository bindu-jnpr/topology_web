import sqlite3
import os
from datetime import datetime

# Default to a local topologies.db file if DB_PATH isn't set
DB_PATH = os.getenv("DB_PATH", "topologies.db")

def init_db():
    # Only try to create directories if there is a directory path
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS topologies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario TEXT,
            topology_json TEXT,
            feedback INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_topology(scenario: str, topology_json: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO topologies (scenario, topology_json, created_at) VALUES (?,?,?)",
        (scenario, topology_json, datetime.utcnow().isoformat())
    )
    topo_id = c.lastrowid
    conn.commit()
    conn.close()
    return topo_id

def get_topology(topo_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT topology_json FROM topologies WHERE id=?", (topo_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def save_feedback(topo_id: int, good: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE topologies SET feedback=? WHERE id=?", (1 if good else -1, topo_id))
    conn.commit()
    conn.close()

def find_similar(scenario: str, limit: int = 2):
    words = scenario.lower().split()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    results = []
    for word in words:
        if len(word) > 4:
            c.execute(
                "SELECT scenario, topology_json FROM topologies WHERE scenario LIKE ? AND feedback >= 0 LIMIT ?",
                (f"%{word}%", limit)
            )
            results.extend(c.fetchall())
    conn.close()
    seen = set()
    unique = []
    for row in results:
        if row[0] not in seen:
            seen.add(row[0])
            unique.append(row)
    return unique[:limit]
