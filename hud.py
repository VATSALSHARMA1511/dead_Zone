"""
ui/hud.py — In-game HUD rendering.
"""

import math
import pygame
import settings
from helpers import draw_bar, clamp


class HUD:
    def __init__(self, screen_w: int, screen_h: int) -> None:
        self.sw = screen_w
        self.sh = screen_h

        pygame.font.init()
        self._font_lg  = pygame.font.SysFont("consolas,monospace", settings.HUD_FONT_LARGE, bold=True)
        self._font_md  = pygame.font.SysFont("consolas,monospace", settings.HUD_FONT_MED)
        self._font_sm  = pygame.font.SysFont("consolas,monospace", settings.HUD_FONT_SMALL)
        self._font_xl  = pygame.font.SysFont("consolas,monospace", 64, bold=True)

        self._margin   = settings.HUD_MARGIN
        self._panel_h  = 70
        self._pulse_t  = 0.0
        self._wave_clear_t = 0.0

    def update(self, dt: float) -> None:
        self._pulse_t += dt
        if self._wave_clear_t > 0:
            self._wave_clear_t -= dt

    def show_wave_clear(self) -> None:
        self._wave_clear_t = 2.5

    def draw(self, surface: pygame.Surface, player, wave_mgr,
             score: int, fps: int, particle_count: int,
             streak: int = 0) -> None:
        self._draw_bottom_panel(surface, player)
        self._draw_top_bar(surface, score, wave_mgr, fps, particle_count, streak)
        self._draw_crosshair(surface, player)
        self._draw_reload_indicator(surface, player)
        self._draw_wave_alert(surface, wave_mgr)
        self._draw_wave_clear(surface)
        self._draw_weapon_slots(surface, player)

    # ── Bottom panel ─────────────────────────────────────────────────────────

    def _draw_bottom_panel(self, surface: pygame.Surface, player) -> None:
        m   = self._margin
        pw  = self.sw
        ph  = self._panel_h
        py  = self.sh - ph

        panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel.fill((8, 10, 16, 200))
        surface.blit(panel, (0, py))
        pygame.draw.line(surface, settings.C_MID_GRAY, (0, py), (pw, py), 1)

        bw = settings.HUD_BAR_W
        bh = settings.HUD_BAR_H
        bx = m
        by = py + 14

        hp_label = self._font_sm.render("HP", True, settings.C_MID_GRAY)
        surface.blit(hp_label, (bx, by - 14))

        hp_ratio = player.health / player.max_health
        if hp_ratio > 0.5:
            bar_col = settings.C_HEALTH_GOOD
        elif hp_ratio > 0.25:
            bar_col = settings.C_ACCENT_GOLD
        else:
            pulse   = abs(math.sin(self._pulse_t * 4))
            bar_col = (int(200 + 55 * pulse), 30, 30)

        draw_bar(surface, bx, by, bw, bh,
                 player.health, player.max_health,
                 bar_col, settings.C_HEALTH_BAR_BG,
                 border_color=settings.C_MID_GRAY)

        hp_text = self._font_sm.render(
            f"{player.health}/{player.max_health}", True, settings.C_WHITE)
        surface.blit(hp_text, (bx + bw + 8, by - 2))

        by2 = by + bh + 10
        sta_label = self._font_sm.render("STAM", True, settings.C_MID_GRAY)
        surface.blit(sta_label, (bx, by2 - 14))
        draw_bar(surface, bx, by2, bw, bh - 4,
                 player.stamina, player.max_stamina,
                 settings.C_XP_BAR, (20, 25, 40),
                 border_color=settings.C_MID_GRAY)

        dcx    = bx + bw + 70
        dcy    = py + self._panel_h // 2
        dash_r = 14
        ratio  = player.dash_cooldown_ratio
        color  = settings.C_PLAYER if ratio >= 1.0 else settings.C_MID_GRAY
        pygame.draw.circle(surface, (20, 25, 40), (dcx, dcy), dash_r)
        if ratio > 0:
            start_angle = -math.pi / 2
            end_angle   = start_angle + math.tau * ratio
            rect        = pygame.Rect(dcx - dash_r, dcy - dash_r, dash_r * 2, dash_r * 2)
            pygame.draw.arc(surface, color, rect, start_angle, end_angle, 4)
        pygame.draw.circle(surface, color, (dcx, dcy), dash_r, 2)
        dash_lbl = self._font_sm.render("DASH", True, settings.C_MID_GRAY)
        surface.blit(dash_lbl, (dcx - dash_lbl.get_width() // 2, dcy + dash_r + 2))

    # ── Top info bar ─────────────────────────────────────────────────────────

    def _draw_top_bar(self, surface: pygame.Surface, score: int,
                       wave_mgr, fps: int, particle_count: int,
                       streak: int) -> None:
        m  = self._margin
        bh = 36
        panel = pygame.Surface((self.sw, bh), pygame.SRCALPHA)
        panel.fill((8, 10, 16, 180))
        surface.blit(panel, (0, 0))
        pygame.draw.line(surface, settings.C_MID_GRAY, (0, bh), (self.sw, bh), 1)

        score_surf = self._font_md.render(f"SCORE  {score:,}", True, settings.C_ACCENT_GOLD)
        surface.blit(score_surf, (m, 7))

        wave_text = f"WAVE  {wave_mgr.wave_number}"
        if wave_mgr.is_boss_wave and not wave_mgr.in_cooldown:
            wave_text += "  ⚠ BOSS"
        wave_surf = self._font_md.render(wave_text, True, settings.C_WHITE)
        surface.blit(wave_surf, (self.sw // 2 - wave_surf.get_width() // 2, 7))

        fps_surf = self._font_sm.render(f"FPS {fps}  P{particle_count}", True, settings.C_MID_GRAY)
        surface.blit(fps_surf, (self.sw - fps_surf.get_width() - m, 10))

        if streak >= 5:
            multiplier   = max(1, streak // 5)
            pulse        = abs(math.sin(self._pulse_t * 6))
            streak_color = (255, int(150 + 105 * pulse), int(50 * pulse))
            streak_surf  = self._font_sm.render(
                f"x{multiplier} STREAK  ({streak} kills)", True, streak_color)
            surface.blit(streak_surf, (m, bh + 6))

    # ── Wave clear banner — TOP LEFT, small, unobtrusive ─────────────────────

    def _draw_wave_clear(self, surface: pygame.Surface) -> None:
        if self._wave_clear_t <= 0:
            return
        alpha = int(clamp(self._wave_clear_t * 200, 0, 255))
        s     = self._font_md.render("✓  WAVE CLEARED", True, settings.C_HEALTH_GOOD)
        tmp   = pygame.Surface((s.get_width(), s.get_height()), pygame.SRCALPHA)
        tmp.blit(s, (0, 0))
        tmp.set_alpha(alpha)
        # Top left, below top bar — doesn't overlap anything
        surface.blit(tmp, (self._margin, 46))

    # ── Wave summary panel — RIGHT SIDE, clear of center ─────────────────────

    def draw_wave_summary(self, surface: pygame.Surface, wave_mgr) -> None:
        stats = wave_mgr.last_wave_stats
        if not stats:
            return

        cd        = settings.WAVE_COOLDOWN
        remaining = wave_mgr.cooldown_remaining

        fade_in  = min(1.0, (cd - remaining) * 4)
        fade_out = min(1.0, remaining / 1.2)
        alpha    = int(255 * fade_in * fade_out)
        if alpha <= 0:
            return

        # Position: right side of screen, vertically centered
        panel_w = 300
        panel_h = 180
        panel_x = self.sw - panel_w - self._margin
        panel_y = self.sh // 2 - panel_h // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((8, 10, 18, 210))
        pygame.draw.rect(panel, settings.C_PLAYER, (0, 0, panel_w, panel_h), 1, border_radius=8)
        panel.set_alpha(alpha)
        surface.blit(panel, (panel_x, panel_y))

        # Header
        header   = self._font_sm.render(f"WAVE {stats['wave']} COMPLETE", True, settings.C_PLAYER)
        hs       = pygame.Surface((header.get_width(), header.get_height()), pygame.SRCALPHA)
        hs.blit(header, (0, 0))
        hs.set_alpha(alpha)
        cx_panel = panel_x + panel_w // 2
        surface.blit(hs, (cx_panel - header.get_width() // 2, panel_y + 12))

        # Divider
        div_surf = pygame.Surface((panel_w - 32, 1), pygame.SRCALPHA)
        div_surf.fill((*settings.C_MID_GRAY, alpha))
        surface.blit(div_surf, (panel_x + 16, panel_y + 34))

        # Stats
        accuracy  = stats["accuracy_pct"]
        kills     = stats["kills"]
        damage    = stats["damage_taken"]

        acc_color = (settings.C_HEALTH_GOOD if accuracy >= 60
                     else settings.C_ACCENT_GOLD if accuracy >= 35
                     else settings.C_ACCENT_RED)
        dmg_color = (settings.C_HEALTH_GOOD if damage == 0
                     else settings.C_ACCENT_GOLD if damage < 30
                     else settings.C_ACCENT_RED)

        items = [
            ("KILLS",    str(kills),         settings.C_ACCENT_GOLD),
            ("ACCURACY", f"{accuracy:.1f}%", acc_color),
            ("DAMAGE",   f"-{damage} HP",    dmg_color),
        ]

        col_w   = panel_w // len(items)
        value_y = panel_y + 55
        label_y = panel_y + 95

        for i, (label, value, color) in enumerate(items):
            col_cx   = panel_x + col_w * i + col_w // 2
            val_surf = self._font_md.render(value, True, color)
            vs       = pygame.Surface((val_surf.get_width(), val_surf.get_height()), pygame.SRCALPHA)
            vs.blit(val_surf, (0, 0))
            vs.set_alpha(alpha)
            surface.blit(vs, (col_cx - val_surf.get_width() // 2, value_y))

            lbl_surf = self._font_sm.render(label, True, settings.C_MID_GRAY)
            ls       = pygame.Surface((lbl_surf.get_width(), lbl_surf.get_height()), pygame.SRCALPHA)
            ls.blit(lbl_surf, (0, 0))
            ls.set_alpha(alpha)
            surface.blit(ls, (col_cx - lbl_surf.get_width() // 2, label_y))

        for i in range(1, len(items)):
            div_x = panel_x + col_w * i
            dv    = pygame.Surface((1, 60), pygame.SRCALPHA)
            dv.fill((*settings.C_MID_GRAY, alpha // 2))
            surface.blit(dv, (div_x, panel_y + 45))

        # Grade
        if accuracy >= 75 and damage == 0:
            grade, gcol = "S", settings.C_PLAYER_ACCENT
        elif accuracy >= 60 and damage < 20:
            grade, gcol = "A", settings.C_HEALTH_GOOD
        elif accuracy >= 45 and damage < 40:
            grade, gcol = "B", settings.C_ACCENT_GOLD
        elif accuracy >= 30 and damage < 60:
            grade, gcol = "C", (200, 150, 50)
        else:
            grade, gcol = "D", settings.C_ACCENT_RED

        grade_font = pygame.font.SysFont("consolas,monospace", 48, bold=True)
        grade_surf = grade_font.render(grade, True, gcol)
        gs         = pygame.Surface((grade_surf.get_width(), grade_surf.get_height()), pygame.SRCALPHA)
        gs.blit(grade_surf, (0, 0))
        gs.set_alpha(alpha)
        surface.blit(gs, (panel_x + panel_w - 50, panel_y + 120))

    # ── Wave alert — BOTTOM CENTER, clear of summary panel ───────────────────

    def _draw_wave_alert(self, surface: pygame.Surface, wave_mgr) -> None:
        if not wave_mgr.in_cooldown:
            return
        t  = wave_mgr.cooldown_remaining
        cd = settings.WAVE_COOLDOWN

        alpha_ratio = min(1.0, (cd - t) * 3) * min(1.0, t * 3)
        alpha       = int(255 * alpha_ratio)
        if alpha <= 0:
            return

        next_wave = wave_mgr.wave_number + 1
        is_boss   = (next_wave % settings.WAVE_BOSS_EVERY == 0)

        if is_boss:
            text  = f"⚠  BOSS WAVE  {next_wave}  ⚠"
            color = settings.C_ACCENT_RED
        else:
            text  = f"WAVE  {next_wave}  INCOMING"
            color = settings.C_WHITE

        msg_surf   = self._font_lg.render(text, True, color)
        count_surf = self._font_xl.render(f"{int(t) + 1}", True, settings.C_ACCENT_GOLD)

        cx  = self.sw // 2
        # Bottom center — well below the summary panel on the right
        cy  = self.sh - self._panel_h - 160
        tmp = pygame.Surface((self.sw, 120), pygame.SRCALPHA)
        tmp.blit(msg_surf,   (cx - msg_surf.get_width() // 2, 10))
        tmp.blit(count_surf, (cx - count_surf.get_width() // 2, 50))
        tmp.set_alpha(alpha)
        surface.blit(tmp, (0, cy))

    # ── Crosshair ────────────────────────────────────────────────────────────
    def _draw_weapon_slots(self, surface: pygame.Surface, player) -> None:
        from constants import WEAPON_ORDER
        slot_w, slot_h = 80, 64
        gap     = 6
        total   = len(WEAPON_ORDER) * (slot_w + gap) - gap
        start_x = self.sw - total - self._margin
        start_y = self.sh - self._panel_h - slot_h - 8
        for i, wname in enumerate(WEAPON_ORDER):
            sx = start_x + i * (slot_w + gap)
            sy = start_y
            active  = (i == player._weapon_slot)
            bg_col  = (30, 40, 60) if active else (12, 15, 22)
            bdr_col = settings.C_PLAYER if active else settings.C_MID_GRAY
            pygame.draw.rect(surface, bg_col,  (sx, sy, slot_w, slot_h), border_radius=4)
            pygame.draw.rect(surface, bdr_col, (sx, sy, slot_w, slot_h), 2, border_radius=4)
            name_surf = self._font_sm.render(wname.upper(), True,
                                            settings.C_WHITE if active else settings.C_MID_GRAY)
            surface.blit(name_surf, (sx + slot_w // 2 - name_surf.get_width() // 2, sy + 4))
            if active:
                ws        = player._weapons[wname]
                ammo_text = f"{ws.ammo}/{player.ammo_max}"
                if player.is_reloading:
                    ammo_text = "RELOAD"
                    ammo_surf = self._font_sm.render(ammo_text, True, (255, 0, 0))
                    surface.blit(ammo_surf,
                                 (sx + slot_w // 2 - ammo_surf.get_width() // 2, sy + 26))
                if not player.is_reloading:
                    pip_w = (slot_w - 8) // player.ammo_max
                    for p in range(player.ammo_max):
                        pcol = settings.C_ACCENT_GOLD if p < ws.ammo else (40, 40, 50)
                        pygame.draw.rect(surface, pcol,
                                         (sx + 4 + p * pip_w, sy + slot_h - 8,
                                          max(1, pip_w - 1), 4))
            else:
                key_surf = self._font_sm.render(str(i + 1), True, settings.C_MID_GRAY)
                surface.blit(key_surf,
                            (sx + slot_w // 2 - key_surf.get_width() // 2, sy + 26))

    def _draw_crosshair(self, surface: pygame.Surface, player) -> None:
        mx, my = pygame.mouse.get_pos()
        size, gap, w = 10, 5, 2
        color = settings.C_WHITE
        pygame.draw.line(surface, color, (mx - size - gap, my), (mx - gap, my), w)
        pygame.draw.line(surface, color, (mx + gap, my), (mx + size + gap, my), w)
        pygame.draw.line(surface, color, (mx, my - size - gap), (mx, my - gap), w)
        pygame.draw.line(surface, color, (mx, my + gap), (mx, my + size + gap), w)
        pygame.draw.circle(surface, color, (mx, my), 2, 1)

    # ── Reload indicator ─────────────────────────────────────────────────────

    def _draw_reload_indicator(self, surface: pygame.Surface, player) -> None:
        if not player.is_reloading:
            return
        mx, my   = pygame.mouse.get_pos()
        r        = 20
        progress = player.reload_progress
        start_a  = -math.pi / 2
        end_a    = start_a + math.tau * progress
        rect     = pygame.Rect(mx - r, my + 12, r * 2, r * 2)
        pygame.draw.arc(surface, settings.C_ACCENT_GOLD, rect, start_a, end_a, 3)
        pygame.draw.arc(surface, settings.C_MID_GRAY,   rect, end_a, start_a + math.tau, 3)