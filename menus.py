"""
menus.py — Main menu, pause screen, game-over screen, and sprite picker.
"""

import math
import os
import pygame
import settings
from helpers import clamp
import sprite_store
import player_name_store


class _Button:
    def __init__(self, x, y, w, h, text, font, action,
                 color_normal=(30, 40, 60), color_hover=(50, 70, 110),
                 text_color=None):
        self.rect   = pygame.Rect(x - w // 2, y - h // 2, w, h)
        self.text   = text
        self.font   = font
        self.action = action
        self.c_norm = color_normal
        self.c_hov  = color_hover
        self.t_col  = text_color or settings.C_WHITE
        self._hover = False
        self._pulse = 0.0

    def update(self, dt, mouse_pos):
        self._hover = self.rect.collidepoint(mouse_pos)
        self._pulse = (self._pulse + dt * 3) % math.tau

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return self.action
        return None

    def draw(self, surface):
        color = self.c_hov if self._hover else self.c_norm
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        if self._hover:
            glow_alpha = int(60 + 30 * math.sin(self._pulse))
            glow_surf  = pygame.Surface((self.rect.w + 16, self.rect.h + 16), pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (*settings.C_PLAYER, glow_alpha),
                             (0, 0, self.rect.w + 16, self.rect.h + 16), border_radius=8)
            surface.blit(glow_surf, (self.rect.x - 8, self.rect.y - 8))
            pygame.draw.rect(surface, settings.C_PLAYER, self.rect, 2, border_radius=6)
        else:
            pygame.draw.rect(surface, settings.C_MID_GRAY, self.rect, 1, border_radius=6)
        text_surf = self.font.render(self.text, True,
                                     settings.C_PLAYER_ACCENT if self._hover else self.t_col)
        surface.blit(text_surf, (self.rect.centerx - text_surf.get_width() // 2,
                                  self.rect.centery - text_surf.get_height() // 2))


# ─── Sprite Picker Screen ─────────────────────────────────────────────────────

class SpritePickerScreen:
    """
    Shown after PLAY is clicked, before game starts.

    Layout — two panels side by side:
      LEFT:  player photo upload + circular preview
      RIGHT: zombie photo upload + circular preview

    Actions emitted:
      "play"  — user clicked START GAME (player photo is set)
      "back"  — user clicked BACK (return to main menu)
    """

    PREVIEW_SIZE = 90   # diameter of the circular preview

    def __init__(self, screen_w, screen_h):
        self.sw, self.sh = screen_w, screen_h
        pygame.font.init()

        self._font_title = pygame.font.SysFont("consolas,monospace", 36, bold=True)
        self._font_label = pygame.font.SysFont("consolas,monospace", 20, bold=True)
        self._font_hint  = pygame.font.SysFont("consolas,monospace", 15)
        self._font_btn   = pygame.font.SysFont("consolas,monospace", 22, bold=True)
        self._font_err   = pygame.font.SysFont("consolas,monospace", 14)

        cx = screen_w // 2
        cy = screen_h // 2

        # Panel centres
        self._left_cx  = cx - 220
        self._right_cx = cx + 220
        self._panel_y  = cy - 40

        # Upload buttons
        self._btn_player = _Button(self._left_cx,  self._panel_y + 100, 200, 44,
                                   "CHOOSE PHOTO", self._font_btn, "upload_player",
                                   color_normal=(20, 50, 40), color_hover=(30, 90, 70))
        self._btn_zombie = _Button(self._right_cx, self._panel_y + 100, 200, 44,
                                   "CHOOSE PHOTO", self._font_btn, "upload_zombie",
                                   color_normal=(50, 20, 20), color_hover=(90, 30, 30))
        self._btn_clear_player = _Button(self._left_cx,  self._panel_y + 155, 200, 32,
                                         "CLEAR", self._font_hint, "clear_player",
                                         color_normal=(25, 25, 35), color_hover=(40, 40, 60))
        self._btn_clear_zombie = _Button(self._right_cx, self._panel_y + 155, 200, 32,
                                         "CLEAR", self._font_hint, "clear_zombie",
                                         color_normal=(25, 25, 35), color_hover=(40, 40, 60))

        # Navigation buttons
        self._btn_start = _Button(cx, cy + 220, 260, 52,
                                  "START GAME", self._font_btn, "play",
                                  color_normal=(20, 60, 40), color_hover=(30, 110, 70),
                                  text_color=settings.C_PLAYER_ACCENT)
        self._btn_back  = _Button(cx, cy + 285, 200, 40,
                                  "BACK", self._font_btn, "back",
                                  color_normal=(30, 30, 40), color_hover=(50, 50, 70))

        self._t         = 0.0
        self._error_msg = ""
        self._error_t   = 0.0

        # Preview surfaces (scaled from sprite_store for display)
        self._player_preview = None
        self._zombie_preview  = None
        self._refresh_previews()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _refresh_previews(self):
        p = self.PREVIEW_SIZE
        if sprite_store.player_sprite:
            self._player_preview = pygame.transform.smoothscale(
                sprite_store.player_sprite, (p, p))
        else:
            self._player_preview = None

        if sprite_store.zombie_sprite:
            self._zombie_preview = pygame.transform.smoothscale(
                sprite_store.zombie_sprite, (p, p))
        else:
            self._zombie_preview  = None

    def _open_file_dialog(self) -> str | None:
        """
        Open a native Windows/Linux/Mac file picker via tkinter.
        Returns chosen path string, or None if cancelled.
        Runs in the same thread — pygame event loop pauses briefly (fine).
        """
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()          # hide the tk window
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Choose an image",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                    ("All files",   "*.*"),
                ]
            )
            root.destroy()
            return path if path else None
        except Exception as e:
            self._show_error(f"File dialog failed: {e}")
            return None

    def _show_error(self, msg: str):
        self._error_msg = msg
        self._error_t   = 3.0   # show for 3 seconds

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, dt):
        self._t += dt
        self._error_t = max(0.0, self._error_t - dt)
        mp = pygame.mouse.get_pos()
        for btn in [self._btn_player, self._btn_zombie,
                    self._btn_clear_player, self._btn_clear_zombie,
                    self._btn_start, self._btn_back]:
            btn.update(dt, mp)

    def handle_event(self, event) -> str | None:
        # Upload player
        if self._btn_player.handle_event(event) == "upload_player":
            path = self._open_file_dialog()
            if path:
                ok = sprite_store.set_player_image(path)
                if ok:
                    self._refresh_previews()
                else:
                    self._show_error("Couldn't load that image. Try a PNG or JPG.")
            return None

        # Upload zombie
        if self._btn_zombie.handle_event(event) == "upload_zombie":
            path = self._open_file_dialog()
            if path:
                ok = sprite_store.set_zombie_image(path)
                if ok:
                    self._refresh_previews()
                else:
                    self._show_error("Couldn't load that image. Try a PNG or JPG.")
            return None

        # Clear buttons
        if self._btn_clear_player.handle_event(event) == "clear_player":
            sprite_store.player_sprite = None
            self._refresh_previews()
            return None
        if self._btn_clear_zombie.handle_event(event) == "clear_zombie":
            sprite_store.zombie_sprite = None
            self._refresh_previews()
            return None

        # Start / back
        if self._btn_start.handle_event(event) == "play":
            return "play"
        if self._btn_back.handle_event(event) == "back":
            return "back"

        return None

    def draw(self, surface):
        surface.fill(settings.C_BG)

        # Subtle grid
        grid_surf = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        spacing = 64
        for x in range(0, self.sw + spacing, spacing):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 100), (x, 0), (x, self.sh))
        for y in range(0, self.sh + spacing, spacing):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 100), (0, y), (self.sw, y))
        surface.blit(grid_surf, (0, 0))

        cx = self.sw // 2
        cy = self.sh // 2

        # ── Title ─────────────────────────────────────────────────────────
        
      
        title = self._font_title.render("CHOOSE YOUR FACES", True, settings.C_WHITE)
        surface.blit(title, (cx - title.get_width() // 2, cy - 260))
        hint = self._font_hint.render(
            "Optional — skip either to use the default look", True, settings.C_MID_GRAY)
        surface.blit(hint, (cx - hint.get_width() // 2, cy - 220))



       

        # ── Left panel — Player ────────────────────────────────────────────
        self._draw_panel(surface, self._left_cx, self._panel_y,
                         "YOUR FACE", settings.C_PLAYER,
                         self._player_preview, self._btn_player,
                         self._btn_clear_player,
                         sprite_store.player_sprite is not None)

        # ── Right panel — Zombie ───────────────────────────────────────────
        self._draw_panel(surface, self._right_cx, self._panel_y,
                         "ZOMBIE FACE", settings.C_ACCENT_RED,
                         self._zombie_preview, self._btn_zombie,
                         self._btn_clear_zombie,
                         sprite_store.zombie_sprite is not None)

        # ── Start button (always visible, always clickable) ───────────────
        self._btn_start.draw(surface)
        self._btn_back.draw(surface)

        # Hint under start
        skip_hint = self._font_hint.render(
            "No photo chosen? Default visuals will be used.", True, settings.C_MID_GRAY)
        surface.blit(skip_hint, (cx - skip_hint.get_width() // 2, cy + 248))

        # ── Error message ─────────────────────────────────────────────────
        if self._error_t > 0:
            alpha = min(255, int(self._error_t * 200))
            err_surf = self._font_err.render(
                f"⚠  {self._error_msg}", True, settings.C_ACCENT_RED)
            err_surf.set_alpha(alpha)
            surface.blit(err_surf, (cx - err_surf.get_width() // 2, cy + 310))

    def _draw_panel(self, surface, cx, cy, label, accent_color,
                    preview_surf, upload_btn, clear_btn, has_image):
        p  = self.PREVIEW_SIZE
        pw = 240
        ph = 260

        # Panel background
        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((14, 18, 28, 210))
        border_color = accent_color if has_image else settings.C_MID_GRAY
        pygame.draw.rect(panel, border_color, (0, 0, pw, ph), 2, border_radius=10)
        surface.blit(panel, (cx - pw // 2, cy - ph // 2))

        # Label
        lbl = self._font_label.render(label, True, accent_color)
        surface.blit(lbl, (cx - lbl.get_width() // 2, cy - ph // 2 + 14))

        # Preview circle
        preview_cx = cx
        preview_cy = cy - ph // 2 + 100
        pygame.draw.circle(surface, (25, 30, 45),
                           (preview_cx, preview_cy), p // 2 + 4)
        pygame.draw.circle(surface, border_color,
                           (preview_cx, preview_cy), p // 2 + 4, 2)

        if preview_surf:
            surface.blit(preview_surf, (preview_cx - p // 2, preview_cy - p // 2))
            # Checkmark badge
            badge_x = preview_cx + p // 2 - 4
            badge_y = preview_cy - p // 2 + 4
            pygame.draw.circle(surface, (30, 180, 100), (badge_x, badge_y), 10)
            ok = self._font_hint.render("✓", True, settings.C_WHITE)
            surface.blit(ok, (badge_x - ok.get_width() // 2,
                              badge_y - ok.get_height() // 2))
        else:
            # Placeholder icon
            ph_font = pygame.font.SysFont("consolas", 36)
            ph_surf = ph_font.render("?", True, settings.C_MID_GRAY)
            surface.blit(ph_surf, (preview_cx - ph_surf.get_width() // 2,
                                    preview_cy - ph_surf.get_height() // 2))

        upload_btn.draw(surface)
        if has_image:
            clear_btn.draw(surface)


# ─── Main Menu ────────────────────────────────────────────────────────────────

class MainMenu:
    def __init__(self, screen_w, screen_h):
        self.sw, self.sh = screen_w, screen_h
        pygame.font.init()

        self._font_title = pygame.font.SysFont("consolas,monospace", 80, bold=True)
        self._font_sub   = pygame.font.SysFont("consolas,monospace", 22)
        self._font_btn   = pygame.font.SysFont("consolas,monospace", 24, bold=True)

        cx = screen_w // 2
        self._buttons = [
            _Button(cx, screen_h // 2 + 20,  260, 52, "PLAY", self._font_btn, "start"),
            _Button(cx, screen_h // 2 + 90,  260, 52, "QUIT", self._font_btn, "quit",
                    color_normal=(40, 20, 20), color_hover=(80, 30, 30)),
        ]
        self._t = 0.0
        self._scanline_surf = self._make_scanlines(screen_w, screen_h)

    def _make_scanlines(self, w, h):
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(0, h, 4):
            pygame.draw.line(s, (0, 0, 0, 30), (0, y), (w, y))
        return s

    def update(self, dt):
        self._t += dt
        mp = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.update(dt, mp)

    def handle_event(self, event):
        for btn in self._buttons:
            result = btn.handle_event(event)
            if result:
                return result
        return None

    def draw(self, surface):
        surface.fill(settings.C_BG)
        grid_surf = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        spacing = 64
        offset  = int(self._t * 20) % spacing
        for x in range(-spacing, self.sw + spacing, spacing):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 180),
                             (x + offset, 0), (x + offset, self.sh))
        for y in range(-spacing, self.sh + spacing, spacing):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 180),
                             (0, y + offset), (self.sw, y + offset))
        surface.blit(grid_surf, (0, 0))
        surface.blit(self._scanline_surf, (0, 0))

        pulse = abs(math.sin(self._t * 1.5))
        glow_alpha = int(80 + 60 * pulse)
        title_surf = self._font_title.render("DEADZONE", True, settings.C_PLAYER)
        glow_surf  = self._font_title.render("DEADZONE", True, settings.C_PLAYER_ACCENT)
        tx = self.sw // 2 - title_surf.get_width() // 2
        ty = self.sh // 2 - 180
        for off in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            g = glow_surf.copy()
            g.set_alpha(glow_alpha // 2)
            surface.blit(g, (tx + off[0], ty + off[1]))
        surface.blit(title_surf, (tx, ty))

        sub = self._font_sub.render("ZOMBIE SURVIVAL  •  WAVE SHOOTER", True, settings.C_MID_GRAY)
        surface.blit(sub, (self.sw // 2 - sub.get_width() // 2, ty + 90))

        controls = [
            "WASD — Move    SHIFT — Sprint    SPACE — Dash",
            "LMB — Shoot    R — Reload    1/2/3 — Weapon",
            "ESC — Pause",
        ]
        cy = self.sh - 100
        for line in controls:
            s = self._font_sub.render(line, True, settings.C_MID_GRAY)
            surface.blit(s, (self.sw // 2 - s.get_width() // 2, cy))
            cy += 22

        for btn in self._buttons:
            btn.draw(surface)


# ─── Pause Menu ───────────────────────────────────────────────────────────────

class PauseMenu:
    def __init__(self, screen_w, screen_h):
        self.sw, self.sh = screen_w, screen_h
        self._font_title = pygame.font.SysFont("consolas,monospace", 48, bold=True)
        self._font_btn   = pygame.font.SysFont("consolas,monospace", 24, bold=True)
        self._font_hint  = pygame.font.SysFont("consolas,monospace", 18)

        cx = screen_w // 2
        cy = screen_h // 2
        self._buttons = [
            _Button(cx, cy,       240, 48, "RESUME",    self._font_btn, "resume"),
            _Button(cx, cy + 66,  240, 48, "MAIN MENU", self._font_btn, "main_menu",
                    color_normal=(20, 30, 50)),
            _Button(cx, cy + 132, 240, 48, "QUIT",      self._font_btn, "quit",
                    color_normal=(40, 20, 20), color_hover=(80, 30, 30)),
        ]
        self._t = 0.0

    def update(self, dt):
        self._t += dt
        mp = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.update(dt, mp)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "resume"
        for btn in self._buttons:
            r = btn.handle_event(event)
            if r:
                return r
        return None

    def draw(self, surface):
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        pw, ph = 340, 420
        panel  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((10, 14, 24, 230))
        pygame.draw.rect(panel, settings.C_PLAYER, (0, 0, pw, ph), 2, border_radius=8)
        px = self.sw // 2 - pw // 2
        py = self.sh // 2 - ph // 2 - 20
        surface.blit(panel, (px, py))

        title = self._font_title.render("PAUSED", True, settings.C_WHITE)
        surface.blit(title, (self.sw // 2 - title.get_width() // 2, py + 24))

        for btn in self._buttons:
            btn.draw(surface)

        hint = self._font_hint.render("ESC to resume", True, settings.C_MID_GRAY)
        surface.blit(hint, (self.sw // 2 - hint.get_width() // 2, py + ph + 10))


# ─── Game Over Screen ─────────────────────────────────────────────────────────

class GameOverScreen:
    def __init__(self, screen_w, screen_h):
        self.sw, self.sh = screen_w, screen_h
        self._font_big   = pygame.font.SysFont("consolas,monospace", 72, bold=True)
        self._font_med   = pygame.font.SysFont("consolas,monospace", 28)
        self._font_btn   = pygame.font.SysFont("consolas,monospace", 24, bold=True)
        self._font_sm    = pygame.font.SysFont("consolas,monospace", 16)
        self._font_ai    = pygame.font.SysFont("consolas,monospace", 17)

        cx = screen_w // 2
        cy = screen_h // 2
        self._buttons = [
            _Button(cx, cy + 200, 240, 48, "PLAY AGAIN", self._font_btn, "restart"),
            _Button(cx, cy + 260, 240, 48, "MAIN MENU",  self._font_btn, "main_menu",
                    color_normal=(20, 30, 50)),
            _Button(cx, cy + 320, 240, 48, "QUIT",       self._font_btn, "quit",
                    color_normal=(40, 20, 20), color_hover=(80, 30, 30)),
        ]
        self._t          = 0.0
        self._score      = 0
        self._wave       = 0
        self._kills      = 0
        self._best_score = 0
        self._new_best   = False

        # AI analysis
        self._ai_text    = ""        # filled by background thread
        self._ai_pending = False
        self._ai_done    = False

    def set_results(self, score, wave, kills, best_score,
                    accuracy=0.0, time_alive=0, bullets_fired=0):
        self._score      = score
        self._wave       = wave
        self._kills      = kills
        self._best_score = best_score
        self._new_best   = (score >= best_score)
        self._t          = 0.0
        self._ai_text    = ""
        self._ai_done    = False
        self._ai_pending = True

        # Fire AI analysis in background
        import threading
        threading.Thread(
            target=self._fetch_analysis,
            args=(score, wave, kills, accuracy, time_alive, bullets_fired),
            daemon=True
        ).start()

    def _fetch_analysis(self, score, wave, kills,accuracy, time_alive, bullets_fired):
        try:
            import os
            from groq import Groq
            client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

            prompt = f"""You are a brutally honest tactical analyst for DEADZONE, a zombie survival game.
Analyse this player's run in exactly 2 sentences. Be specific, direct, and sarcastically funny — like a coach who's seen better but still cares.

Run stats:
- Score: {score}
- Waves survived: {wave}
- Kills: {kills}
- Accuracy: {accuracy:.1f}%
- Time alive: {time_alive} seconds
- Bullets fired: {bullets_fired}

Use the exact numbers. End with one sentence starting with "NEXT TIME:" giving one specific tip targeting their worst stat. 3 sentences total, plain text, no bullet points."""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=120,
                timeout=8,
            )
            raw = response.choices[0].message.content.strip()
            # Word wrap at ~60 chars per line
            words    = raw.split()
            lines    = []
            cur_line = ""
            for word in words:
                if len(cur_line) + len(word) + 1 > 62:
                    lines.append(cur_line)
                    cur_line = word
                else:
                    cur_line = (cur_line + " " + word).strip()
            if cur_line:
                lines.append(cur_line)
            self._ai_text = "\n".join(lines)
        except Exception as e:
            self._ai_text = f"Error: {e}"
        finally:
            self._ai_pending = False
            self._ai_done    = True

    def update(self, dt):
        self._t += dt
        mp = pygame.mouse.get_pos()
        for btn in self._buttons:
            btn.update(dt, mp)

    def handle_event(self, event):
        for btn in self._buttons:
            r = btn.handle_event(event)
            if r:
                return r
        return None

    def draw(self, surface):
        pulse    = abs(math.sin(self._t * 0.8))
        ov_alpha = int(120 + 60 * pulse) if self._t < 1.5 else 140
        overlay  = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((30, 0, 0, ov_alpha))
        surface.blit(overlay, (0, 0))

        cx = self.sw // 2
        cy = self.sh // 2

        # Title
        slide   = clamp(self._t * 3, 0.0, 1.0)
        title_y = int(cy - 220 - (1 - slide) * 80)
        title   = self._font_big.render("YOU DIED", True, settings.C_ACCENT_RED)
        surface.blit(title, (cx - title.get_width() // 2, title_y))

        # Stats
        if self._t > 0.4:
            stats = [
                ("SCORE", f"{self._score:,}"),
                ("WAVE",  str(self._wave)),
                ("KILLS", str(self._kills)),
                ("BEST",  f"{self._best_score:,}" + (" ★" if self._new_best else "")),
            ]
            for i, (label, value) in enumerate(stats):
                alpha = min(255, int((self._t - 0.4 - i * 0.1) * 500))
                lsurf = self._font_med.render(f"{label:<8}{value:>10}", True, settings.C_WHITE)
                lsurf.set_alpha(alpha)
                surface.blit(lsurf, (cx - lsurf.get_width() // 2, cy - 130 + i * 32))

        # AI Analysis panel
        if self._t > 0.8:
            panel_y = cy - 10
            panel_w = 680
            panel_h = 160
            panel   = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            panel.fill((10, 5, 5, 180))
            pygame.draw.rect(panel, (80, 20, 20), (0, 0, panel_w, panel_h), 1,
                             border_radius=6)
            surface.blit(panel, (cx - panel_w // 2, panel_y))

            # Label
            lbl = self._font_sm.render("⚡ AI TACTICAL ANALYSIS", True, (180, 40, 40))
            surface.blit(lbl, (cx - panel_w // 2 + 12, panel_y + 8))

            if self._ai_pending:
                # Animated dots while waiting
                dots    = "." * (int(self._t * 3) % 4)
                waiting = self._font_sm.render(f"ANALYSING RUN{dots}", True, (100, 100, 100))
                surface.blit(waiting, (cx - waiting.get_width() // 2, panel_y + 38))

            elif self._ai_done and self._ai_text:
                # Fade in analysis text
                alpha    = min(255, int((self._t - 0.8) * 150))
                lines    = self._ai_text.split("\n")
                line_y   = panel_y + 30
                for line in lines[:5]:   # max 5 lines
                    ls = self._font_ai.render(line, True, (220, 200, 200))
                    ls.set_alpha(alpha)
                    surface.blit(ls, (cx - panel_w // 2 + 12, line_y))
                    line_y += 22

        # Buttons
        if self._t > 1.0:
            for btn in self._buttons:
                btn.draw(surface)


# ─── Auth Screen (Login / Register / Guest) ──────────────────────────────────

class AuthScreen:
    """
    Replaces the old NameEntryScreen.
    Three modes: LOGIN, REGISTER, GUEST.
    - LOGIN/REGISTER: hits Railway backend, stores JWT in player_name_store
    - GUEST: skips auth, sets name only, is_guest=True
    All auth calls run in a background thread so the UI never freezes.
    """

    MAX_LEN  = 20
    BASE_URL = "https://deadzone-production-4446.up.railway.app"

    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.sw, self.sh = screen_w, screen_h
        pygame.font.init()

        self._font_title = pygame.font.SysFont("consolas,monospace", 44, bold=True)
        self._font_input = pygame.font.SysFont("consolas,monospace", 28, bold=True)
        self._font_hint  = pygame.font.SysFont("consolas,monospace", 15)
        self._font_btn   = pygame.font.SysFont("consolas,monospace", 20, bold=True)
        self._font_sm    = pygame.font.SysFont("consolas,monospace", 14)

        self._mode       = "choose"   # "choose" | "login" | "register" | "guest"
        self._field      = "user"     # "user" | "pass"
        self._username   = ""
        self._password   = ""
        self._cursor_t   = 0.0
        self._t          = 0.0
        self._status     = ""         # feedback message
        self._status_col = settings.C_MID_GRAY
        self._status_t   = 0.0
        self._loading    = False      # thread in flight
        self._result     = None       # set by thread: "ok" or "err:message"

        cx = screen_w // 2
        cy = screen_h // 2

        # Choose mode buttons
        self._btn_login    = _Button(cx, cy - 40,  280, 52, "LOGIN",
                                     self._font_btn, "login",
                                     color_normal=(16, 40, 60), color_hover=(24, 70, 110),
                                     text_color=settings.C_PLAYER_ACCENT)
        self._btn_register = _Button(cx, cy + 28,  280, 52, "REGISTER",
                                     self._font_btn, "register",
                                     color_normal=(20, 50, 30), color_hover=(30, 90, 50),
                                     text_color=settings.C_HEALTH_GOOD)
        self._btn_guest    = _Button(cx, cy + 96,  280, 40, "PLAY AS GUEST",
                                     self._font_btn, "guest",
                                     color_normal=(25, 25, 35), color_hover=(40, 40, 60))

        # Form buttons
        self._btn_submit   = _Button(cx, cy + 120, 260, 48, "CONFIRM",
                                     self._font_btn, "submit",
                                     color_normal=(20, 60, 40), color_hover=(30, 110, 70),
                                     text_color=settings.C_PLAYER_ACCENT)
        self._btn_back     = _Button(cx, cy + 182, 200, 36, "BACK",
                                     self._font_btn, "back",
                                     color_normal=(30, 30, 40), color_hover=(50, 50, 70))

    # ── Update / events ───────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self._t        += dt
        self._cursor_t += dt
        self._status_t  = max(0.0, self._status_t - dt)

        # Check thread result
        if self._result is not None:
            self._loading = False
            if self._result == "ok":
                pass   # game.py will read player_name_store and advance state
            else:
                self._show_status(self._result.replace("err:", ""), settings.C_ACCENT_RED)
            self._result = None

        mp = pygame.mouse.get_pos()
        if self._mode == "choose":
            for btn in [self._btn_login, self._btn_register, self._btn_guest]:
                btn.update(dt, mp)
        else:
            for btn in [self._btn_submit, self._btn_back]:
                btn.update(dt, mp)

    def handle_event(self, event) -> str | None:
        # While loading, ignore input
        if self._loading:
            return None

        if self._mode == "choose":
            if self._btn_login.handle_event(event)    == "login":
                self._mode = "login";    return None
            if self._btn_register.handle_event(event) == "register":
                self._mode = "register"; return None
            if self._btn_guest.handle_event(event)    == "guest":
                self._mode = "guest";    return None

        elif self._mode in ("login", "register"):
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    self._field = "pass" if self._field == "user" else "user"
                elif event.key == pygame.K_RETURN:
                    return self._submit()
                elif event.key == pygame.K_ESCAPE:
                    self._reset(); return None
                elif event.key == pygame.K_BACKSPACE:
                    if self._field == "user":
                        self._username = self._username[:-1]
                    else:
                        self._password = self._password[:-1]
                else:
                    char = event.unicode
                    if char and char.isprintable():
                        if self._field == "user" and len(self._username) < self.MAX_LEN:
                            self._username += char
                        elif self._field == "pass" and len(self._password) < self.MAX_LEN:
                            self._password += char

            if self._btn_submit.handle_event(event) == "submit":
                return self._submit()
            if self._btn_back.handle_event(event)   == "back":
                self._reset(); return None

            # Click to focus field
            if event.type == pygame.MOUSEBUTTONDOWN:
                cx, cy = self.sw // 2, self.sh // 2
                user_rect = pygame.Rect(cx - 210, cy - 60, 420, 52)
                pass_rect = pygame.Rect(cx - 210, cy + 10, 420, 52)
                if user_rect.collidepoint(event.pos): self._field = "user"
                if pass_rect.collidepoint(event.pos): self._field = "pass"

        elif self._mode == "guest":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    return self._confirm_guest()
                elif event.key == pygame.K_ESCAPE:
                    self._reset(); return None
                elif event.key == pygame.K_BACKSPACE:
                    self._username = self._username[:-1]
                else:
                    char = event.unicode
                    if char and char.isprintable() and len(self._username) < self.MAX_LEN:
                        self._username += char.upper()
            if self._btn_submit.handle_event(event) == "submit":
                return self._confirm_guest()
            if self._btn_back.handle_event(event)   == "back":
                self._reset(); return None

        return None

    # ── Auth logic ────────────────────────────────────────────────────────────

    def _submit(self) -> str | None:
        u = self._username.strip()
        p = self._password.strip()
        if not u:
            self._show_status("Username required.", settings.C_ACCENT_RED); return None
        if not p:
            self._show_status("Password required.", settings.C_ACCENT_RED); return None
        if len(u) < 3:
            self._show_status("Username too short (min 3).", settings.C_ACCENT_RED); return None

        self._loading = True
        self._show_status("Connecting...", settings.C_MID_GRAY)

        import threading
        endpoint = "/auth/login" if self._mode == "login" else "/auth/register"
        username, password = u, p

        def _call():
            try:
                import urllib.request, json
                body = json.dumps({"username": username, "password": password}).encode()
                req  = urllib.request.Request(
                    self.BASE_URL + endpoint,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                resp = urllib.request.urlopen(req, timeout=8)
                data = json.loads(resp.read())
                player_name_store.name     = data["username"]
                player_name_store.token    = data["token"]
                player_name_store.is_guest = False
                self._result = "ok"
            except urllib.error.HTTPError as e:
                try:
                    msg = json.loads(e.read()).get("detail", "Auth failed.")
                except Exception:
                    msg = f"Error {e.code}"
                self._result = f"err:{msg}"
            except Exception as ex:
                self._result = f"err:Connection failed. ({ex})"

        threading.Thread(target=_call, daemon=True).start()
        return None

    def _confirm_guest(self) -> str | None:
        name = self._username.strip()
        if not name:
            self._show_status("Enter a name first.", settings.C_ACCENT_RED)
            return None
        player_name_store.name     = name[:self.MAX_LEN]
        player_name_store.token    = ""
        player_name_store.is_guest = True
        return "confirm"

    def _reset(self):
        self._mode     = "choose"
        self._field    = "user"
        self._username = ""
        self._password = ""
        self._loading  = False
        self._result   = None

    def _show_status(self, msg: str, color) -> None:
        self._status     = msg
        self._status_col = color
        self._status_t   = 4.0

    # ── Check if auth succeeded (called by game.py) ───────────────────────────

    @property
    def auth_complete(self) -> bool:
        """True when logged in or guest confirmed — game.py polls this."""
        return not player_name_store.is_guest or (
            player_name_store.is_guest and bool(player_name_store.name.strip())
            and self._mode == "guest" and self._result is None and not self._loading
        )

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill(settings.C_BG)

        # Grid
        grid_surf = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        for x in range(0, self.sw + 64, 64):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 100), (x, 0), (x, self.sh))
        for y in range(0, self.sh + 64, 64):
            pygame.draw.line(grid_surf, (*settings.C_GRID, 100), (0, y), (self.sw, y))
        surface.blit(grid_surf, (0, 0))

        cx = self.sw // 2
        cy = self.sh // 2

        if self._mode == "choose":
            self._draw_choose(surface, cx, cy)
        elif self._mode in ("login", "register"):
            self._draw_form(surface, cx, cy)
        elif self._mode == "guest":
            self._draw_guest(surface, cx, cy)

        # Status message
        if self._status_t > 0:
            alpha = min(255, int(self._status_t * 120))
            s = self._font_hint.render(self._status, True, self._status_col)
            s.set_alpha(alpha)
            surface.blit(s, (cx - s.get_width() // 2, cy + 230))

    def _draw_choose(self, surface, cx, cy):
        title = self._font_title.render("DEADZONE", True, settings.C_PLAYER)
        surface.blit(title, (cx - title.get_width() // 2, cy - 160))
        sub = self._font_hint.render("IDENTIFY YOURSELF, SOLDIER", True, settings.C_MID_GRAY)
        surface.blit(sub, (cx - sub.get_width() // 2, cy - 108))
        self._btn_login.draw(surface)
        self._btn_register.draw(surface)
        self._btn_guest.draw(surface)

        guest_note = self._font_sm.render(
            "Guest scores are saved but not linked to a profile.", True, (40, 45, 60))
        surface.blit(guest_note, (cx - guest_note.get_width() // 2, cy + 148))

    def _draw_form(self, surface, cx, cy):
        mode_label = "LOGIN" if self._mode == "login" else "CREATE ACCOUNT"
        title = self._font_title.render(mode_label, True, settings.C_WHITE)
        surface.blit(title, (cx - title.get_width() // 2, cy - 180))

        tab_hint = self._font_sm.render("TAB to switch fields  •  ENTER to confirm", True, settings.C_MID_GRAY)
        surface.blit(tab_hint, (cx - tab_hint.get_width() // 2, cy - 130))

        # Username field
        self._draw_input_field(surface, cx, cy - 60, "USERNAME",
                               self._username, self._field == "user", False)
        # Password field
        self._draw_input_field(surface, cx, cy + 10, "PASSWORD",
                               self._password, self._field == "pass", True)

        if self._loading:
            dots = "." * (int(self._t * 3) % 4)
            ls = self._font_btn.render(f"AUTHENTICATING{dots}", True, settings.C_MID_GRAY)
            surface.blit(ls, (cx - ls.get_width() // 2, cy + 80))
        else:
            self._btn_submit.draw(surface)
            self._btn_back.draw(surface)

    def _draw_guest(self, surface, cx, cy):
        title = self._font_title.render("GUEST MODE", True, settings.C_ACCENT_GOLD)
        surface.blit(title, (cx - title.get_width() // 2, cy - 180))
        hint = self._font_hint.render("Enter a display name for the leaderboard", True, settings.C_MID_GRAY)
        surface.blit(hint, (cx - hint.get_width() // 2, cy - 130))
        self._draw_input_field(surface, cx, cy - 40, "YOUR NAME",
                               self._username, True, False)
        self._btn_submit.draw(surface)
        self._btn_back.draw(surface)

    def _draw_input_field(self, surface, cx, cy, label, text, focused, hide_text):
        box_w, box_h = 420, 52
        bx = cx - box_w // 2

        lbl = self._font_sm.render(label, True,
                                    settings.C_PLAYER if focused else settings.C_MID_GRAY)
        surface.blit(lbl, (bx, cy - 18))

        border_col = settings.C_PLAYER if focused else (30, 35, 50)
        pygame.draw.rect(surface, (12, 15, 22), (bx, cy, box_w, box_h), border_radius=5)
        pygame.draw.rect(surface, border_col,   (bx, cy, box_w, box_h), 2, border_radius=5)

        display = ("*" * len(text)) if hide_text else text
        if focused and int(self._cursor_t * 2) % 2 == 0:
            display += "_"

        ts = self._font_input.render(display, True,
                                      settings.C_PLAYER_ACCENT if focused else settings.C_WHITE)
        surface.blit(ts, (bx + 12, cy + box_h // 2 - ts.get_height() // 2))