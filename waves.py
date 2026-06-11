"""
waves.py — Wave-based zombie spawning with Groq AI adaptive difficulty.

AI INTEGRATION:
  After each wave ends, player performance stats + full run history are sent
  to Groq (Llama3) in a background thread. AI responds with wave composition
  for the NEXT wave. Falls back to normal logic if API unavailable or times out.

  Key fix: AI is requested at END of wave (not start), so the response
  arrives during cooldown and is ready when the next wave begins.
"""

import random
import math
import threading
import os
import json
import settings
from zombie import Zombie

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class WaveManager:
    def __init__(self, world_w: int, world_h: int) -> None:
        self.world_w = world_w
        self.world_h = world_h

        self.wave_number        = 0
        self.state              = "cooldown"
        self._cooldown_t        = 3.0
        self._spawn_queue       : list[str] = []
        self._spawn_timer       = 0.0
        self._spawn_interval    = 0.18

        self.cooldown_remaining = self._cooldown_t

        # ── AI system ─────────────────────────────────────────────────────
        self._ai_override       : dict | None = None
        self._ai_pending        = False
        self._ai_message        = ""
        self._ai_message_timer  = 0.0

        # Run-level history for AI context — grows each wave
        self._wave_history      : list[dict] = []

        # Per-wave stats (reset each wave)
        self.stat_kills_this_wave = 0
        self.stat_damage_taken    = 0
        self.stat_time_alive      = 0.0
        self.stat_bullets_fired   = 0
        self.stat_bullets_hit     = 0

        # Last wave composition sent, so AI knows the baseline it's adjusting from
        self._last_composition : dict = {
            "total_zombies": 6,
            "normal_ratio":  1.0,
            "fast_ratio":    0.0,
            "tank_ratio":    0.0,
            "boss":          False,
        }

    # ── Main update ──────────────────────────────────────────────────────────

    def update(self, dt: float, zombies: list, player) -> None:
        self.stat_time_alive += dt

        if self._ai_message_timer > 0:
            self._ai_message_timer -= dt

        if self.state == "cooldown":
            self._cooldown_t -= dt
            self.cooldown_remaining = max(0.0, self._cooldown_t)
            if self._cooldown_t <= 0:
                self._start_wave()

        elif self.state == "spawning":
            self._spawn_timer -= dt
            if self._spawn_timer <= 0 and self._spawn_queue:
                burst = min(2, len(self._spawn_queue))
                for _ in range(burst):
                    ztype = self._spawn_queue.pop(0)
                    z = self._create_zombie(ztype, player)
                    zombies.append(z)
                self._spawn_timer = self._spawn_interval
            if not self._spawn_queue:
                self.state = "active"

        elif self.state == "active":
            alive = sum(1 for z in zombies if z.alive)
            if alive == 0:
                self._end_wave()

    # ── Wave logic ───────────────────────────────────────────────────────────

    def _start_wave(self) -> None:
        self.wave_number += 1
        self.state = "spawning"

        is_boss = (self.wave_number % settings.WAVE_BOSS_EVERY == 0)

        if self._ai_override:
            composition = self._ai_override
            composition["boss"] = is_boss   # deterministic — AI doesn't decide this
            self._spawn_queue = self._composition_from_dict(composition)
            self._last_composition = composition
            self._ai_override = None
            print(f"[AI] Wave {self.wave_number} using AI composition: {self._last_composition}")
        else:
            self._spawn_queue = self._build_default_composition()
            print(f"[AI] Wave {self.wave_number} using fallback composition")

        self._spawn_timer = 0.0

        # Reset per-wave stats
        self.stat_kills_this_wave = 0
        self.stat_damage_taken    = 0
        self.stat_bullets_fired   = 0
        self.stat_bullets_hit     = 0

    def _end_wave(self) -> None:
        # Snapshot this wave's performance into history
        accuracy = round(
            (self.stat_bullets_hit / max(1, self.stat_bullets_fired)) * 100, 1
        )
        wave_record = {
            "wave":         self.wave_number,
            "kills":        self.stat_kills_this_wave,
            "damage_taken": self.stat_damage_taken,
            "time_sec":     int(self.stat_time_alive),
            "accuracy_pct": accuracy,
            "composition":  self._last_composition.copy(),
        }
        self._wave_history.append(wave_record)

        # Kick off AI request for the NEXT wave during cooldown
        if not self._ai_pending:
            self._request_ai_wave()

        self.state        = "cooldown"
        self._cooldown_t  = settings.WAVE_COOLDOWN
        self.cooldown_remaining = self._cooldown_t

    # ── Default fallback composition ─────────────────────────────────────────

    def _build_default_composition(self) -> list[str]:
        wn    = self.wave_number
        base  = settings.WAVE_BASE_COUNT
        total = int(base * (settings.WAVE_COUNT_SCALE ** (wn - 1)))
        total = min(total, 60)

        pool = ["normal"] * 10
        if wn >= settings.WAVE_FAST_UNLOCK:
            pool += ["fast"] * 5
        if wn >= settings.WAVE_TANK_UNLOCK:
            pool += ["tank"] * 3

        composition = [random.choice(pool) for _ in range(total)]
        if wn % settings.WAVE_BOSS_EVERY == 0:
            composition.append("boss")

        random.shuffle(composition)
        return composition

    # ── AI wave composition ───────────────────────────────────────────────────

    def _request_ai_wave(self) -> None:
        """Fire AI request in background thread during cooldown — never blocks game loop."""
        self._ai_pending = True

        # Snapshot everything the AI needs right now (thread-safe copy)
        next_wave     = self.wave_number + 1
        history_snap  = self._wave_history[-5:]  # last 5 waves max — keep prompt tight
        last_comp     = self._last_composition.copy()

        # Summarise recent trend for the prompt
        recent_kills  = sum(w["kills"]        for w in history_snap)
        recent_dmg    = sum(w["damage_taken"]  for w in history_snap)
        recent_acc    = round(
            sum(w["accuracy_pct"] for w in history_snap) / max(1, len(history_snap)), 1
        )

        # Wave-anchored zombie floor so wave 10 can't get 6 zombies
        min_zombies = max(6, 4 + next_wave * 2)
        max_zombies = min(60, 10 + next_wave * 4)

        def _call():
            try:
                from groq import Groq
                client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

                history_str = "\n".join(
                    f"  Wave {w['wave']}: {w['kills']} kills, "
                    f"{w['damage_taken']} dmg taken, "
                    f"{w['accuracy_pct']}% accuracy, "
                    f"{w['composition']['total_zombies']} zombies "
                    f"(N:{w['composition']['normal_ratio']:.1f} "
                    f"F:{w['composition']['fast_ratio']:.1f} "
                    f"T:{w['composition']['tank_ratio']:.1f})"
                    for w in history_snap
                )

                prompt = f"""You are the AI director for DEADZONE, a neon tactical zombie shooter.
Your job is to generate a zombie wave composition that creates a FAIR but ESCALATING challenge.

=== RUN HISTORY (last {len(history_snap)} waves) ===
{history_str if history_str else "  No history yet — this is wave 1."}

=== LAST WAVE COMPOSITION ===
  Zombies: {last_comp['total_zombies']}, Normal: {last_comp['normal_ratio']:.1f}, Fast: {last_comp['fast_ratio']:.1f}, Tank: {last_comp['tank_ratio']:.1f}

=== AGGREGATE PERFORMANCE ===
  Total kills (recent): {recent_kills}
  Total damage taken (recent): {recent_dmg} HP
  Average accuracy (recent): {recent_acc}%
  Next wave number: {next_wave}

=== SCALING RULES ===
  - Valid zombie count range for this wave: {min_zombies} to {max_zombies}
  - Wave number {next_wave} means the game should be noticeably harder than wave 1
  - ALWAYS increase total_zombies compared to last wave unless player is critically struggling (damage > 80 HP per wave average)
  - If player accuracy > 70% AND damage taken < 30: push harder — more zombies, higher fast/tank ratios
  - If player accuracy < 40% OR damage taken > 80: ease slightly — reduce fast/tank ratio, not total count
  - Never reduce total_zombies below {min_zombies}
  - Introduce fast zombies (fast_ratio > 0) from wave 2 onwards
  - Introduce tank zombies (tank_ratio > 0.1) from wave 4 onwards
  - Boss waves are handled by the game engine — do NOT include a boss field

Respond ONLY with valid JSON, no markdown, no explanation:
{{
  "total_zombies": <integer {min_zombies}-{max_zombies}>,
  "normal_ratio": <float 0.0-1.0>,
  "fast_ratio": <float 0.0-1.0>,
  "tank_ratio": <float 0.0-1.0>,
  "message": "<4-6 word military/sci-fi sector alert>"
}}

Ratios must sum to exactly 1.0."""

                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,   # lower = more consistent adherence to rules
                    max_tokens=200,
                )

                raw = response.choices[0].message.content.strip()

                # Strip markdown fences if model ignores instructions
                if "```" in raw:
                    parts = raw.split("```")
                    # Find the JSON block
                    for part in parts:
                        part = part.strip()
                        if part.startswith("{") or part.startswith("json\n{"):
                            raw = part.replace("json\n", "").strip()
                            break

                data = json.loads(raw)

                # Validate and clamp — never trust the model blindly
                data["total_zombies"] = max(min_zombies, min(max_zombies, int(data.get("total_zombies", min_zombies))))

                ratios = ["normal_ratio", "fast_ratio", "tank_ratio"]
                for k in ratios:
                    data[k] = max(0.0, float(data.get(k, 0.0)))

                total_r = sum(data[k] for k in ratios)
                if total_r <= 0:
                    data["normal_ratio"] = 1.0
                    data["fast_ratio"]   = 0.0
                    data["tank_ratio"]   = 0.0
                else:
                    for k in ratios:
                        data[k] = round(data[k] / total_r, 3)

                # Fix floating point so they sum to exactly 1.0
                diff = round(1.0 - sum(data[k] for k in ratios), 3)
                data["normal_ratio"] = round(data["normal_ratio"] + diff, 3)

                print(f"[AI] Wave {next_wave} composition: {data}")

                self._ai_override      = data
                self._ai_message       = data.get("message", "").upper()
                self._ai_message_timer = 5.0

            except Exception as e:
                print(f"[AI] ERROR (wave {next_wave}): {e}")
                self._ai_override = None
            finally:
                self._ai_pending = False

        threading.Thread(target=_call, daemon=True).start()

    def _composition_from_dict(self, data: dict) -> list[str]:
        """Convert validated AI dict into a spawn queue."""
        total = int(data.get("total_zombies", 10))
        n_rat = float(data.get("normal_ratio", 0.6))
        f_rat = float(data.get("fast_ratio",   0.3))
        t_rat = float(data.get("tank_ratio",   0.1))

        composition  = ["normal"] * int(total * n_rat)
        composition += ["fast"]   * int(total * f_rat)
        composition += ["tank"]   * int(total * t_rat)

        while len(composition) < total:
            composition.append("normal")

        # Boss is set deterministically in _start_wave, not by AI
        if data.get("boss", False):
            composition.append("boss")

        random.shuffle(composition)
        return composition

    def _create_zombie(self, ztype: str, player) -> "Zombie":
        x, y = self._random_spawn(player.x, player.y)
        z = Zombie(x, y, ztype)
        z.speed = z.speed * (1.08 ** (self.wave_number - 1))
        return z

    def _random_spawn(self, px: float, py: float) -> tuple[float, float]:
        margin = settings.SPAWN_EDGE_MARGIN
        min_d  = settings.SPAWN_MIN_PLAYER_DIST

        for _ in range(20):
            edge = random.randint(0, 3)
            if edge == 0:
                x = random.uniform(margin, self.world_w - margin)
                y = random.uniform(margin, margin * 3)
            elif edge == 1:
                x = random.uniform(margin, self.world_w - margin)
                y = random.uniform(self.world_h - margin * 3, self.world_h - margin)
            elif edge == 2:
                x = random.uniform(margin, margin * 3)
                y = random.uniform(margin, self.world_h - margin)
            else:
                x = random.uniform(self.world_w - margin * 3, self.world_w - margin)
                y = random.uniform(margin, self.world_h - margin)

            if math.hypot(x - px, y - py) >= min_d:
                return (x, y)

        return (random.uniform(margin, self.world_w - margin), margin)

    # ── HUD properties ───────────────────────────────────────────────────────

    @property
    def in_cooldown(self) -> bool:
        return self.state == "cooldown"

    @property
    def is_boss_wave(self) -> bool:
        return self.wave_number % settings.WAVE_BOSS_EVERY == 0 and self.wave_number > 0

    @property
    def ai_message(self) -> str:
        return self._ai_message if self._ai_message_timer > 0 else ""

    @property
    def last_wave_stats(self) -> dict | None:
        """Returns the most recent completed wave record, or None if no wave done yet."""
        return self._wave_history[-1] if self._wave_history else None