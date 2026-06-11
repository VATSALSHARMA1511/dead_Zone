"""
entities/zombie.py — Zombie entity with type system and simple chase AI.
"""

import math
import random
import pygame
import settings
from helpers import clamp, lerp
import sprite_store


_ZOMBIE_COLOR_MAP = {
    "normal": settings.C_ZOMBIE,
    "fast":   settings.C_ZOMBIE_FAST,
    "tank":   settings.C_ZOMBIE_TANK,
    "boss":   (220, 30, 80),
}


class Zombie:
    def __init__(self, x: float, y: float, ztype: str = "normal") -> None:
        self.x     = x
        self.y     = y
        self.ztype = ztype

        cfg             = settings.ZOMBIE_TYPES[ztype]
        self.speed      = cfg["speed"]
        self.health     = cfg["health"]
        self.max_health = cfg["health"]
        self.damage     = cfg["damage"]
        self.radius     = cfg["radius"]
        self.score_value    = cfg["score_value"]
        self._attack_rate   = cfg["attack_rate"]
        self._attack_timer  = 0.0

        self.base_color = _ZOMBIE_COLOR_MAP.get(ztype, settings.C_ZOMBIE)
        self.color      = self.base_color

        self.alive      = True
        self._hit_flash = 0.0
        self._wobble_t  = random.uniform(0, math.tau)
        self._vel_x     = 0.0
        self._vel_y     = 0.0

    def update(self, dt: float, player) -> None:
        if not self.alive:
            return

        self._wobble_t    += dt * 6.0
        self._hit_flash    = max(0.0, self._hit_flash - dt)
        self._attack_timer = max(0.0, self._attack_timer - dt)

        prediction_strength = 0.28
        target_x = player.x + player.vel_x * prediction_strength
        target_y = player.y + player.vel_y * prediction_strength
        dx   = target_x - self.x
        dy   = target_y - self.y
        dist = math.hypot(dx, dy)
        if dist > 0:
            nx, ny = dx / dist, dy / dist
            target_vx = nx * self.speed
            target_vy = ny * self.speed
            accel = 4.5
            self._vel_x = lerp(
                self._vel_x,
                target_vx,
                clamp(accel * dt, 0, 1)
                )
            self._vel_y = lerp(
                self._vel_y,
                target_vy,
                clamp(accel * dt, 0, 1)
                )
            if dist > player.radius + self.radius:
                self.x += self._vel_x * dt
                self.y += self._vel_y * dt

        self.color = self._compute_color()

    def _compute_color(self) -> tuple:
        if self._hit_flash > 0:
            ratio = self._hit_flash / 0.2
            r = int(lerp(self.base_color[0], settings.C_ZOMBIE_HIT[0], ratio))
            g = int(lerp(self.base_color[1], settings.C_ZOMBIE_HIT[1], ratio))
            b = int(lerp(self.base_color[2], settings.C_ZOMBIE_HIT[2], ratio))
            return (clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))
        return self.base_color

    def take_damage(self, amount: int) -> None:
        self.health    -= amount
        self._hit_flash = 0.2
        if self.health <= 0:
            self.health = 0
            self.alive  = False

    def can_attack(self) -> bool:
        return self._attack_timer <= 0

    def get_damage(self) -> int:
        if self._attack_timer <= 0:
            self._attack_timer = self._attack_rate
            return self.damage
        return 0

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, cam) -> None:
        if not self.alive:
            return
        sx, sy = cam.world_to_screen(self.x, self.y)
        r      = self.radius

        if not (-r < sx < surface.get_width() + r and
                -r < sy < surface.get_height() + r):
            return

        wobble = math.sin(self._wobble_t) * 1.5
        draw_r = max(4, int(r + wobble))

        # Shadow
        pygame.draw.ellipse(surface, (0, 0, 0),
                            (sx - draw_r + 3, sy + draw_r - 4,
                             draw_r * 2 - 3, draw_r // 2))

        if sprite_store.zombie_sprite is not None:
            # ── CUSTOM SPRITE PATH ────────────────────────────────────────
            diameter = draw_r * 2
            scaled   = pygame.transform.smoothscale(
                sprite_store.zombie_sprite, (diameter, diameter))

            # Hit flash: red tint overlay
            if self._hit_flash > 0:
                tint = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
                ratio = self._hit_flash / 0.2
                tint.fill((255, 50, 50, int(180 * ratio)))
                scaled.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(scaled, (sx - draw_r, sy - draw_r))

            # Boss crown still drawn on top of sprite
            if self.ztype == "boss":
                self._draw_boss_crown(surface, sx, sy, draw_r)

            # Type ring so player can tell zombie types apart even with custom face
            ring_colors = {
                "normal": settings.C_ZOMBIE,
                "fast":   settings.C_ZOMBIE_FAST,
                "tank":   settings.C_ZOMBIE_TANK,
                "boss":   (220, 30, 80),
            }
            ring_col = ring_colors.get(self.ztype, settings.C_ZOMBIE)
            pygame.draw.circle(surface, ring_col, (sx, sy), draw_r, 2)

        else:
            # ── DEFAULT CIRCLE PATH (original code) ───────────────────────
            pygame.draw.circle(surface, self.color, (sx, sy), draw_r)

            outline_w = 3 if self.ztype in ("boss", "tank") else 1
            outline_c = (20, 20, 20) if self.ztype == "boss" else (0, 0, 0)
            pygame.draw.circle(surface, outline_c, (sx, sy), draw_r, outline_w)

            if self.ztype == "boss":
                self._draw_boss_crown(surface, sx, sy, draw_r)

            # X eyes
            eye_r  = max(2, draw_r // 5)
            offset = draw_r // 3
            for ex_off in (-offset, offset):
                ex = sx + ex_off
                ey = sy - offset // 2
                pygame.draw.line(surface, (20, 20, 20),
                                 (ex - eye_r, ey - eye_r), (ex + eye_r, ey + eye_r), 2)
                pygame.draw.line(surface, (20, 20, 20),
                                 (ex + eye_r, ey - eye_r), (ex - eye_r, ey + eye_r), 2)

        # Health bar (always shown when damaged, regardless of sprite mode)
        if self.health < self.max_health:
            bar_w = draw_r * 2
            bar_h = 4
            bx    = sx - draw_r
            by    = sy - draw_r - 8
            pygame.draw.rect(surface, settings.C_HEALTH_BAR_BG, (bx, by, bar_w, bar_h))
            fill_w = int(bar_w * self.health / self.max_health)
            pygame.draw.rect(surface, settings.C_HEALTH_GOOD, (bx, by, fill_w, bar_h))

    def _draw_boss_crown(self, surface, sx, sy, r):
        n     = 6
        outer = r + 10
        inner = r + 2
        for i in range(n):
            angle = math.tau / n * i - math.pi / 2
            tip_x = int(sx + math.cos(angle) * outer)
            tip_y = int(sy + math.sin(angle) * outer)
            la    = angle - 0.25
            ra    = angle + 0.25
            lx    = int(sx + math.cos(la) * inner)
            ly    = int(sy + math.sin(la) * inner)
            rx    = int(sx + math.cos(ra) * inner)
            ry    = int(sy + math.sin(ra) * inner)
            pygame.draw.polygon(surface, settings.C_ACCENT_GOLD,
                                [(tip_x, tip_y), (lx, ly), (rx, ry)])
