"""
game.py — Core game orchestrator.
"""

import pygame
import settings
import threading
import urllib.request
import json
import random
from constants import GameState

from player import Player
from zombie import Zombie
from bullet import Bullet

from camera import Camera
from particles import ParticleSystem
from collision import CollisionSystem
from waves import WaveManager
from obstacle import Obstacle

from hud import HUD
from menus import MainMenu, PauseMenu, GameOverScreen, SpritePickerScreen


class Game:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen   = screen
        self._bullets_fired = 0
        self._bullets_hit   = 0
        self.sw       = settings.SCREEN_W
        self.sh       = settings.SCREEN_H
        self.ww       = settings.WORLD_W
        self.wh       = settings.WORLD_H

        # ── Systems ─────────────────────────────────────────────────────────
        self.camera    = Camera(self.sw, self.sh, self.ww, self.wh)
        self.particles = ParticleSystem()
        self.collision = CollisionSystem(self.ww, self.wh)

        # ── UI ──────────────────────────────────────────────────────────────
        self.hud           = HUD(self.sw, self.sh)
        self.main_menu     = MainMenu(self.sw, self.sh)
        self.pause_menu    = PauseMenu(self.sw, self.sh)
        self.gameover      = GameOverScreen(self.sw, self.sh)
        self.sprite_picker = SpritePickerScreen(self.sw, self.sh)

        # ── State ───────────────────────────────────────────────────────────
        self.state       = GameState.MAIN_MENU
        self._best_score = 0

        # ── Gameplay data ────────────────────────────────────────────────────
        self.player      : Player | None = None
        self.zombies     : list[Zombie]  = []
        self.bullets     : list[Bullet]  = []
        self.obstacles   : list[Obstacle] = []
        self.waves       : WaveManager | None = None
        self.score       = 0
        self.kills       = 0
        self._score_tick = 0.0
        self._streak     = 0
        self._streak_timer = 0.0

        # ── World surface (pre-rendered background) ──────────────────────────
        self._world_surf = self._build_world_surface()

        # ── Audio ────────────────────────────────────────────────────────────
        self._sfx = {}
        self._load_audio()

        # ── Cursor ───────────────────────────────────────────────────────────
        pygame.mouse.set_visible(False)

    # ── Audio setup ──────────────────────────────────────────────────────────

    def _load_audio(self) -> None:
        import os
        sound_map = {
            "shoot_pistol":  "assets/sounds/shoot_pistol.wav",
            "shoot_shotgun": "assets/sounds/shoot_shotgun.wav",
            "shoot_smg":     "assets/sounds/shoot_smg.wav",
            "zombie_hit":    "assets/sounds/zombie_hit.wav",
            "zombie_die":    "assets/sounds/zombie_die.wav",
            "player_hit":    "assets/sounds/player_hit.wav",
            "reload":        "assets/sounds/reload.wav",
            "dash":          "assets/sounds/dash.wav",
        }
        if pygame.mixer.get_init():
            for key, path in sound_map.items():
                if os.path.exists(path):
                    try:
                        sfx = pygame.mixer.Sound(path)
                        sfx.set_volume(settings.SFX_VOLUME)
                        self._sfx[key] = sfx
                    except Exception:
                        pass
            music_path = "assets/music/ambient.ogg"
            if os.path.exists(music_path):
                try:
                    pygame.mixer.music.load(music_path)
                    pygame.mixer.music.set_volume(settings.MUSIC_VOLUME)
                    pygame.mixer.music.play(-1)
                except Exception:
                    pass

    def _play_sfx(self, name: str) -> None:
        sfx = self._sfx.get(name)
        if sfx:
            sfx.play()

    # ── World surface ────────────────────────────────────────────────────────

    def _build_world_surface(self) -> pygame.Surface:
        surf = pygame.Surface((self.ww, self.wh))
        sector_w = self.ww // settings.SECTOR_COLS
        sector_h = self.wh // settings.SECTOR_ROWS
        sector_layout = []
        for row in range(settings.SECTOR_ROWS):
            layout_row = []
            for col in range(settings.SECTOR_COLS):
                sector_type = random.choice(settings.SECTOR_TYPES)
                layout_row.append(sector_type)
            sector_layout.append(layout_row)
        for row in range(settings.SECTOR_ROWS):
            for col in range(settings.SECTOR_COLS):
                sx = col * sector_w
                sy = row * sector_h
                sector_type = sector_layout[row][col]
                palette = settings.SECTOR_COLORS[sector_type]
                base_col   = palette["base"]
                accent_col = palette["accent"]
                grid_col   = palette["grid"]
                pygame.draw.rect(
                    surf,
                    base_col,
                    (sx, sy, sector_w, sector_h)
                )
                ts = settings.TILE_SIZE
                for x in range(sx, sx + sector_w, ts):
                    pygame.draw.line(
                        surf,
                        grid_col,
                        (x, sy),
                        (x, sy + sector_h)
                    )
                for y in range(sy, sy + sector_h, ts):
                    pygame.draw.line(
                        surf,
                        grid_col,
                        (sx, y),
                        (sx + sector_w, y)
                    )
                pygame.draw.rect(
                    surf,
                    accent_col,
                    (sx, sy, sector_w, sector_h),
                    4
                )
                for _ in range(8):
                    dx = random.randint(sx + 60, sx + sector_w - 60)
                    dy = random.randint(sy + 60, sy + sector_h - 60)
                    decal_type = random.choice([
                        "stripe",
                        "vent",
                        "marker",
                        "corner"
                    ])
                    if decal_type == "stripe":
                        w = random.randint(60, 140)
                        h = 18
                        pygame.draw.rect(
                            surf,
                            accent_col,
                            (dx, dy, w, h),
                            2
                        )
                        for i in range(0, w, 14):
                            pygame.draw.line(
                                surf,
                                accent_col,
                                (dx + i, dy),
                                (dx + i + 10, dy + h),
                                2
                            )
                    elif decal_type == "vent":
                        size = random.randint(30, 50)
                        pygame.draw.rect(
                            surf,grid_col,
                            (dx, dy, size, size),
                            border_radius=4
                        )
                        for gy in range(dy + 6, dy + size - 4, 6):
                            pygame.draw.line(
                                surf,
                                accent_col,
                                (dx + 4, gy),
                                (dx + size - 4, gy),
                                1
                            )
                    elif decal_type == "marker":
                        radius = random.randint(16, 34)
                        pygame.draw.circle(
                            surf,
                            accent_col,
                            (dx, dy),
                            radius,
                            2
                        )
                        pygame.draw.line(
                            surf,
                            accent_col,
                            (dx - radius, dy),
                            (dx + radius, dy),
                            1
                        )
                        pygame.draw.line(
                            surf,
                            accent_col,
                            (dx, dy - radius),
                            (dx, dy + radius),
                            1
                        )
                    elif decal_type == "corner":
                        size = random.randint(30, 60)
                        pygame.draw.line(
                            surf,
                            accent_col,
                            (dx, dy),
                            (dx + size, dy),
                            3
                        )
                        pygame.draw.line(
                            surf,
                            accent_col,
                            (dx, dy),
                            (dx, dy + size),
                            3
                        )
                font = pygame.font.SysFont("consolas", 28, bold=True)
                label = font.render(
                    sector_type.upper(),
                    True,
                    accent_col
                )
                surf.blit(label, (sx + 20, sy + 20))
        pygame.draw.rect(
            surf,
            (40, 55, 80),
            (0, 0, self.ww, self.wh),
            6
        )
        return surf

    # ── Game setup ───────────────────────────────────────────────────────────
    def _generate_obstacles(self):
        self.obstacles = []
        obstacle_data = [
            (1400, 1000, 180, 180),
            (1650, 1000, 180, 180),
            (700, 700, 140, 260),
            (500, 1500, 220, 120),
            (2400, 600, 200, 140),
            (2500, 1700, 160, 260),
            (1200, 300, 300, 120),
            (1500, 2000, 320, 120),
        ]
        for x, y, w, h in obstacle_data:
            self.obstacles.append(Obstacle(x, y, w, h))
    def _start_new_game(self) -> None:
        self._bullets_fired = 0
        self._bullets_hit   = 0
        cx, cy           = self.ww // 2, self.wh // 2
        self.player      = Player(cx, cy)
        self.zombies     = []
        self.bullets     = []
        self.waves       = WaveManager(self.ww, self.wh)
        self.score       = 0
        self.kills       = 0
        self._score_tick = 0.0
        self._streak     = 0
        self._streak_timer = 0.0
        self.particles   = ParticleSystem()
        self.camera.x    = cx - self.sw / 2
        self.camera.y    = cy - self.sh / 2
        self._generate_obstacles()

    # ── Score POST ───────────────────────────────────────────────────────────

    def _post_score(self, name, score, wave, kills):
        def _send():
            try:
                data = json.dumps({"name": name, "score": score,
                                   "wave": wave, "kills": kills}).encode()
                req  = urllib.request.Request(
                    "https://deadzone-production-759b.up.railway.app/score",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req, timeout=2)
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()

    # ── State machine ────────────────────────────────────────────────────────

    # ── State machine ────────────────────────────────────────────────────────

    def change_state(self, new_state: GameState) -> None:
        if new_state == GameState.PLAYING and self.state != GameState.PAUSED:
            self._start_new_game()
        if new_state == GameState.GAME_OVER:
            self._best_score = max(self._best_score, self.score)
            bullets_fired = getattr(self, '_bullets_fired', 0)
            bullets_hit   = getattr(self, '_bullets_hit', 0)
            accuracy      = (bullets_hit / max(1, bullets_fired)) * 100
            time_alive    = int(self.waves.stat_time_alive)
            self.gameover.set_results(
                self.score, self.waves.wave_number, self.kills, self._best_score,
                accuracy, time_alive, bullets_fired)
            self._post_score("PLAYER", self.score, self.waves.wave_number, self.kills)
        self.state = new_state

    # ── Main update ──────────────────────────────────────────────────────────

    def update(self, dt: float, events: list) -> None:
        if self.state == GameState.MAIN_MENU:
            self._update_main_menu(dt, events)
        elif self.state == GameState.SPRITE_SELECT:
            self._update_sprite_select(dt, events)
        elif self.state == GameState.PLAYING:
            self._update_playing(dt, events)
        elif self.state == GameState.PAUSED:
            self._update_paused(dt, events)
        elif self.state == GameState.GAME_OVER:
            self._update_game_over(dt, events)

    def _update_main_menu(self, dt: float, events: list) -> None:
        self.main_menu.update(dt)
        for event in events:
            action = self.main_menu.handle_event(event)
            if action == "start":
                self.state = GameState.SPRITE_SELECT
            elif action == "quit":
                pygame.quit()
                raise SystemExit

    def _update_sprite_select(self, dt: float, events: list) -> None:
        self.sprite_picker.update(dt)
        for event in events:
            action = self.sprite_picker.handle_event(event)
            if action == "play":
                self.change_state(GameState.PLAYING)
            elif action == "back":
                self.state = GameState.MAIN_MENU

    def _update_paused(self, dt: float, events: list) -> None:
        self.pause_menu.update(dt)
        for event in events:
            action = self.pause_menu.handle_event(event)
            if action == "resume":
                self.state = GameState.PLAYING
            elif action == "main_menu":
                self.state = GameState.MAIN_MENU
            elif action == "quit":
                pygame.quit()
                raise SystemExit

    def _update_game_over(self, dt: float, events: list) -> None:
        self.gameover.update(dt)
        for event in events:
            action = self.gameover.handle_event(event)
            if action == "restart":
                self.change_state(GameState.PLAYING)
            elif action == "main_menu":
                self.state = GameState.MAIN_MENU
            elif action == "quit":
                pygame.quit()
                raise SystemExit

    def _update_playing(self, dt: float, events: list) -> None:

        keys           = pygame.key.get_pressed()
        fire_pressed   = pygame.mouse.get_pressed()[0]
        mouse_screen   = pygame.mouse.get_pos()
        mouse_world    = self.camera.screen_to_world(*mouse_screen)
        sprint_held    = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        dash_pressed   = False
        reload_pressed = False

        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.state = GameState.PAUSED
                    return
                if event.key == pygame.K_r:
                    reload_pressed = True
                if event.key == pygame.K_SPACE:
                    dash_pressed = True
                if event.key == pygame.K_1:
                    self.player.switch_weapon(0)
                if event.key == pygame.K_2:
                    self.player.switch_weapon(1)
                if event.key == pygame.K_3:
                    self.player.switch_weapon(2)
            if event.type == pygame.MOUSEWHEEL:
                self.player.scroll_weapon(event.y)

        prev_ammo   = self.player.ammo
        new_bullets = self.player.update(
            dt, keys, mouse_world, fire_pressed,
            reload_pressed, dash_pressed, sprint_held
        )

        if new_bullets:
            self._play_sfx(f"shoot_{self.player.current_weapon_name}")
            self.particles.spawn_muzzle_flash(
                self.player.x, self.player.y, self.player.facing)
            self.camera.add_shake(2.0)

        if prev_ammo > 0 and self.player.ammo == self.player.ammo_max:
            self._play_sfx("reload")

        self.bullets.extend(new_bullets)
        self._bullets_fired += len(new_bullets)

        for zombie in self.zombies:
            if zombie.alive:
                zombie.update(dt, self.player)

        for bullet in self.bullets:
            bullet.update(dt)

        self.collision.process(
            self.player,
            self.bullets,
            self.zombies,
            self.obstacles,
            self.particles,
            self.camera
        )

        # ── Dead entity cleanup + scoring ─────────────────────────────────
        for zombie in self.zombies:
            if not zombie.alive and zombie.score_value > 0:
                self._streak += 1
                self._streak_timer = 3.0
                multiplier   = max(1, self._streak // 5)
                self.score  += zombie.score_value * multiplier
                self.kills  += 1
                self.waves.stat_kills_this_wave += 1
                self.particles.spawn_zombie_death(
                    zombie.x, zombie.y, zombie.base_color)
                self._play_sfx("zombie_die")
                zombie.score_value = 0

        self.zombies = [z for z in self.zombies if z.alive]
        self.bullets = [b for b in self.bullets if b.alive]

        # ── Streak decay ──────────────────────────────────────────────────
        if self._streak_timer > 0:
            self._streak_timer -= dt
        else:
            self._streak = 0

        # ── Survival score ────────────────────────────────────────────────
        self._score_tick += dt
        if self._score_tick >= 1.0:
            self.score += self.waves.wave_number
            self._score_tick -= 1.0

        # ── Wave cleared banner ───────────────────────────────────────────
        self.waves.update(dt, self.zombies, self.player)
        if self.waves.in_cooldown and self.waves.cooldown_remaining > settings.WAVE_COOLDOWN - 0.1:
            self.hud.show_wave_clear()

        self.camera.update(self.player.x, self.player.y, dt)
        self.particles.update(dt)
        self.hud.update(dt)

        if not self.player.alive:
            self.change_state(GameState.GAME_OVER)

    # ── Main draw ────────────────────────────────────────────────────────────

    def draw(self, fps: int) -> None:
        if self.state == GameState.MAIN_MENU:
            self.main_menu.draw(self.screen)
            return

        if self.state == GameState.SPRITE_SELECT:
            self.sprite_picker.draw(self.screen)
            return

        if self.state == GameState.GAME_OVER:
            self._draw_world(fps)
            self.gameover.draw(self.screen)
            return

        self._draw_world(fps)

        if self.state == GameState.PAUSED:
            self.pause_menu.draw(self.screen)

    def _draw_world(self, fps) -> None:
        cam_x, cam_y = int(self.camera.x), int(self.camera.y)
        self.screen.blit(self._world_surf, (0, 0),
                         area=pygame.Rect(cam_x, cam_y, self.sw, self.sh))
        for obstacle in self.obstacles:
            obstacle.draw(self.screen, self.camera)
        for bullet in self.bullets:
            bullet.draw(self.screen, self.camera)
        for zombie in self.zombies:
            if self.camera.is_visible(zombie.x, zombie.y, margin=60):
                zombie.draw(self.screen, self.camera)
        if self.player and self.player.alive:
            self.player.draw(self.screen, self.camera)
        self.particles.draw(self.screen, self.camera)
        if self.state == GameState.PLAYING and self.player:
            if self.waves.ai_message:
                font = pygame.font.SysFont("consolas,monospace", 20, bold=True)
                msg  = font.render(f"⚡ AI DIRECTOR: {self.waves.ai_message}", True, (255, 50, 50))
                self.screen.blit(msg, (self.sw // 2 - msg.get_width() // 2, 120))
            self.hud.draw(self.screen, self.player, self.waves,
                        self.score, fps, self.particles.count,
                        self._streak)