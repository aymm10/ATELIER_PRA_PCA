import os
import glob
import time
import sqlite3
from datetime import datetime, timezone
from flask import Flask, jsonify, request

DB_PATH = os.getenv("DB_PATH", "/data/app.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backup")

app = Flask(__name__)

# ---------- DB helpers ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            message TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ---------- Routes ----------

@app.get("/")
def hello():
    init_db()
    return jsonify(status="Bonjour tout le monde !")


@app.get("/health")
def health():
    init_db()
    return jsonify(status="ok")

@app.get("/add")
def add():
    init_db()

    msg = request.args.get("message", "hello")
    ts = datetime.utcnow().isoformat() + "Z"

    conn = get_conn()
    conn.execute(
        "INSERT INTO events (ts, message) VALUES (?, ?)",
        (ts, msg)
    )
    conn.commit()
    conn.close()

    return jsonify(
        status="added",
        timestamp=ts,
        message=msg
    )

@app.get("/consultation")
def consultation():
    init_db()

    conn = get_conn()
    cur = conn.execute(
        "SELECT id, ts, message FROM events ORDER BY id DESC LIMIT 50"
    )

    rows = [
        {"id": r[0], "timestamp": r[1], "message": r[2]}
        for r in cur.fetchall()
    ]

    conn.close()

    return jsonify(rows)

@app.get("/count")
def count():
    init_db()

    conn = get_conn()
    cur = conn.execute("SELECT COUNT(*) FROM events")
    n = cur.fetchone()[0]
    conn.close()

    return jsonify(count=n)

@app.get("/status")
def status():
    init_db()

    # 1. Nombre d'événements en base
    try:
        conn = get_conn()
        cur = conn.execute("SELECT COUNT(*) FROM events")
        event_count = cur.fetchone()[0]
        conn.close()
    except Exception:
        event_count = 0

    # 2. Dernier fichier de backup dans /backup
    backup_files = sorted(glob.glob(os.path.join(BACKUP_DIR, "*.db")))

    if backup_files:
        last_backup_file = os.path.basename(backup_files[-1])
        backup_age_seconds = int(time.time() - os.path.getmtime(backup_files[-1]))
    else:
        last_backup_file = None
        backup_age_seconds = None

    return jsonify(
        count=event_count,
        last_backup_file=last_backup_file,
        backup_age_seconds=backup_age_seconds
    )

@app.get("/backups")
def backups():
    """
    Liste tous les points de restauration disponibles dans /backup.
    Retourne pour chaque fichier : son nom, le timestamp unix,
    la date lisible et l'âge en secondes.
    """
    backup_files = sorted(
        glob.glob(os.path.join(BACKUP_DIR, "*.db")),
        reverse=True  # Du plus récent au plus ancien
    )

    result = []
    now = time.time()

    for filepath in backup_files:
        filename = os.path.basename(filepath)
        mtime = os.path.getmtime(filepath)

        # Extraire le timestamp unix depuis le nom de fichier (app-<ts>.db)
        try:
            ts_unix = int(filename.replace("app-", "").replace(".db", ""))
            ts_human = datetime.fromtimestamp(ts_unix, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        except ValueError:
            ts_unix = int(mtime)
            ts_human = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        result.append({
            "filename":        filename,
            "timestamp_unix":  ts_unix,
            "datetime":        ts_human,
            "age_seconds":     int(now - mtime)
        })

    return jsonify(
        total=len(result),
        backups=result
    )

# ---------- Main ----------
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)