# DEADZONE

> A top-down neon tactical zombie survival shooter — built not as a game project, but as a **systems engineering project** using a game as the implementation surface.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Pygame](https://img.shields.io/badge/Pygame-2.6+-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Railway-blue)
![Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20LLaMA3-orange)
![ChromaDB](https://img.shields.io/badge/RAG-ChromaDB-purple)

**Project site:** https://deadzone-production-759b.up.railway.app  
**Leaderboard:** https://deadzone-production-759b.up.railway.app  
**Analytics:** https://deadzone-production-759b.up.railway.app/analytics

---

## What This Actually Is

Most student game projects are a game loop with some sprites. This is different.

DEADZONE implements a production-style AI pipeline, a deployed REST backend with JWT authentication, a RAG persistent memory system, a real-time analytics dashboard, a death heatmap, and a cinematic project website — the game is the interface through which all of these systems are demonstrated.

---

## Quick Start

```bash
git clone https://github.com/VATSALSHARMA1511/dead_Zone
cd dead_Zone
pip install -r requirements.txt
python main.py
```

The backend is already live on Railway — scores, leaderboard, AI director, and analytics all work out of the box. No local server needed to play.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GAME CLIENT                             │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Auth    │───▶│  Game    │───▶│   HUD    │    │ Menus    │  │
│  │  Screen  │    │  Loop    │    │  System  │    │ System   │  │
│  └──────────┘    └────┬─────┘    └──────────┘    └──────────┘  │
│                       │                                         │
│         ┌─────────────┼─────────────┐                          │
│         ▼             ▼             ▼                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Collision│  │  Wave    │  │Particles │                      │
│  │  System  │  │ Manager  │  │  System  │                      │
│  └──────────┘  └────┬─────┘  └──────────┘                      │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
   ┌─────────────┐  ┌──────────┐  ┌──────────────┐
   │  Groq API   │  │ChromaDB  │  │  FastAPI     │
   │  LLaMA 3.3  │  │ RAG Store│  │  + PostgreSQL│
   │  70B        │  │(local)   │  │  (Railway)   │
   └─────────────┘  └──────────┘  └──────────────┘
```

---

## Core Systems

### 1. AI Wave Director
Every wave that ends triggers a background-threaded Groq API call. The director receives:
- Current wave number
- Per-wave stats: kills, damage taken, accuracy, time
- Last 5 waves of run history with compositions

Returns a validated, normalized JSON wave composition applied to the next wave. Boss waves are deterministic — the AI has no say on wave % 5 == 0.

```python
# Wave-anchored difficulty floor — wave 10 cannot have only 6 zombies
min_zombies = max(6, 4 + next_wave * 2)
max_zombies = min(60, 10 + next_wave * 4)
```

### 2. RAG Persistent Memory
Each completed run is converted to natural language, embedded with `sentence-transformers/all-MiniLM-L6-v2`, and stored in a local ChromaDB vector database. Before each wave composition request, the top 3 semantically similar past runs are retrieved and injected into the Groq prompt.

```
Run ends
  → Natural language summary generated
  → Embedded (sentence-transformers, local)
  → Stored in ChromaDB (persistent, ./deadzone_memory/)

Next wave requested
  → Current session stats → query vector
  → ChromaDB cosine similarity search
  → Top 3 similar runs retrieved
  → Injected into Groq prompt as historical context
  → Wave composition generated
```

Same RAG architecture used in enterprise document Q&A systems.

### 3. JWT Authentication
Players register or login before playing. Credentials verified against PostgreSQL, passwords hashed with bcrypt. JWT tokens issued on success, sent as `Authorization: Bearer` header on every score POST. Guest play is supported — scores post without a token, `user_id = NULL`.

```
POST /auth/register  →  bcrypt hash + store  →  JWT token
POST /auth/login     →  bcrypt verify        →  JWT token
POST /score          →  JWT verify           →  link run to user_id
GET  /player/<name>  →  fetch runs by user_id →  profile page
```

### 4. Death Heatmap
Every player death posts `(x, y, wave)` world coordinates to the backend. A server-side matplotlib + scipy pipeline applies Gaussian blur over all death coordinates and returns a base64 PNG heatmap — showing exactly where the map kills players most. Auto-refreshes every 15 seconds on the analytics dashboard.

```
POST /heatmap/death        →  log (x, y, wave) to PostgreSQL
GET  /analytics/heatmap    →  matplotlib Gaussian blur → base64 PNG
```

### 5. Backend & Analytics
Deployed FastAPI on Railway with PostgreSQL. Full analytics dashboard at `/analytics`.

| Endpoint | Description |
|----------|-------------|
| `POST /score` | Submit run with name, score, wave, kills, ai_review |
| `GET /scores` | Top 10 leaderboard JSON |
| `GET /analytics/summary` | Total runs, unique players, best wave, best score |
| `GET /analytics/wave-distribution` | Where players die by wave number |
| `GET /analytics/heatmap` | Gaussian death heatmap PNG (base64) |
| `GET /analytics/accuracy-trend` | Last 20 runs score trend |
| `GET /analytics/top-players` | Per-player aggregated stats |
| `GET /player/<name>` | Full player profile with run history |

### 6. Collision System
Centralised — all collision logic in one file, zero circular imports. Returns hit count per frame which feeds directly into per-wave accuracy tracking.

```
bullets ↔ zombies   → damage + hit count (for accuracy)
player  ↔ zombies   → damage + iframes check
zombie  ↔ zombie    → separation push (prevents stacking)
player  ↔ obstacles → AABB resolution
zombie  ↔ obstacles → AABB resolution (0.7 damping)
```

### 7. Game Over AI Analysis
On death, a separate Groq call generates a ~200 character tactical analysis of the run — specific, slightly sarcastic, referencing actual stats. Runs in a background thread. `_delayed_post` waits up to 6 seconds for analysis to complete before posting score, so the AI review always ships with the score.

### 8. Project Website
Cinematic single-page site built with a custom WebGL CPPN shader background (same architecture as Framer's SpectraNoise), cursor glow, scroll-driven reveal animations, live leaderboard embed, and live analytics data — all pulling from the Railway backend in real time. Fully responsive with mobile WebGL fallbacks.

---

## File Structure

```
├── main.py              — Entry point, pygame init, game loop
├── game.py              — Core game loop, state machine, score posting, death heatmap
├── player.py            — Player entity, weapons, dash, stamina, HP penalties
├── zombie.py            — Zombie entity, 4-type system, smooth movement
├── bullet.py            — Bullet entity, lifetime, velocity
├── collision.py         — Centralised collision system (returns hit count)
├── waves.py             — Wave manager, AI director, Groq integration, RAG injection
├── rag_director.py      — RAG pipeline, ChromaDB, sentence-transformers
├── hud.py               — HUD rendering, wave summary, S/A/B/C/D grading
├── menus.py             — Auth screen, sprite picker, game over + AI analysis
├── camera.py            — Camera, screen shake, world↔screen transform
├── particles.py         — Particle system: blood, muzzle flash, dash trail
├── obstacle.py          — Obstacle rendering and collision data
├── settings.py          — All config values, colours, balance tuning
├── constants.py         — Enums: GameState, ZombieType, WeaponSlot
├── helpers.py           — Pure math/draw utilities
├── sprite_store.py      — Module singleton for custom sprites
├── player_name_store.py — Session singleton: name, token, is_guest
├── server.py            — FastAPI backend (deployed on Railway)
├── index.html           — Project website (WebGL shader, live data)
├── requirements.txt     — All dependencies
└── deadzone_memory/     — ChromaDB vector store (local, gitignored)
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Game engine | Python, Pygame 2.6 |
| LLM API | Groq (llama-3.3-70b-versatile) |
| Vector DB | ChromaDB |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Backend | FastAPI |
| Database | PostgreSQL |
| Auth | JWT (python-jose) + bcrypt |
| Deployment | Railway |
| Analytics | matplotlib, scipy, numpy |
| Website | Vanilla HTML/CSS/JS, WebGL CPPN shader |

---

## Running Locally

### Prerequisites
Python 3.10+

```bash
pip install -r requirements.txt
```

### Environment variables
Create a `.env` in the project root:
```
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=postgresql://...  # Railway provides this automatically
JWT_SECRET=your-secret-key
```

### Run the game
```bash
python main.py
```
Backend is live on Railway — no local server needed.

### Run the backend locally (optional)
```bash
uvicorn server:app --reload
```

---

## Controls

| Key | Action |
|-----|--------|
| WASD | Move |
| Shift | Sprint |
| Space | Dash (iframes) |
| LMB | Shoot |
| R | Reload |
| 1 / 2 / 3 | Switch weapon |
| Scroll | Switch weapon |
| ESC | Pause |

---

## Balance Tuning

All values in `settings.py`:

| Setting | Effect |
|---------|--------|
| `WAVE_COUNT_SCALE` | Zombie count growth per wave |
| `WAVE_BOSS_EVERY` | Boss wave frequency (default: 5) |
| `WAVE_COOLDOWN` | Seconds between waves |
| `PLAYER_DASH_COOLDOWN` | Dash recharge time |
| `PLAYER_IFRAMES` | Invincibility window after hit |
| `WEAPONS[*].fire_rate` | Fire rate per weapon |
| `ZOMBIE_TYPES[*].speed` | Base speed per type |