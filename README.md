# DEADZONE

> A top-down neon tactical zombie survival shooter — built not as a game project, but as a **systems engineering project** using a game as the implementation surface.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Pygame](https://img.shields.io/badge/Pygame-2.6+-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Railway-blue)
![Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20LLaMA3-orange)
![ChromaDB](https://img.shields.io/badge/RAG-ChromaDB-purple)

**Live backend:** https://deadzone-production-759b.up.railway.app  
**Leaderboard:** https://deadzone-production-759b.up.railway.app  
**Analytics:** https://deadzone-production-759b.up.railway.app/analytics

---

## What This Actually Is

Most student game projects are a game loop with some sprites. This is different.

DEADZONE implements a production-style AI pipeline, a deployed REST backend with JWT authentication, a RAG memory system, and a full analytics dashboard — the game is the interface through which all of these systems are demonstrated.

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

It returns a JSON wave composition (zombie count, type ratios, sector message) that is validated, normalized, and applied to the next wave. Boss waves are deterministic — the AI has no control over them.

```python
# Wave-anchored difficulty floor — wave 10 cannot get 6 zombies
min_zombies = max(6, 4 + next_wave * 2)
max_zombies = min(60, 10 + next_wave * 4)
```

### 2. RAG Persistent Memory
Each completed run is converted to a natural language summary, embedded using `sentence-transformers/all-MiniLM-L6-v2`, and stored in a local ChromaDB vector database.

Before generating each wave composition, ChromaDB is queried for semantically similar past runs using cosine similarity. The top 3 retrieved runs are injected into the Groq prompt as additional context.

**The pipeline:**
```
Run ends
  → Natural language summary generated
  → Embedded (sentence-transformers, local)
  → Stored in ChromaDB (persistent, ./deadzone_memory/)
  
Next wave requested
  → Current session stats → query vector
  → ChromaDB cosine similarity search
  → Top 3 similar runs retrieved
  → Injected into Groq prompt
  → Wave composition generated with historical context
```

This is the same RAG architecture used in enterprise document Q&A systems.

### 3. JWT Authentication
Players register or login before playing. Credentials verified against PostgreSQL, passwords hashed with bcrypt. JWT tokens issued on success, stored in session, sent as `Authorization: Bearer` header on every score POST.

```
POST /auth/register  →  bcrypt hash + store  →  JWT token
POST /auth/login     →  bcrypt verify        →  JWT token
POST /score          →  JWT verify           →  link run to user_id
GET  /player/<name>  →  fetch runs by user_id →  profile page
```

### 4. Collision System
Centralised collision detection — all collision logic in one system, zero circular imports. Returns hit count per frame which feeds directly into accuracy tracking.

```
bullets ↔ zombies   → damage + hit count (for accuracy)
player  ↔ zombies   → damage + iframes check
zombie  ↔ zombie    → separation push (prevents stacking)
player  ↔ obstacles → AABB resolution
zombie  ↔ obstacles → AABB resolution (0.7 damping)
```

### 5. Wave Summary + Grading
Between every wave, a summary panel displays kills, accuracy, and damage taken for the wave just completed. Each wave is graded S/A/B/C/D based on combined accuracy and damage metrics.

### 6. Game Over AI Analysis
On death, a separate Groq call generates a ~200 character tactical analysis of the run — specific, slightly sarcastic, referencing actual stats. Runs in a background thread. Stored to the database alongside the score.

---

## Backend

**Deployed on Railway — PostgreSQL database, auto-deploy from GitHub.**


## File Structure

```
├── main.py              — Entry point, pygame init, game loop
├── game.py              — Core game loop, state machine, score posting
├── player.py            — Player entity, weapons, dash, stamina
├── zombie.py            — Zombie entity, type system, AI movement
├── bullet.py            — Bullet entity, lifetime, velocity
├── collision.py         — Centralised collision system (returns hit count)
├── waves.py             — Wave manager, AI director, Groq integration
├── rag_director.py      — RAG pipeline, ChromaDB, embeddings
├── hud.py               — HUD rendering, wave summary, grading
├── menus.py             — All screens: auth, sprite picker, game over
├── camera.py            — Camera, screen shake, world↔screen transform
├── particles.py         — Particle system, blood, muzzle flash
├── obstacle.py          — Obstacle rendering and data
├── settings.py          — All config values, colours, balance tuning
├── constants.py         — Enums: GameState, ZombieType, WeaponSlot
├── helpers.py           — Pure math/draw utilities
├── sprite_store.py      — Module singleton for custom sprites
├── player_name_store.py — Module singleton for session: name, token, is_guest
├── server.py            — FastAPI backend (deployed on Railway)
└── deadzone_memory/     — ChromaDB vector store (local, gitignored)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Game engine | Python, Pygame 2.6 |
| LLM API | Groq (llama-3.3-70b-versatile) |
| Vector DB | ChromaDB |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Backend | FastAPI |
| Database | PostgreSQL |
| Auth | JWT (python-jose) + bcrypt |
| Deployment | Railway |

---

## Running Locally

### Prerequisites
```bash
pip install pygame fastapi psycopg2 groq chromadb sentence-transformers \
            python-dotenv uvicorn bcrypt python-jose[cryptography]
```

### Environment variables
Create a `.env` file:
```
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=postgresql://...  # Railway provides this automatically
JWT_SECRET=your-secret-key
```

### Run the game
```bash
python main.py
```

### Run the backend locally
```bash
uvicorn server:app --reload
```

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