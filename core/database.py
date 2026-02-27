"""
Database manager - SQLite storage for all collected data.
Dead simple: one table for entries, one for export history.
"""
import sqlite3
import os
from datetime import datetime
from config import DB_PATH


def get_connection():
    """Get a database connection (creates DB if needed)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            word_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS export_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            format TEXT NOT NULL,
            entry_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
    """)
    conn.commit()
    conn.close()


# ─── CRUD Operations ──────────────────────────────────────────────

def add_entry(title, content, source_type, source_url="", tags="", category="general"):
    """Add a new data entry. Returns the new entry's ID."""
    word_count = len(content.split())
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO entries (title, content, source_type, source_url, tags, category, word_count)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, content, source_type, source_url, tags, category, word_count)
    )
    entry_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return entry_id


def get_entry(entry_id):
    """Get a single entry by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_entries(source_type=None, category=None, search=None):
    """Get all entries with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM entries WHERE 1=1"
    params = []

    if source_type and source_type != "all":
        query += " AND source_type = ?"
        params.append(source_type)

    if category and category != "all":
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])

    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_entry(entry_id, **kwargs):
    """Update an entry. Pass any column=value pairs to update."""
    if not kwargs:
        return
    if "content" in kwargs:
        kwargs["word_count"] = len(kwargs["content"].split())
    kwargs["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [entry_id]

    conn = get_connection()
    conn.execute(f"UPDATE entries SET {sets} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_entry(entry_id):
    """Delete an entry by ID."""
    conn = get_connection()
    conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()


def delete_multiple_entries(entry_ids):
    """Delete multiple entries."""
    if not entry_ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" * len(entry_ids))
    conn.execute(f"DELETE FROM entries WHERE id IN ({placeholders})", entry_ids)
    conn.commit()
    conn.close()


def get_entry_count():
    """Get total number of entries."""
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    conn.close()
    return count


def get_all_categories():
    """Get list of all unique categories."""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT category FROM entries ORDER BY category").fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_tags():
    """Get list of all unique tags."""
    conn = get_connection()
    rows = conn.execute("SELECT DISTINCT tags FROM entries WHERE tags != ''").fetchall()
    conn.close()
    all_tags = set()
    for r in rows:
        for tag in r[0].split(","):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)
    return sorted(all_tags)


def get_stats():
    """Get database stats for dashboard."""
    conn = get_connection()
    stats = {}
    stats["total_entries"] = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    stats["total_words"] = conn.execute("SELECT COALESCE(SUM(word_count), 0) FROM entries").fetchone()[0]

    type_counts = conn.execute(
        "SELECT source_type, COUNT(*) as cnt FROM entries GROUP BY source_type"
    ).fetchall()
    stats["by_type"] = {r[0]: r[1] for r in type_counts}

    stats["total_exports"] = conn.execute("SELECT COUNT(*) FROM export_history").fetchone()[0]
    conn.close()
    return stats


# ─── Export History ────────────────────────────────────────────────

def add_export_record(filename, fmt, entry_count):
    """Record an export."""
    conn = get_connection()
    conn.execute(
        "INSERT INTO export_history (filename, format, entry_count) VALUES (?, ?, ?)",
        (filename, fmt, entry_count)
    )
    conn.commit()
    conn.close()


# ─── Duplicate Detection ──────────────────────────────────────────

def url_exists(url):
    """Check if a URL has already been scraped. Returns entry dict or None."""
    if not url:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT id, title, created_at FROM entries WHERE source_url = ? LIMIT 1", (url,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_similar_titles(title, threshold=0.8):
    """Find entries with similar titles (basic word overlap)."""
    if not title:
        return []
    conn = get_connection()
    rows = conn.execute("SELECT id, title, source_type, created_at FROM entries").fetchall()
    conn.close()

    title_words = set(title.lower().split())
    if not title_words:
        return []

    matches = []
    for row in rows:
        row_words = set(row["title"].lower().split())
        if not row_words:
            continue
        overlap = len(title_words & row_words) / max(len(title_words | row_words), 1)
        if overlap >= threshold:
            matches.append({**dict(row), "similarity": round(overlap * 100)})

    return sorted(matches, key=lambda x: x["similarity"], reverse=True)[:5]


# Initialize on import
init_db()
