"""
entities/player.py — Player entity.
"""

import math
import random
import pygame
import settings

from helpers import clamp, vec_normalise
from constants import WEAPON_ORDER
from bullet import Bullet
import sprite_store


class Player:
    def __init__(self, x: float, y: float) -> None:
        self.x      = x
        self.y      = y
        self.radius = settings.PLAYER_RADIUS

        self.health     = settings.PLAYER_HEALTH_MAX
        self.max_health = settings.PLAYER_HEALTH_MAX
        self.alive      = True
        self._iframe_t  = 0.0

        self.stamina     = settings.PLAYER_STAMINA_MAX
        self.max_stamina = settings.PLAYER_STAMINA_MAX
        self._sprinting  = False

        self._dash_t     = 0.0
        self._dash_cd    = 0.0
        self._dash_vx    = 0.0
        self._dash_vy    = 0.0

        self._weapon_slot   = 0
        self._weapons       = {name: _WeaponState(name) for name in WEAPON_ORDER}
        self._shoot_timer   = 0.0
        self._reloading     = False
        self._reload_timer  = 0.0

        self.facing = 0.0

        self._hit_flash_t = 0.0
        self._bob_t       = 0.0
        self.vel_x = 0.0
        self.vel_y = 0.0

    @property
    def current_weapon_name(self) -> str:
        return WEAPON_ORDER[self._weapon_slot]

    @property
    def current_weapon(self) -> dict:
        return settings.WEAPONS[self.current_weapon_name]

    @property
    def ammo(self) -> int:
        return self._weapons[self.current_weapon_name].ammo

    @property
    def ammo_max(self) -> int:
        return self.current_weapon["ammo_max"]

    @property
    def is_reloading(self) -> bool:
        return self._reloading

    @property
    def reload_progress(self) -> float:
        rt = self.current_weapon["reload_time"]
        return clamp(1.0 - self._reload_timer / rt, 0.0, 1.0) if self._reloading else 1.0

    @property
    def dash_cooldown_ratio(self) -> float:
        return clamp(1.0 - self._dash_cd / settings.PLAYER_DASH_COOLDOWN, 0.0, 1.0)

    @property
    def is_dashing(self) -> bool:
        return self._dash_t > 0

    def update(self, dt, keys, mouse_world, fire_pressed,
               reload_pressed, dash_pressed, sprint_held):
        if not self.alive:
            return []

        self._bob_t += dt
        self._iframe_t    = max(0.0, self._iframe_t - dt)
        self._hit_flash_t = max(0.0, self._hit_flash_t - dt)
        self._shoot_timer = max(0.0, self._shoot_timer - dt)
        self._dash_cd     = max(0.0, self._dash_cd - dt)

        dx = mouse_world[0] - self.x
        dy = mouse_world[1] - self.y
        self.facing = math.degrees(math.atan2(dy, dx))

        self._move(dt, keys, sprint_held)

        if dash_pressed and self._dash_cd <= 0 and not self.is_dashing:
            self._start_dash(keys)
        if self.is_dashing:
            self._update_dash(dt)

        self._update_reload(dt, reload_pressed)

        bullets = []
        if fire_pressed and not self._reloading:
            bullets = self._try_shoot()

        return bullets

    def _move(self, dt, keys, sprint_held):
        if self.is_dashing:
            return
        move_x, move_y = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_x += 1
        if move_x != 0 or move_y != 0:
            nx, ny = vec_normalise((move_x, move_y))
            if sprint_held and self.stamina > 0:
                speed = settings.PLAYER_SPRINT_SPEED
                self.stamina -= settings.PLAYER_SPRINT_COST * dt
                self.stamina = max(0.0, self.stamina)
                self._sprinting = True
            else:
                speed = settings.PLAYER_SPEED
                hp_ratio = self.health / self.max_health
                
                if hp_ratio < 0.25:
                    speed *= 0.5
                elif hp_ratio < 0.5:
                    speed *= 0.7
                self._sprinting = False
            self.vel_x = nx * speed
            self.vel_y = ny * speed
            self.x += self.vel_x * dt
            self.y += self.vel_y * dt
        else:
            self._sprinting = False
            self.vel_x = 0.0
            self.vel_y = 0.0
        if not self._sprinting:
            self.stamina = min(
                self.max_stamina,
                self.stamina + settings.PLAYER_STAMINA_REGEN * dt
                )

    def _start_dash(self, keys):
        dx, dy = 0.0, 0.0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1
        if dx == 0 and dy == 0:
            rad = math.radians(self.facing)
            dx, dy = math.cos(rad), math.sin(rad)
        nx, ny = vec_normalise((dx, dy))
        self._dash_vx  = nx * settings.PLAYER_DASH_SPEED
        self._dash_vy  = ny * settings.PLAYER_DASH_SPEED
        self._dash_t   = settings.PLAYER_DASH_DUR
        self._dash_cd  = settings.PLAYER_DASH_COOLDOWN
        self._iframe_t = max(self._iframe_t, settings.PLAYER_DASH_DUR)

    def _update_dash(self, dt):
        step = min(dt, self._dash_t)
        self.vel_x = self._dash_vx
        self.vel_y = self._dash_vy
        self.x += self.vel_x * step
        self.y += self.vel_y * step
        self._dash_t -= dt

    def _try_shoot(self):
        if self._shoot_timer > 0:
            return []
        ws   = self._weapons[self.current_weapon_name]
        wdef = self.current_weapon
        if ws.ammo <= 0:
            self._start_reload()
            return []
        hp_ratio = self.health / self.max_health
        if hp_ratio < 0.25:
             ws.ammo -= 3    # burns through ammo fast when critical
        elif hp_ratio < 0.5:
             ws.ammo -= 2    # burns faster when hurt
        else:
             ws.ammo -= 1    # normal
        ws.ammo = max(0, ws.ammo)
        self._shoot_timer = wdef["fire_rate"]
        bullets = []
        for _ in range(wdef["bullets_per_shot"]):
            spread = random.uniform(-wdef["spread"], wdef["spread"])
            angle  = self.facing + spread
            bullets.append(Bullet(self.x, self.y, angle,
                                  wdef["bullet_speed"], wdef["damage"]))
        return bullets

    def _start_reload(self):
        ws = self._weapons[self.current_weapon_name]
        if ws.ammo < self.ammo_max and not self._reloading:
            self._reloading    = True
            self._reload_timer = self.current_weapon["reload_time"]

    def _update_reload(self, dt, reload_pressed):
        if reload_pressed and not self._reloading:
            self._start_reload()
        if self._reloading:
            self._reload_timer -= dt
            if self._reload_timer <= 0:
                ws      = self._weapons[self.current_weapon_name]
                ws.ammo = self.ammo_max
                self._reloading = False

    def switch_weapon(self, slot):
        slot = clamp(slot, 0, len(WEAPON_ORDER) - 1)
        if slot != self._weapon_slot:
            self._weapon_slot = slot
            self._reloading   = False
            self._shoot_timer = 0.0

    def scroll_weapon(self, direction):
        new_slot = (self._weapon_slot + direction) % len(WEAPON_ORDER)
        self.switch_weapon(new_slot)

    def take_damage(self, amount):
        if self._iframe_t > 0 or self.is_dashing:
            return False
        self.health    -= amount
        self._iframe_t  = settings.PLAYER_IFRAMES
        self._hit_flash_t = 0.3
        if self.health <= 0:
            self.health = 0
            self.alive  = False
        return True

    def heal(self, amount):
        self.health = min(self.max_health, self.health + amount)

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface, cam) -> None:
        sx, sy = cam.world_to_screen(self.x, self.y)
        r      = self.radius

        # Invincibility flicker
        if self._iframe_t > 0:
            if int(self._iframe_t / 0.06) % 2 == 1:
                return

        bob = math.sin(self._bob_t * 8) * 1.5 if self._sprinting else 0

        # ── Dash trail (drawn before body so it's behind) ─────────────────
        if self.is_dashing:
            for i in range(3):
                alpha   = 80 - i * 25
                tr      = r - i * 3
                trail_x = int(sx - self._dash_vx * 0.015 * (i + 1))
                trail_y = int(sy - self._dash_vy * 0.015 * (i + 1) + bob)
                trail_surf = pygame.Surface((tr * 2 + 2, tr * 2 + 2), pygame.SRCALPHA)
                pygame.draw.circle(trail_surf, (*settings.C_PLAYER_ACCENT, alpha),
                                   (tr + 1, tr + 1), tr)
                surface.blit(trail_surf, (trail_x - tr - 1, trail_y - tr - 1))

        # ── Shadow ────────────────────────────────────────────────────────
        shadow_surf = pygame.Surface((r * 2, r), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow_surf, (0, 0, 0, 60), (0, 0, r * 2, r))
        surface.blit(shadow_surf, (sx - r + 4, sy - r // 2 + 4 + int(bob)))

        # ── Body ──────────────────────────────────────────────────────────
        if sprite_store.player_sprite is not None:
            # ── CUSTOM SPRITE PATH ────────────────────────────────────────
            diameter = r * 2
            # Scale sprite to current radius
            scaled = pygame.transform.smoothscale(
                sprite_store.player_sprite, (diameter, diameter))
            # Rotate to face mouse (pygame rotates CCW, our angle is CW)
            rotated = pygame.transform.rotate(scaled, -self.facing)
            rw, rh  = rotated.get_size()

            # Hit flash: tint red by blending a red overlay
            if self._hit_flash_t > 0:
                tint = pygame.Surface((rw, rh), pygame.SRCALPHA)
                tint.fill((255, 50, 50, 120))
                rotated.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

            surface.blit(rotated,
                         (sx - rw // 2, sy - rh // 2 + int(bob)))
            
            

            # Gun barrel still drawn on top so direction is always clear
            rad      = math.radians(self.facing)
            barrel_l = r + 10
            ex       = int(sx + math.cos(rad) * barrel_l)
            ey       = int(sy + math.sin(rad) * barrel_l + bob)
            pygame.draw.line(surface, settings.C_ACCENT_GOLD,
                             (sx, sy + int(bob)), (ex, ey), 3)

        else:
            # ── DEFAULT CIRCLE PATH (original code) ───────────────────────
            body_color = settings.C_ACCENT_RED if self._hit_flash_t > 0 else settings.C_PLAYER
            pygame.draw.circle(surface, body_color, (sx, sy + int(bob)), r)
            pygame.draw.circle(surface, settings.C_PLAYER_ACCENT,
                               (sx, sy + int(bob)), r - 4, 2)

            rad      = math.radians(self.facing)
            barrel_l = r + 10
            ex       = int(sx + math.cos(rad) * barrel_l)
            ey       = int(sy + math.sin(rad) * barrel_l + bob)
            pygame.draw.line(surface, settings.C_ACCENT_GOLD,
                             (sx, sy + int(bob)), (ex, ey), 3)

            eye_x = int(sx + math.cos(rad) * (r - 4))
            eye_y = int(sy + math.sin(rad) * (r - 4) + bob)
            pygame.draw.circle(surface, settings.C_BLACK, (eye_x, eye_y), 3)


class _WeaponState:
    __slots__ = ("name", "ammo")

    def __init__(self, name: str) -> None:
        self.name = name
        self.ammo = settings.WEAPONS[name]["ammo_max"]
