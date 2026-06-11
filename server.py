"""
server.py — FastAPI leaderboard + analytics server with PostgreSQL backend.

Deployed on Railway — reads DATABASE_URL environment variable automatically.
Run locally: uvicorn server:app --reload

ENDPOINTS:
  POST /score          — submit a run
  GET  /scores         — top 10 leaderboard (JSON)
  GET  /               — leaderboard HTML page
  GET  /analytics      — analytics dashboard HTML page
  GET  /analytics/summary        — overall stats JSON
  GET  /analytics/wave-distribution — wave reached distribution JSON
  GET  /analytics/accuracy-trend    — accuracy over time JSON
  GET  /analytics/top-players       — per-player aggregated stats JSON
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


# ── Score routes ──────────────────────────────────────────────────────────────

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


# ── Analytics routes ──────────────────────────────────────────────────────────

@app.get("/analytics/summary")
def analytics_summary():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            COUNT(*)                        AS total_runs,
            ROUND(AVG(wave)::numeric, 1)    AS avg_wave,
            ROUND(AVG(score)::numeric, 0)   AS avg_score,
            ROUND(AVG(kills)::numeric, 1)   AS avg_kills,
            MAX(score)                      AS best_score,
            MAX(wave)                       AS best_wave,
            MAX(kills)                      AS most_kills,
            COUNT(DISTINCT name)            AS unique_players
        FROM scores
    """)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else {}


@app.get("/analytics/wave-distribution")
def wave_distribution():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT wave, COUNT(*) AS runs
        FROM scores
        GROUP BY wave
        ORDER BY wave ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/analytics/accuracy-trend")
def accuracy_trend():
    """Returns last 20 runs ordered by time for trend display."""
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            id,
            name,
            score,
            wave,
            kills,
            posted_at,
            CASE
                WHEN kills > 0 THEN ROUND((kills::numeric / GREATEST(kills + 5, 1)) * 100, 1)
                ELSE 0
            END AS est_accuracy
        FROM scores
        ORDER BY id DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in list(reversed(rows))]


@app.get("/analytics/top-players")
def top_players():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT
            name,
            COUNT(*)                        AS total_runs,
            MAX(score)                      AS best_score,
            ROUND(AVG(score)::numeric, 0)   AS avg_score,
            MAX(wave)                       AS best_wave,
            ROUND(AVG(wave)::numeric, 1)    AS avg_wave,
            SUM(kills)                      AS total_kills
        FROM scores
        GROUP BY name
        ORDER BY best_score DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# ── Analytics dashboard page ──────────────────────────────────────────────────

@app.get("/analytics", response_class=HTMLResponse)
def analytics_page():
    return """
<!DOCTYPE html>
<html>
<head>
  <title>DEADZONE — Analytics</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0a0c12;
      color: #fff;
      font-family: 'Courier New', monospace;
      padding: 40px 20px;
      min-height: 100vh;
    }
    .header {
      text-align: center;
      margin-bottom: 48px;
    }
    h1 {
      font-size: 48px;
      color: #00dcb4;
      letter-spacing: 8px;
      text-shadow: 0 0 20px #00dcb4;
      margin-bottom: 6px;
    }
    .subtitle { color: #4a5570; letter-spacing: 4px; font-size: 13px; }
    .nav {
      text-align: center;
      margin-bottom: 40px;
    }
    .nav a {
      color: #4a5570;
      text-decoration: none;
      letter-spacing: 2px;
      font-size: 13px;
      margin: 0 16px;
      transition: color 0.2s;
    }
    .nav a:hover { color: #00dcb4; }
    .nav a.active { color: #00dcb4; }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      max-width: 900px;
      margin: 0 auto 40px;
    }
    .stat-card {
      background: #0e1118;
      border: 1px solid #1e2438;
      border-radius: 8px;
      padding: 20px;
      text-align: center;
    }
    .stat-card .value {
      font-size: 36px;
      font-weight: bold;
      color: #00dcb4;
      margin-bottom: 6px;
    }
    .stat-card .label {
      font-size: 11px;
      color: #4a5570;
      letter-spacing: 2px;
    }

    .section {
      max-width: 900px;
      margin: 0 auto 40px;
    }
    .section h2 {
      font-size: 14px;
      letter-spacing: 3px;
      color: #4a5570;
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid #1e2438;
    }

    /* Bar chart */
    .bar-chart { display: flex; flex-direction: column; gap: 8px; }
    .bar-row { display: flex; align-items: center; gap: 12px; }
    .bar-label { width: 60px; font-size: 13px; color: #6a7590; text-align: right; flex-shrink: 0; }
    .bar-track { flex: 1; background: #12151f; border-radius: 3px; height: 24px; position: relative; }
    .bar-fill { height: 100%; border-radius: 3px; transition: width 0.6s ease; }
    .bar-count { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 12px; color: #fff; }

    /* Line chart canvas */
    canvas { width: 100%; background: #0e1118; border: 1px solid #1e2438; border-radius: 8px; display: block; }

    /* Players table */
    table { width: 100%; border-collapse: collapse; }
    th { color: #4a5570; font-size: 11px; letter-spacing: 2px; padding: 10px 14px; text-align: left; border-bottom: 1px solid #1e2438; }
    td { padding: 12px 14px; font-size: 14px; border-bottom: 1px solid #0e1118; }
    tr:hover td { background: #0e1118; }
    .pname { color: #00dcb4; }
    .pgold { color: #ffc832; font-weight: bold; }
    .pred  { color: #ff3246; }
    .pgray { color: #4a5570; }
  </style>
</head>
<body>
  <div class="header">
    <h1>DEADZONE</h1>
    <div class="subtitle">ANALYTICS DASHBOARD</div>
  </div>

  <div class="nav">
    <a href="/">LEADERBOARD</a>
    <a href="/analytics" class="active">ANALYTICS</a>
  </div>

  <!-- Summary cards -->
  <div class="grid" id="summary-grid">
    <div class="stat-card"><div class="value" id="s-runs">—</div><div class="label">TOTAL RUNS</div></div>
    <div class="stat-card"><div class="value" id="s-players">—</div><div class="label">UNIQUE PLAYERS</div></div>
    <div class="stat-card"><div class="value" id="s-avg-wave">—</div><div class="label">AVG WAVE</div></div>
    <div class="stat-card"><div class="value" id="s-best-wave">—</div><div class="label">BEST WAVE</div></div>
    <div class="stat-card"><div class="value" id="s-best-score">—</div><div class="label">BEST SCORE</div></div>
    <div class="stat-card"><div class="value" id="s-avg-kills">—</div><div class="label">AVG KILLS</div></div>
  </div>

  <!-- Wave distribution bar chart -->
  <div class="section">
    <h2>WAVE DISTRIBUTION — WHERE PLAYERS DIE</h2>
    <div class="bar-chart" id="wave-bars"></div>
  </div>

  <!-- Score trend line chart -->
  <div class="section">
    <h2>SCORE TREND — LAST 20 RUNS</h2>
    <canvas id="trend-canvas" height="200"></canvas>
  </div>

  <!-- Top players table -->
  <div class="section">
    <h2>PLAYER STATS</h2>
    <table>
      <thead>
        <tr>
          <th>#</th><th>NAME</th><th>BEST SCORE</th><th>AVG SCORE</th>
          <th>BEST WAVE</th><th>AVG WAVE</th><th>TOTAL KILLS</th><th>RUNS</th>
        </tr>
      </thead>
      <tbody id="players-tbody"></tbody>
    </table>
  </div>

  <script>
    // ── Summary ──────────────────────────────────────────────────────────────
    async function loadSummary() {
      const r = await fetch('/analytics/summary');
      const d = await r.json();
      document.getElementById('s-runs').textContent       = d.total_runs       ?? '—';
      document.getElementById('s-players').textContent    = d.unique_players   ?? '—';
      document.getElementById('s-avg-wave').textContent   = d.avg_wave         ?? '—';
      document.getElementById('s-best-wave').textContent  = d.best_wave        ?? '—';
      document.getElementById('s-best-score').textContent = d.best_score?.toLocaleString() ?? '—';
      document.getElementById('s-avg-kills').textContent  = d.avg_kills        ?? '—';
    }

    // ── Wave distribution ─────────────────────────────────────────────────────
    async function loadWaveDist() {
      const r    = await fetch('/analytics/wave-distribution');
      const data = await r.json();
      if (!data.length) return;

      const max  = Math.max(...data.map(d => d.runs));
      const colors = ['#ff3246','#ff6432','#ffc832','#00dcb4','#00b4ff','#a064ff'];

      const container = document.getElementById('wave-bars');
      container.innerHTML = data.map((d, i) => `
        <div class="bar-row">
          <div class="bar-label">W${d.wave}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${(d.runs/max*100).toFixed(1)}%;background:${colors[i%colors.length]}"></div>
            <span class="bar-count">${d.runs} run${d.runs > 1 ? 's' : ''}</span>
          </div>
        </div>
      `).join('');
    }

    // ── Score trend line chart ────────────────────────────────────────────────
    async function loadTrend() {
      const r    = await fetch('/analytics/accuracy-trend');
      const data = await r.json();
      if (!data.length) return;

      const canvas = document.getElementById('trend-canvas');
      canvas.width = canvas.parentElement.offsetWidth;
      const ctx    = canvas.getContext('2d');
      const W      = canvas.width;
      const H      = canvas.height;
      const pad    = 40;

      const scores = data.map(d => d.score);
      const minS   = Math.min(...scores);
      const maxS   = Math.max(...scores);
      const range  = maxS - minS || 1;

      // Background
      ctx.fillStyle = '#0e1118';
      ctx.fillRect(0, 0, W, H);

      // Grid lines
      ctx.strokeStyle = '#1e2438';
      ctx.lineWidth   = 1;
      for (let i = 0; i <= 4; i++) {
        const y = pad + (H - pad * 2) * (i / 4);
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(W - pad, y);
        ctx.stroke();
        const val = Math.round(maxS - (range * i / 4));
        ctx.fillStyle = '#4a5570';
        ctx.font      = '11px Courier New';
        ctx.fillText(val.toLocaleString(), 4, y + 4);
      }

      // Line
      ctx.strokeStyle = '#00dcb4';
      ctx.lineWidth   = 2;
      ctx.beginPath();
      data.forEach((d, i) => {
        const x = pad + (i / (data.length - 1 || 1)) * (W - pad * 2);
        const y = pad + (1 - (d.score - minS) / range) * (H - pad * 2);
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      });
      ctx.stroke();

      // Dots
      data.forEach((d, i) => {
        const x = pad + (i / (data.length - 1 || 1)) * (W - pad * 2);
        const y = pad + (1 - (d.score - minS) / range) * (H - pad * 2);
        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = '#00dcb4';
        ctx.fill();
      });

      // X labels (every 5th)
      data.forEach((d, i) => {
        if (i % 5 !== 0 && i !== data.length - 1) return;
        const x = pad + (i / (data.length - 1 || 1)) * (W - pad * 2);
        ctx.fillStyle = '#4a5570';
        ctx.font      = '10px Courier New';
        ctx.fillText(d.posted_at?.slice(5) ?? '', x - 18, H - 8);
      });
    }

    // ── Top players table ─────────────────────────────────────────────────────
    async function loadPlayers() {
      const r    = await fetch('/analytics/top-players');
      const data = await r.json();
      const tbody = document.getElementById('players-tbody');
      if (!data.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#2a3048;padding:40px">NO DATA YET</td></tr>';
        return;
      }
      tbody.innerHTML = data.map((p, i) => `
        <tr>
          <td class="pgray">#${i+1}</td>
          <td class="pname">${p.name}</td>
          <td class="pgold">${Number(p.best_score).toLocaleString()}</td>
          <td class="pgray">${Number(p.avg_score).toLocaleString()}</td>
          <td class="pgold">${p.best_wave}</td>
          <td class="pgray">${p.avg_wave}</td>
          <td class="pred">${p.total_kills}</td>
          <td class="pgray">${p.total_runs}</td>
        </tr>
      `).join('');
    }

    // Load all
    Promise.all([loadSummary(), loadWaveDist(), loadTrend(), loadPlayers()]);
  </script>
</body>
</html>
"""


# ── Leaderboard page ──────────────────────────────────────────────────────────

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
    .subtitle { color: #4a5570; letter-spacing: 4px; font-size: 13px; margin-bottom: 12px; }
    .nav { margin-bottom: 32px; }
    .nav a {
      color: #4a5570;
      text-decoration: none;
      letter-spacing: 2px;
      font-size: 13px;
      margin: 0 16px;
      transition: color 0.2s;
    }
    .nav a:hover { color: #00dcb4; }
    .nav a.active { color: #00dcb4; }
    table { width: 100%; max-width: 700px; border-collapse: collapse; }
    thead tr { border-bottom: 1px solid #1e2438; }
    th { color: #4a5570; font-size: 12px; letter-spacing: 2px; padding: 10px 16px; text-align: left; }
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
    .empty { color: #2a3048; text-align: center; padding: 60px; font-size: 14px; letter-spacing: 2px; }
    .refresh { margin-top: 30px; color: #2a3048; font-size: 12px; letter-spacing: 2px; }
    .live-dot {
      display: inline-block; width: 6px; height: 6px;
      background: #00dcb4; border-radius: 50%; margin-right: 6px;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.2; } }
    .review-row td { padding: 0 16px 14px 16px; border-bottom: 1px solid #12151f; }
    .review-row:hover td { background: #12151f; }
    .ai-review { color: #6a7590; font-size: 12px; line-height: 1.6; font-style: italic; letter-spacing: 0.3px; }
    .ai-tag { color: #00dcb4; font-style: normal; font-size: 10px; letter-spacing: 2px; margin-right: 8px; opacity: 0.7; }
  </style>
</head>
<body>
  <h1>DEADZONE</h1>
  <div class="subtitle">ZOMBIE SURVIVAL &nbsp;•&nbsp; LEADERBOARD</div>
  <div class="nav">
    <a href="/" class="active">LEADERBOARD</a>
    <a href="/analytics">ANALYTICS</a>
  </div>
  <table>
    <thead>
      <tr><th>#</th><th>NAME</th><th>SCORE</th><th>WAVE</th><th>KILLS</th><th>DATE</th></tr>
    </thead>
    <tbody id="rows">
      <tr><td colspan="6" class="empty">Loading...</td></tr>
    </tbody>
  </table>
  <div class="refresh"><span class="live-dot"></span>AUTO-REFRESHES EVERY 10 SECONDS</div>
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