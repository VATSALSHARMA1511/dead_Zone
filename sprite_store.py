"""
sprite_store.py — Singleton that holds custom user-uploaded sprites.

WHY THIS EXISTS:
  Both player.py and zombie.py need access to the loaded images.
  A simple module-level singleton avoids circular imports — neither entity
  imports the other, they both just import this one tiny file.

USAGE:
  # In sprite picker (menus.py):
  import sprite_store
  sprite_store.set_player_image("C:/Users/.../photo.png")
  sprite_store.set_zombie_image("C:/Users/.../face.png")

  # In player.py / zombie.py draw():
  import sprite_store
  if sprite_store.player_sprite:
      surface.blit(sprite_store.player_sprite, ...)
"""

import pygame

# ── Public surfaces (None until user uploads) ─────────────────────────────────
player_sprite: pygame.Surface | None = None   # 64×64, circular mask, SRCALPHA
zombie_sprite: pygame.Surface | None = None   # 64×64, circular mask, SRCALPHA


def set_player_image(path: str) -> bool:
    """
    Load image at path, crop to circle, store in player_sprite.
    Returns True on success, False if file is invalid/unreadable.
    """
    global player_sprite
    result = _load_circular(path, 64)
    if result:
        player_sprite = result
        return True
    return False


def set_zombie_image(path: str) -> bool:
    """
    Load image at path, crop to circle, store in zombie_sprite.
    Returns True on success, False if file is invalid/unreadable.
    """
    global zombie_sprite
    result = _load_circular(path, 64)
    if result:
        zombie_sprite = result
        return True
    return False


def clear():
    """Reset both sprites to None (called on full game reset if needed)."""
    global player_sprite, zombie_sprite
    player_sprite = None
    zombie_sprite = None


def _load_circular(path: str, size: int) -> pygame.Surface | None:
    """
    Core image processing pipeline:
      1. Load from disk
      2. Crop to square from center
      3. Scale to `size` × `size`
      4. Apply circular alpha mask
      5. Return SRCALPHA surface

    Returns None if anything fails (bad path, corrupt file, wrong format).
    """
    try:
        raw = pygame.image.load(path).convert_alpha()
    except Exception:
        try:
            # Some formats need convert() instead
            raw = pygame.image.load(path).convert()
        except Exception:
            return None

    # ── Step 1: Crop to square from center ────────────────────────────────
    w, h   = raw.get_size()
    side   = min(w, h)
    crop_x = (w - side) // 2
    crop_y = (h - side) // 2
    cropped = raw.subsurface(pygame.Rect(crop_x, crop_y, side, side)).copy()

    # ── Step 2: Scale to target size ──────────────────────────────────────
    scaled = pygame.transform.smoothscale(cropped, (size, size))

    # ── Step 3: Apply circular mask ───────────────────────────────────────
    result = pygame.Surface((size, size), pygame.SRCALPHA)
    result.fill((0, 0, 0, 0))  # fully transparent base

    # Draw white circle as mask
    mask_surf = pygame.Surface((size, size), pygame.SRCALPHA)
    mask_surf.fill((0, 0, 0, 0))
    pygame.draw.circle(mask_surf, (255, 255, 255, 255), (size // 2, size // 2), size // 2)

    # Blit image, then apply mask via BLEND_RGBA_MIN
    result.blit(scaled, (0, 0))
    result.blit(mask_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

    return result


def get_scaled(sprite: pygame.Surface, diameter: int) -> pygame.Surface:
    """
    Return a version of `sprite` scaled to `diameter` px.
    Cached by the caller if called frequently.
    """
    return pygame.transform.smoothscale(sprite, (diameter, diameter))


def get_rotated(sprite: pygame.Surface, angle_deg: float) -> pygame.Surface:
    """
    Return sprite rotated by angle_deg.
    pygame.transform.rotate uses counter-clockwise convention,
    but our facing angle is clockwise — so we negate it.
    """
    return pygame.transform.rotate(sprite, -angle_deg)
