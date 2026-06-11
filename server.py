"""
server.py — FastAPI leaderboard server with PostgreSQL backend.

Deployed on Railway — reads DATABASE_URL environment variable automatically.
Run locally: uvicorn server:app --reload
"""

import os
from datetime import datetime
import psycopg2
import psycopg2.extras
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    conn = get_db()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id        SERIAL PRIMARY KEY,
            name      TEXT    NOT NULL,
            score     INTEGER NOT NULL,
            wave      INTEGER NOT NULL,
            kills     INTEGER NOT NULL,
            posted_at TEXT    NOT NULL,
            ai_review TEXT    DEFAULT ''
        )
    """)
    # Add column if table already exists without it
    cur.execute("""
        ALTER TABLE scores ADD COLUMN IF NOT EXISTS ai_review TEXT DEFAULT ''
    """)
    conn.commit()
    cur.close()
    conn.close()


init_db()


# ── Models ────────────────────────────────────────────────────────────────────

class ScoreSubmission(BaseModel):
    name:      str
    score:     int
    wave:      int
    kills:     int
    ai_review: str = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.post("/score")
def submit_score(data: ScoreSubmission):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO scores (name, score, wave, kills, posted_at, ai_review) VALUES (%s, %s, %s, %s, %s, %s)",
        (data.name[:20], data.score, data.wave, data.kills,
         datetime.now().strftime("%Y-%m-%d %H:%M"), data.ai_review[:800])
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "ok"}


@app.get("/scores")
def get_scores():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT name, score, wave, kills, posted_at, ai_review FROM scores ORDER BY score DESC LIMIT 10"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/", response_class=HTMLResponse)
def leaderboard_page():
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
    table { width: 100%; max-width: 700px; border-collapse: collapse; }
    thead tr { border-bottom: 1px solid #1e2438; }
    th {
      color: #4a5570;
      font-size: 12px;
      letter-spacing: 2px;
      padding: 10px 16px;
      text-align: left;
    }
    td { padding: 14px 16px; font-size: 15px; border-bottom: 1px solid #12151f; }
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
    .refresh { margin-top: 30px; color: #2a3048; font-size: 12px; letter-spacing: 2px; }
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
    .review-row td { padding: 0 16px 14px 16px; border-bottom: 1px solid #12151f; }
    .review-row:hover td { background: #12151f; }
    .ai-review {
      color: #6a7590;
      font-size: 12px;
      line-height: 1.6;
      font-style: italic;
      letter-spacing: 0.3px;
    }
    .ai-tag {
      color: #00dcb4;
      font-style: normal;
      font-size: 10px;
      letter-spacing: 2px;
      margin-right: 8px;
      opacity: 0.7;
    }
  </style>
</head>
<body>
  <h1>DEADZONE</h1>
  <div class="subtitle">ZOMBIE SURVIVAL &nbsp;•&nbsp; LEADERBOARD</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>NAME</th><th>SCORE</th><th>WAVE</th><th>KILLS</th><th>DATE</th>
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
          ${r.ai_review ? `
          <tr class="review-row">
            <td></td>
            <td colspan="5" class="ai-review">
              <span class="ai-tag">⚡ AI DIRECTOR</span>${r.ai_review}
            </td>
          </tr>` : ''}
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