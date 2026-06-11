"""
server.py — FastAPI leaderboard server.

Run this separately from the game:
    uvicorn server:app --reload

Then open http://localhost:8000 in your browser to see the leaderboard.
The game POSTs scores to http://localhost:8000/score on game over.
"""

import sqlite3
import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow the game (running locally) to POST to this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "leaderboard.db"


# ── Database setup ────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL,
            score     INTEGER NOT NULL,
            wave      INTEGER NOT NULL,
            kills     INTEGER NOT NULL,
            posted_at TEXT    NOT NULL
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ── Models ────────────────────────────────────────────────────────────────────

class ScoreSubmission(BaseModel):
    name:  str
    score: int
    wave:  int
    kills: int


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/score")
def submit_score(data: ScoreSubmission):
    """Game calls this on game over to submit a score."""
    conn = get_db()
    conn.execute(
        "INSERT INTO scores (name, score, wave, kills, posted_at) VALUES (?, ?, ?, ?, ?)",
        (data.name[:20], data.score, data.wave, data.kills,
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/scores")
def get_scores():
    """Return top 10 scores as JSON."""
    conn = get_db()
    rows = conn.execute(
        "SELECT name, score, wave, kills, posted_at FROM scores ORDER BY score DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/", response_class=HTMLResponse)
def leaderboard_page():
    """Browser leaderboard page — open http://localhost:8000"""
    return """
<!DOCTYPE html>
<html>
<head>
  <title>DEADZONE — Leaderboard</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      background: #0a0c12;
      color: #fff;
      font-family: 'Courier New', monospace;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 20px;
      min-height: 100vh;
    }

    h1 {
      font-size: 52px;
      color: #00dcb4;
      letter-spacing: 8px;
      text-shadow: 0 0 20px #00dcb4;
      margin-bottom: 8px;
    }

    .subtitle {
      color: #4a5570;
      letter-spacing: 4px;
      font-size: 13px;
      margin-bottom: 40px;
    }

    table {
      width: 100%;
      max-width: 700px;
      border-collapse: collapse;
    }

    thead tr {
      border-bottom: 1px solid #1e2438;
    }

    th {
      color: #4a5570;
      font-size: 12px;
      letter-spacing: 2px;
      padding: 10px 16px;
      text-align: left;
    }

    td {
      padding: 14px 16px;
      font-size: 15px;
      border-bottom: 1px solid #12151f;
    }

    tr:hover td { background: #12151f; }

    .rank { color: #4a5570; width: 40px; }
    .rank.gold   { color: #ffc832; font-weight: bold; }
    .rank.silver { color: #aab0c0; font-weight: bold; }
    .rank.bronze { color: #cd7f32; font-weight: bold; }

    .name  { color: #00dcb4; }
    .score { color: #ffc832; font-weight: bold; font-size: 17px; }
    .wave  { color: #ffffff; }
    .kills { color: #ff3246; }
    .date  { color: #2a3048; font-size: 12px; }

    .empty {
      color: #2a3048;
      text-align: center;
      padding: 60px;
      font-size: 14px;
      letter-spacing: 2px;
    }

    .refresh {
      margin-top: 30px;
      color: #2a3048;
      font-size: 12px;
      letter-spacing: 2px;
    }

    .live-dot {
      display: inline-block;
      width: 6px; height: 6px;
      background: #00dcb4;
      border-radius: 50%;
      margin-right: 6px;
      animation: pulse 1.5s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.2; }
    }
  </style>
</head>
<body>
  <h1>DEADZONE</h1>
  <div class="subtitle">ZOMBIE SURVIVAL &nbsp;•&nbsp; LEADERBOARD</div>

  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>NAME</th>
        <th>SCORE</th>
        <th>WAVE</th>
        <th>KILLS</th>
        <th>DATE</th>
      </tr>
    </thead>
    <tbody id="rows">
      <tr><td colspan="6" class="empty">Loading...</td></tr>
    </tbody>
  </table>

  <div class="refresh">
    <span class="live-dot"></span>AUTO-REFRESHES EVERY 10 SECONDS
  </div>

  <script>
    const rankLabel = (i) => {
      if (i === 0) return '<span class="rank gold">#1</span>';
      if (i === 1) return '<span class="rank silver">#2</span>';
      if (i === 2) return '<span class="rank bronze">#3</span>';
      return `<span class="rank">#${i+1}</span>`;
    };

    async function load() {
      try {
        const res  = await fetch('/scores');
        const data = await res.json();
        const tbody = document.getElementById('rows');

        if (data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="empty">NO SCORES YET — PLAY THE GAME</td></tr>';
          return;
        }

        tbody.innerHTML = data.map((r, i) => `
          <tr>
            <td>${rankLabel(i)}</td>
            <td class="name">${r.name}</td>
            <td class="score">${r.score.toLocaleString()}</td>
            <td class="wave">${r.wave}</td>
            <td class="kills">${r.kills}</td>
            <td class="date">${r.posted_at}</td>
          </tr>
        `).join('');
      } catch (e) {
        document.getElementById('rows').innerHTML =
          '<tr><td colspan="6" class="empty">SERVER OFFLINE</td></tr>';
      }
    }

    load();
    setInterval(load, 10000);
  </script>
</body>
</html>
"""