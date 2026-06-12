"""
server.py — FastAPI leaderboard + analytics + auth server.

ENDPOINTS:
  POST /auth/register  — create account, returns JWT
  POST /auth/login     — login, returns JWT
  POST /score          — submit run (optional JWT for profile linking)
  GET  /scores         — top 10 leaderboard JSON
  GET  /player/<name>  — player profile page
  GET  /               — leaderboard HTML
  GET  /analytics      — analytics dashboard HTML
  GET  /analytics/summary
  GET  /analytics/wave-distribution
  GET  /analytics/accuracy-trend
  GET  /analytics/top-players
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter
import os
import bcrypt
import io
import base64
from datetime import datetime, timedelta
from typing import Optional
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("JWT_SECRET", "deadzone-secret-key-change-in-prod")
ALGORITHM  = "HS256"
TOKEN_EXP  = 30   # days

security = HTTPBearer(auto_error=False)

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
            ai_review TEXT    DEFAULT '',
            user_id   INTEGER DEFAULT NULL
        )
    """)
    cur.execute("ALTER TABLE scores ADD COLUMN IF NOT EXISTS ai_review TEXT DEFAULT ''")
    cur.execute("ALTER TABLE scores ADD COLUMN IF NOT EXISTS user_id   INTEGER DEFAULT NULL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS heatmap_points (
            id       SERIAL PRIMARY KEY,
            x        INTEGER NOT NULL,
            y        INTEGER NOT NULL,
            wave     INTEGER NOT NULL,
            world_w  INTEGER NOT NULL DEFAULT 3200,
            world_h  INTEGER NOT NULL DEFAULT 2400,
            logged_at TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


init_db()

# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_token(user_id: int, username: str) -> str:
    payload = {
        "sub":      str(user_id),
        "username": username,
        "exp":      datetime.utcnow() + timedelta(days=TOKEN_EXP),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Returns user dict if valid token, None if guest/no token."""
    if not creds:
        return None
    payload = decode_token(creds.credentials)
    return payload   # {"sub": "id", "username": "name"} or None

# ── Models ────────────────────────────────────────────────────────────────────

class AuthRequest(BaseModel):
    username: str
    password: str

class ScoreSubmission(BaseModel):
    name:      str
    score:     int
    wave:      int
    kills:     int
    ai_review: str = ""

# ── Auth routes ───────────────────────────────────────────────────────────────

@app.post("/auth/register")
def register(data: AuthRequest):
    username = data.username.strip()[:20]
    if len(username) < 3:
        raise HTTPException(400, "Username must be at least 3 characters.")
    if len(data.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters.")

    pw_hash = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()

    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
            (username, pw_hash, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        user_id = cur.fetchone()[0]
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(409, "Username already taken.")
    finally:
        cur.close()
        conn.close()

    return {"token": create_token(user_id, username), "username": username}


@app.post("/auth/login")
def login(data: AuthRequest):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM users WHERE username = %s", (data.username.strip(),))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        raise HTTPException(401, "Invalid username or password.")
    if not bcrypt.checkpw(data.password.encode(), user["password_hash"].encode()):
        raise HTTPException(401, "Invalid username or password.")

    return {"token": create_token(user["id"], user["username"]), "username": user["username"]}


# ── Score routes ──────────────────────────────────────────────────────────────

@app.post("/score")
def submit_score(data: ScoreSubmission,
                 user=Depends(get_current_user)):
    user_id = int(user["sub"]) if user else None

    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO scores (name, score, wave, kills, posted_at, ai_review, user_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (data.name[:20], data.score, data.wave, data.kills,
         datetime.now().strftime("%Y-%m-%d %H:%M"), data.ai_review[:800], user_id)
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


# ── Player profile route ──────────────────────────────────────────────────────

@app.get("/player/{username}", response_class=HTMLResponse)
def player_profile(username: str):
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get user
    cur.execute("SELECT id, username, created_at FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    if not user:
        cur.close(); conn.close()
        raise HTTPException(404, "Player not found.")

    # Get all runs for this user
    cur.execute("""
        SELECT score, wave, kills, posted_at, ai_review
        FROM scores WHERE user_id = %s
        ORDER BY posted_at DESC LIMIT 50
    """, (user["id"],))
    runs = [dict(r) for r in cur.fetchall()]

    # Aggregate stats
    cur.execute("""
        SELECT
            COUNT(*)                      AS total_runs,
            MAX(score)                    AS best_score,
            ROUND(AVG(score)::numeric,0)  AS avg_score,
            MAX(wave)                     AS best_wave,
            ROUND(AVG(wave)::numeric,1)   AS avg_wave,
            SUM(kills)                    AS total_kills
        FROM scores WHERE user_id = %s
    """, (user["id"],))
    stats = dict(cur.fetchone())
    cur.close()
    conn.close()

    runs_html = ""
    for r in runs:
        review_html = f'<div class="run-review"><span class="ai-tag">⚡ AI</span>{r["ai_review"]}</div>' if r["ai_review"] else ""
        runs_html += f"""
        <div class="run-card">
          <div class="run-stats">
            <span class="run-score">{int(r['score']):,}</span>
            <span class="run-stat">WAVE {r['wave']}</span>
            <span class="run-stat red">{r['kills']} KILLS</span>
            <span class="run-date">{r['posted_at']}</span>
          </div>
          {review_html}
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>DEADZONE — {user['username']}</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ background:#0a0c12; color:#fff; font-family:'Courier New',monospace; padding:40px 20px; }}
    .header {{ text-align:center; margin-bottom:40px; }}
    h1 {{ font-size:42px; color:#00dcb4; letter-spacing:6px; text-shadow:0 0 20px #00dcb4; }}
    .joined {{ color:#2a3048; font-size:12px; letter-spacing:2px; margin-top:6px; }}
    .nav {{ text-align:center; margin-bottom:32px; }}
    .nav a {{ color:#4a5570; text-decoration:none; letter-spacing:2px; font-size:13px; margin:0 16px; }}
    .nav a:hover {{ color:#00dcb4; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; max-width:800px; margin:0 auto 40px; }}
    .card {{ background:#0e1118; border:1px solid #1e2438; border-radius:8px; padding:18px; text-align:center; }}
    .card .val {{ font-size:30px; font-weight:bold; color:#00dcb4; }}
    .card .lbl {{ font-size:11px; color:#4a5570; letter-spacing:2px; margin-top:4px; }}
    .runs {{ max-width:800px; margin:0 auto; }}
    .runs h2 {{ font-size:13px; letter-spacing:3px; color:#4a5570; margin-bottom:16px; border-bottom:1px solid #1e2438; padding-bottom:8px; }}
    .run-card {{ background:#0e1118; border:1px solid #1e2438; border-radius:6px; padding:14px 18px; margin-bottom:10px; }}
    .run-stats {{ display:flex; align-items:center; gap:20px; flex-wrap:wrap; }}
    .run-score {{ color:#ffc832; font-weight:bold; font-size:20px; min-width:80px; }}
    .run-stat {{ color:#fff; font-size:13px; }}
    .run-stat.red {{ color:#ff3246; }}
    .run-date {{ color:#2a3048; font-size:12px; margin-left:auto; }}
    .run-review {{ color:#6a7590; font-size:12px; font-style:italic; margin-top:8px; line-height:1.5; }}
    .ai-tag {{ color:#00dcb4; font-style:normal; font-size:10px; letter-spacing:2px; margin-right:8px; opacity:0.7; }}
    .empty {{ color:#2a3048; text-align:center; padding:40px; letter-spacing:2px; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>{user['username']}</h1>
    <div class="joined">JOINED {user['created_at']}</div>
  </div>
  <div class="nav">
    <a href="/">LEADERBOARD</a>
    <a href="/analytics">ANALYTICS</a>
    <a href="/player/{user['username']}">MY PROFILE</a>
  </div>
  <div class="grid">
    <div class="card"><div class="val">{stats['total_runs'] or 0}</div><div class="lbl">TOTAL RUNS</div></div>
    <div class="card"><div class="val">{int(stats['best_score'] or 0):,}</div><div class="lbl">BEST SCORE</div></div>
    <div class="card"><div class="val">{int(stats['avg_score'] or 0):,}</div><div class="lbl">AVG SCORE</div></div>
    <div class="card"><div class="val">{stats['best_wave'] or 0}</div><div class="lbl">BEST WAVE</div></div>
    <div class="card"><div class="val">{stats['avg_wave'] or 0}</div><div class="lbl">AVG WAVE</div></div>
    <div class="card"><div class="val">{stats['total_kills'] or 0}</div><div class="lbl">TOTAL KILLS</div></div>
  </div>
  <div class="runs">
    <h2>RUN HISTORY</h2>
    {runs_html if runs_html else '<div class="empty">NO RUNS YET</div>'}
  </div>
</body>
</html>"""


# ── Heatmap routes ───────────────────────────────────────────────────────────

class DeathPoint(BaseModel):
    x:       int
    y:       int
    wave:    int
    world_w: int = 3200
    world_h: int = 2400


@app.post("/heatmap/death")
def log_death(data: DeathPoint):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(
        "INSERT INTO heatmap_points (x, y, wave, world_w, world_h, logged_at) VALUES (%s,%s,%s,%s,%s,%s)",
        (data.x, data.y, data.wave, data.world_w, data.world_h,
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "ok"}


@app.get("/analytics/heatmap")
def get_heatmap():
    """Generate and return a heatmap PNG as base64."""
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT x, y, wave FROM heatmap_points ORDER BY id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    if not rows:
        return {"image": None, "count": 0}

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        import numpy as np

        WORLD_W, WORLD_H = 3200, 2400

        xs = [r["x"] for r in rows]
        ys = [r["y"] for r in rows]

        fig, ax = plt.subplots(figsize=(10, 7.5))
        fig.patch.set_facecolor("#0a0c12")
        ax.set_facecolor("#0a0c12")

        # 2D histogram heatmap
        h, xedges, yedges = np.histogram2d(xs, ys,
                                            bins=40,
                                            range=[[0, WORLD_W], [0, WORLD_H]])

        # Smooth with gaussian blur
        from scipy.ndimage import gaussian_filter
        h = gaussian_filter(h, sigma=1.5)

        # Custom colormap: dark → red → yellow → white
        colors_list = ["#0a0c12", "#1a0505", "#ff0000", "#ff8800", "#ffff00", "#ffffff"]
        cmap = mcolors.LinearSegmentedColormap.from_list("deadzone", colors_list)

        im = ax.imshow(
            h.T,
            origin="lower",
            extent=[0, WORLD_W, 0, WORLD_H],
            cmap=cmap,
            aspect="auto",
            alpha=0.9,
            interpolation="bilinear",
        )

        # Death location dots
        ax.scatter(xs, ys, c="#ff3246", s=8, alpha=0.4, zorder=5)

        # Colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.ax.yaxis.set_tick_params(color="white")
        plt.setp(cbar.ax.yaxis.get_ticklabels(), color="white")
        cbar.set_label("Death Density", color="white", fontsize=10)

        ax.set_title(f"DEADZONE — Death Heatmap ({len(rows)} runs)",
                     color="#00dcb4", fontsize=14, fontfamily="monospace", pad=12)
        ax.set_xlabel("World X", color="#4a5570", fontsize=9)
        ax.set_ylabel("World Y", color="#4a5570", fontsize=9)
        ax.tick_params(colors="#4a5570")
        for spine in ax.spines.values():
            spine.set_edgecolor("#1e2438")

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, facecolor="#0a0c12")
        plt.close(fig)
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode()

        return {"image": img_b64, "count": len(rows)}

    except ImportError as e:
        return {"error": f"Missing dependency: {e}", "count": len(rows)}


# ── Analytics routes ──────────────────────────────────────────────────────────

@app.get("/analytics/summary")
def analytics_summary():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT COUNT(*) AS total_runs, ROUND(AVG(wave)::numeric,1) AS avg_wave,
               ROUND(AVG(score)::numeric,0) AS avg_score, ROUND(AVG(kills)::numeric,1) AS avg_kills,
               MAX(score) AS best_score, MAX(wave) AS best_wave, MAX(kills) AS most_kills,
               COUNT(DISTINCT name) AS unique_players
        FROM scores
    """)
    row = cur.fetchone()
    cur.close(); conn.close()
    return dict(row) if row else {}


@app.get("/analytics/wave-distribution")
def wave_distribution():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT wave, COUNT(*) AS runs FROM scores GROUP BY wave ORDER BY wave ASC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


@app.get("/analytics/accuracy-trend")
def accuracy_trend():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, name, score, wave, kills, posted_at FROM scores ORDER BY id DESC LIMIT 20
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in list(reversed(rows))]


@app.get("/analytics/top-players")
def top_players():
    conn = get_db()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT name, COUNT(*) AS total_runs, MAX(score) AS best_score,
               ROUND(AVG(score)::numeric,0) AS avg_score, MAX(wave) AS best_wave,
               ROUND(AVG(wave)::numeric,1) AS avg_wave, SUM(kills) AS total_kills
        FROM scores GROUP BY name ORDER BY best_score DESC LIMIT 10
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return [dict(r) for r in rows]


# ── Analytics dashboard ───────────────────────────────────────────────────────

@app.get("/analytics", response_class=HTMLResponse)
def analytics_page():
    return """<!DOCTYPE html>
<html>
<head>
  <title>DEADZONE — Analytics</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { background:#0a0c12; color:#fff; font-family:'Courier New',monospace; padding:40px 20px; }
    .header { text-align:center; margin-bottom:40px; }
    h1 { font-size:48px; color:#00dcb4; letter-spacing:8px; text-shadow:0 0 20px #00dcb4; margin-bottom:6px; }
    .subtitle { color:#4a5570; letter-spacing:4px; font-size:13px; }
    .nav { text-align:center; margin-bottom:40px; }
    .nav a { color:#4a5570; text-decoration:none; letter-spacing:2px; font-size:13px; margin:0 16px; }
    .nav a:hover, .nav a.active { color:#00dcb4; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; max-width:900px; margin:0 auto 40px; }
    .stat-card { background:#0e1118; border:1px solid #1e2438; border-radius:8px; padding:20px; text-align:center; }
    .stat-card .value { font-size:36px; font-weight:bold; color:#00dcb4; margin-bottom:6px; }
    .stat-card .label { font-size:11px; color:#4a5570; letter-spacing:2px; }
    .section { max-width:900px; margin:0 auto 40px; }
    .section h2 { font-size:13px; letter-spacing:3px; color:#4a5570; margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid #1e2438; }
    .bar-chart { display:flex; flex-direction:column; gap:8px; }
    .bar-row { display:flex; align-items:center; gap:12px; }
    .bar-label { width:60px; font-size:13px; color:#6a7590; text-align:right; flex-shrink:0; }
    .bar-track { flex:1; background:#12151f; border-radius:3px; height:24px; position:relative; }
    .bar-fill { height:100%; border-radius:3px; }
    .bar-count { position:absolute; right:8px; top:50%; transform:translateY(-50%); font-size:12px; color:#fff; }
    canvas { width:100%; background:#0e1118; border:1px solid #1e2438; border-radius:8px; display:block; }
    table { width:100%; border-collapse:collapse; }
    th { color:#4a5570; font-size:11px; letter-spacing:2px; padding:10px 14px; text-align:left; border-bottom:1px solid #1e2438; }
    td { padding:12px 14px; font-size:14px; border-bottom:1px solid #0e1118; }
    tr:hover td { background:#0e1118; }
    .pname { color:#00dcb4; text-decoration:none; }
    .pname:hover { text-decoration:underline; }
    .pgold { color:#ffc832; font-weight:bold; }
    .pred { color:#ff3246; }
    .pgray { color:#4a5570; }
  </style>
</head>
<body>
  <div class="header"><h1>DEADZONE</h1><div class="subtitle">ANALYTICS DASHBOARD</div></div>
  <div class="nav"><a href="/">LEADERBOARD</a><a href="/analytics" class="active">ANALYTICS</a></div>
  <div class="grid" id="summary-grid">
    <div class="stat-card"><div class="value" id="s-runs">—</div><div class="label">TOTAL RUNS</div></div>
    <div class="stat-card"><div class="value" id="s-players">—</div><div class="label">UNIQUE PLAYERS</div></div>
    <div class="stat-card"><div class="value" id="s-avg-wave">—</div><div class="label">AVG WAVE</div></div>
    <div class="stat-card"><div class="value" id="s-best-wave">—</div><div class="label">BEST WAVE</div></div>
    <div class="stat-card"><div class="value" id="s-best-score">—</div><div class="label">BEST SCORE</div></div>
    <div class="stat-card"><div class="value" id="s-avg-kills">—</div><div class="label">AVG KILLS</div></div>
  </div>
  <div class="section"><h2>WAVE DISTRIBUTION — WHERE PLAYERS DIE</h2><div class="bar-chart" id="wave-bars"></div></div>
  <div class="section"><h2>SCORE TREND — LAST 20 RUNS</h2><canvas id="trend-canvas" height="200"></canvas></div>
  <div class="section">
    <h2>DEATH HEATMAP</h2>
    <div id="heatmap-container" style="text-align:center;min-height:120px;display:flex;align-items:center;justify-content:center;">
      <span style="color:#2a3048;letter-spacing:2px;font-size:13px;">LOADING HEATMAP...</span>
    </div>
  </div>
  <div class="section">
    <h2>PLAYER STATS</h2>
    <table><thead><tr><th>#</th><th>NAME</th><th>BEST SCORE</th><th>AVG SCORE</th><th>BEST WAVE</th><th>AVG WAVE</th><th>TOTAL KILLS</th><th>RUNS</th></tr></thead>
    <tbody id="players-tbody"></tbody></table>
  </div>
  <script>
    async function loadSummary() {
      const d = await fetch('/analytics/summary').then(r=>r.json());
      document.getElementById('s-runs').textContent       = d.total_runs       ?? '—';
      document.getElementById('s-players').textContent    = d.unique_players   ?? '—';
      document.getElementById('s-avg-wave').textContent   = d.avg_wave         ?? '—';
      document.getElementById('s-best-wave').textContent  = d.best_wave        ?? '—';
      document.getElementById('s-best-score').textContent = d.best_score?.toLocaleString() ?? '—';
      document.getElementById('s-avg-kills').textContent  = d.avg_kills        ?? '—';
    }
    async function loadWaveDist() {
      const data = await fetch('/analytics/wave-distribution').then(r=>r.json());
      if (!data.length) return;
      const max = Math.max(...data.map(d=>d.runs));
      const colors = ['#ff3246','#ff6432','#ffc832','#00dcb4','#00b4ff','#a064ff'];
      document.getElementById('wave-bars').innerHTML = data.map((d,i) => `
        <div class="bar-row">
          <div class="bar-label">W${d.wave}</div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${(d.runs/max*100).toFixed(1)}%;background:${colors[i%colors.length]}"></div>
            <span class="bar-count">${d.runs}</span>
          </div>
        </div>`).join('');
    }
    async function loadTrend() {
      const data = await fetch('/analytics/accuracy-trend').then(r=>r.json());
      if (!data.length) return;
      const canvas = document.getElementById('trend-canvas');
      canvas.width = canvas.parentElement.offsetWidth;
      const ctx = canvas.getContext('2d'), W = canvas.width, H = canvas.height, pad = 40;
      const scores = data.map(d=>d.score), minS = Math.min(...scores), maxS = Math.max(...scores), range = maxS-minS||1;
      ctx.fillStyle='#0e1118'; ctx.fillRect(0,0,W,H);
      ctx.strokeStyle='#1e2438'; ctx.lineWidth=1;
      for(let i=0;i<=4;i++){const y=pad+(H-pad*2)*(i/4);ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(W-pad,y);ctx.stroke();ctx.fillStyle='#4a5570';ctx.font='11px Courier New';ctx.fillText(Math.round(maxS-(range*i/4)).toLocaleString(),4,y+4);}
      ctx.strokeStyle='#00dcb4'; ctx.lineWidth=2; ctx.beginPath();
      data.forEach((d,i)=>{const x=pad+(i/(data.length-1||1))*(W-pad*2),y=pad+(1-(d.score-minS)/range)*(H-pad*2);i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);});
      ctx.stroke();
      data.forEach((d,i)=>{const x=pad+(i/(data.length-1||1))*(W-pad*2),y=pad+(1-(d.score-minS)/range)*(H-pad*2);ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.fillStyle='#00dcb4';ctx.fill();});
    }
    async function loadPlayers() {
      const data = await fetch('/analytics/top-players').then(r=>r.json());
      const tbody = document.getElementById('players-tbody');
      if (!data.length) { tbody.innerHTML='<tr><td colspan="8" style="text-align:center;color:#2a3048;padding:40px">NO DATA YET</td></tr>'; return; }
      tbody.innerHTML = data.map((p,i) => `<tr>
        <td class="pgray">#${i+1}</td>
        <td><a class="pname" href="/player/${p.name}">${p.name}</a></td>
        <td class="pgold">${Number(p.best_score).toLocaleString()}</td>
        <td class="pgray">${Number(p.avg_score).toLocaleString()}</td>
        <td class="pgold">${p.best_wave}</td>
        <td class="pgray">${p.avg_wave}</td>
        <td class="pred">${p.total_kills}</td>
        <td class="pgray">${p.total_runs}</td>
      </tr>`).join('');
    }
    async function loadHeatmap() {
      const container = document.getElementById('heatmap-container');
      try {
        const d = await fetch('/analytics/heatmap').then(r=>r.json());
        if (!d.image) {
          container.innerHTML = '<span style="color:#2a3048;letter-spacing:2px;font-size:13px;">NO DEATH DATA YET — PLAY THE GAME</span>';
          return;
        }
        container.innerHTML = `
          <div style="width:100%">
            <img src="data:image/png;base64,${d.image}"
                 style="width:100%;border-radius:8px;border:1px solid #1e2438;"
                 alt="Death Heatmap"/>
            <div style="color:#4a5570;font-size:11px;letter-spacing:2px;margin-top:8px;text-align:right">
              ${d.count} DEATH${d.count !== 1 ? 'S' : ''} RECORDED
            </div>
          </div>`;
      } catch(e) {
        container.innerHTML = '<span style="color:#2a3048">HEATMAP UNAVAILABLE</span>';
      }
    }
    Promise.all([loadSummary(),loadWaveDist(),loadTrend(),loadHeatmap(),loadPlayers()]);
  </script>
</body>
</html>"""


# ── Leaderboard page ──────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def homepage():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()
@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page():
    return """<!DOCTYPE html>
<html>
<head>
  <title>DEADZONE — Leaderboard</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body { background:#0a0c12; color:#fff; font-family:'Courier New',monospace; display:flex; flex-direction:column; align-items:center; padding:40px 20px; min-height:100vh; }
    h1 { font-size:52px; color:#00dcb4; letter-spacing:8px; text-shadow:0 0 20px #00dcb4; margin-bottom:8px; }
    .subtitle { color:#4a5570; letter-spacing:4px; font-size:13px; margin-bottom:12px; }
    .nav { margin-bottom:32px; }
    .nav a { color:#4a5570; text-decoration:none; letter-spacing:2px; font-size:13px; margin:0 16px; }
    .nav a:hover, .nav a.active { color:#00dcb4; }
    table { width:100%; max-width:700px; border-collapse:collapse; }
    thead tr { border-bottom:1px solid #1e2438; }
    th { color:#4a5570; font-size:12px; letter-spacing:2px; padding:10px 16px; text-align:left; }
    td { padding:14px 16px; font-size:15px; border-bottom:1px solid #12151f; }
    tr:hover td { background:#12151f; }
    .rank { color:#4a5570; width:40px; }
    .rank.gold { color:#ffc832; font-weight:bold; }
    .rank.silver { color:#aab0c0; font-weight:bold; }
    .rank.bronze { color:#cd7f32; font-weight:bold; }
    .name { color:#00dcb4; text-decoration:none; }
    .name:hover { text-decoration:underline; }
    .score { color:#ffc832; font-weight:bold; font-size:17px; }
    .wave { color:#ffffff; }
    .kills { color:#ff3246; }
    .date { color:#2a3048; font-size:12px; }
    .empty { color:#2a3048; text-align:center; padding:60px; font-size:14px; letter-spacing:2px; }
    .refresh { margin-top:30px; color:#2a3048; font-size:12px; letter-spacing:2px; }
    .live-dot { display:inline-block; width:6px; height:6px; background:#00dcb4; border-radius:50%; margin-right:6px; animation:pulse 1.5s infinite; }
    @keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.2} }
    .review-row td { padding:0 16px 14px 16px; border-bottom:1px solid #12151f; }
    .review-row:hover td { background:#12151f; }
    .ai-review { color:#6a7590; font-size:12px; line-height:1.6; font-style:italic; }
    .ai-tag { color:#00dcb4; font-style:normal; font-size:10px; letter-spacing:2px; margin-right:8px; opacity:0.7; }
  </style>
</head>
<body>
  <h1>DEADZONE</h1>
  <div class="subtitle">ZOMBIE SURVIVAL &nbsp;•&nbsp; LEADERBOARD</div>
  <div class="nav"><a href="/leaderboard" class="active">LEADERBOARD</a><a href="/analytics">ANALYTICS</a></div>
  <table>
    <thead><tr><th>#</th><th>NAME</th><th>SCORE</th><th>WAVE</th><th>KILLS</th><th>DATE</th></tr></thead>
    <tbody id="rows"><tr><td colspan="6" class="empty">Loading...</td></tr></tbody>
  </table>
  <div class="refresh"><span class="live-dot"></span>AUTO-REFRESHES EVERY 10 SECONDS</div>
  <script>
    const rankLabel = i => i===0?'<span class="rank gold">#1</span>':i===1?'<span class="rank silver">#2</span>':i===2?'<span class="rank bronze">#3</span>':`<span class="rank">#${i+1}</span>`;
    async function load() {
      try {
        const data = await fetch('/scores').then(r=>r.json());
        const tbody = document.getElementById('rows');
        if (!data.length) { tbody.innerHTML='<tr><td colspan="6" class="empty">NO SCORES YET</td></tr>'; return; }
        tbody.innerHTML = data.map((r,i) => `
          <tr>
            <td>${rankLabel(i)}</td>
            <td><a class="name" href="/player/${r.name}">${r.name}</a></td>
            <td class="score">${r.score.toLocaleString()}</td>
            <td class="wave">${r.wave}</td>
            <td class="kills">${r.kills}</td>
            <td class="date">${r.posted_at}</td>
          </tr>
          ${r.ai_review?`<tr class="review-row"><td></td><td colspan="5" class="ai-review"><span class="ai-tag">⚡ AI DIRECTOR</span>${r.ai_review}</td></tr>`:''}
        `).join('');
      } catch(e) {
        document.getElementById('rows').innerHTML='<tr><td colspan="6" class="empty">SERVER OFFLINE</td></tr>';
      }
    }
    load(); setInterval(load, 10000);
  </script>
</body>
</html>"""