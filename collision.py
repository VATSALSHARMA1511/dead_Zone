"""
systems/collision.py — Centralised collision detection and resolution.

WHY THIS EXISTS:
  Collision logic scattered across entities creates circular import hell and
  O(n²) redundant checks. A dedicated system:
  - Owns the collision budget
  - Can add spatial partitioning later without touching entities
  - Provides a single place to profile and optimise

COLLISION PIPELINE (per frame):
  1. bullets ↔ zombies  → damage + death + particles
  2. zombies ↔ player   → player damage + iframes check
  3. zombie ↔ zombie    → separation push (prevents stacking)
  4. player bounds       → clamp inside world

PERFORMANCE NOTE:
  For <200 entities Python's O(n²) brute-force is fast enough (< 0.3 ms per
  frame). If you need more zombies, add a simple grid spatial hash here — the
  interface stays identical.
"""
import pygame
import settings
from helpers import circles_overlap, push_apart, distance


class CollisionSystem:
    def __init__(self, world_w: int, world_h: int) -> None:
        self.world_w = world_w
        self.world_h = world_h

    def process(self, player, bullets: list, zombies: list,obstacles: list,
                particles, camera) -> None:
        """
        Main entry point called once per frame.
        Mutates entities in-place; never returns values.
        """
        self._bullets_vs_zombies(bullets, zombies, particles)
        self._player_vs_zombies(player, zombies, particles, camera)
        self._zombie_separation(zombies)
        self._player_vs_obstacles(player, obstacles)
        self._zombies_vs_obstacles(zombies, obstacles)
        self._clamp_player(player)
        self._clamp_zombies(zombies)

    # ── Collision tests ───────────────────────────────────────────────────────

    def _bullets_vs_zombies(self, bullets: list, zombies: list,
                             particles) -> None:
        to_remove_bullets = set()
        for bi, bullet in enumerate(bullets):
            if not bullet.alive:
                continue
            for zombie in zombies:
                if not zombie.alive:
                    continue
                if circles_overlap(bullet.x, bullet.y, settings.BULLET_RADIUS,
                                   zombie.x, zombie.y, zombie.radius):
                    # Direction from zombie toward bullet origin (recoil direction)
                    dx = bullet.vx
                    dy = bullet.vy
                    length = (dx*dx + dy*dy) ** 0.5
                    if length > 0:
                        dx, dy = dx / length, dy / length

                    zombie.take_damage(bullet.damage)
                    zombie.x += dx * 18
                    zombie.y += dy * 18
                    particles.spawn_blood(zombie.x, zombie.y, (dx, dy))

                    to_remove_bullets.add(bi)
                    break  # one bullet hits one zombie

        # Remove consumed bullets (reverse order preserves indices)
        for i in sorted(to_remove_bullets, reverse=True):
            bullets[i].alive = False

    def _player_vs_zombies(self, player, zombies: list,
                            particles, camera) -> None:
        for zombie in zombies:
            if not zombie.alive:
                continue
            if circles_overlap(player.x, player.y, player.radius,
                                zombie.x, zombie.y, zombie.radius):
                # Zombie attacks based on its attack timer
                if zombie.can_attack():
                    damage = zombie.get_damage()
                    if player.take_damage(damage):
                        camera.add_shake(10.0)
                        particles.spawn_player_damage(player.x, player.y)

    def _zombie_separation(self, zombies: list) -> None:
        """Push overlapping zombies apart to prevent pile-ups."""
        r = settings.ZOMBIE_SEPARATION_RADIUS
        for i in range(len(zombies)):
            if not zombies[i].alive:
                continue
            for j in range(i + 1, len(zombies)):
                if not zombies[j].alive:
                    continue
                za, zb = zombies[i], zombies[j]
                combined_r = za.radius + zb.radius
                if circles_overlap(za.x, za.y, za.radius,
                                   zb.x, zb.y, zb.radius):
                    da, db = push_apart(za.x, za.y, za.radius,
                                        zb.x, zb.y, zb.radius, strength=0.9)
                    za.x += da[0]
                    za.y += da[1]
                    zb.x += db[0]
                    zb.y += db[1]

    def _clamp_player(self, player) -> None:
        r = player.radius
        player.x = max(r, min(self.world_w - r, player.x))
        player.y = max(r, min(self.world_h - r, player.y))

    def _clamp_zombies(self, zombies: list) -> None:
        for z in zombies:
            if not z.alive:
                continue
            r = z.radius
            z.x = max(r, min(self.world_w - r, z.x))
            z.y = max(r, min(self.world_h - r, z.y))
        # ── Obstacle collision ─────────────────────────────────────────────

    def _player_vs_obstacles(self, player, obstacles):

        player_rect = pygame.Rect(
            player.x - player.radius,
            player.y - player.radius,
            player.radius * 2,
            player.radius * 2
        )

        for obstacle in obstacles:

            if player_rect.colliderect(obstacle.rect):

                overlap_left = player_rect.right - obstacle.rect.left
                overlap_right = obstacle.rect.right - player_rect.left

                overlap_top = player_rect.bottom - obstacle.rect.top
                overlap_bottom = obstacle.rect.bottom - player_rect.top

                min_overlap = min(
                    overlap_left,
                    overlap_right,
                    overlap_top,
                    overlap_bottom
                )

                if min_overlap == overlap_left:
                    player.x -= overlap_left

                elif min_overlap == overlap_right:
                    player.x += overlap_right

                elif min_overlap == overlap_top:
                    player.y -= overlap_top

                elif min_overlap == overlap_bottom:
                    player.y += overlap_bottom

                player_rect.x = player.x - player.radius
                player_rect.y = player.y - player.radius


    def _zombies_vs_obstacles(self, zombies, obstacles):

        for zombie in zombies:

            if not zombie.alive:
                continue

            zombie_rect = pygame.Rect(
                zombie.x - zombie.radius,
                zombie.y - zombie.radius,
                zombie.radius * 2,
                zombie.radius * 2
            )

            for obstacle in obstacles:

                if zombie_rect.colliderect(obstacle.rect):

                    overlap_left = zombie_rect.right - obstacle.rect.left
                    overlap_right = obstacle.rect.right - zombie_rect.left

                    overlap_top = zombie_rect.bottom - obstacle.rect.top
                    overlap_bottom = obstacle.rect.bottom - zombie_rect.top

                    min_overlap = min(
                        overlap_left,
                        overlap_right,
                        overlap_top,
                        overlap_bottom
                    )

                    if min_overlap == overlap_left:
                        zombie.x -= overlap_left * 0.7

                    elif min_overlap == overlap_right:
                        zombie.x += overlap_right * 0.7

                    elif min_overlap == overlap_top:
                        zombie.y -= overlap_top * 0.7

                    elif min_overlap == overlap_bottom:
                        zombie.y += overlap_bottom * 0.7

                    zombie_rect.x = zombie.x - zombie.radius
                    zombie_rect.y = zombie.y - zombie.radius
