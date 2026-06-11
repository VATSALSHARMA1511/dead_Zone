import pygame
import settings


class Obstacle:
    def __init__(self, x, y, w, h,
                 color=(40, 55, 80),
                 border=(0, 255, 200)):

        self.x = x
        self.y = y
        self.w = w
        self.h = h

        self.color = color
        self.border = border

        self.rect = pygame.Rect(x, y, w, h)

    def draw(self, surface, cam):

        sx = self.x - cam.x
        sy = self.y - cam.y

        rect = pygame.Rect(sx, sy, self.w, self.h)

        # Main body
        pygame.draw.rect(surface, self.color, rect, border_radius=6)

        # Neon outline
        pygame.draw.rect(surface, self.border, rect, 2, border_radius=6)
        glow_rect = pygame.Rect(
            sx - 4,
            sy - 4,
            self.w + 8,
            self.h + 8
        )
        glow_surf = pygame.Surface(
            (glow_rect.width, glow_rect.height),
            pygame.SRCALPHA
        )
        pygame.draw.rect(
            glow_surf,
            (*self.border, 35),
            glow_surf.get_rect(),
            width=6,
            border_radius=10
        )
        surface.blit(
            glow_surf,
            glow_rect.topleft,
            special_flags=pygame.BLEND_RGBA_ADD
        )

        # Inner glow line
        inner = rect.inflate(-10, -10)

        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(
                surface,
                (20, 30, 45),
                inner,
                border_radius=4
            )

        # Shadow
        shadow = pygame.Surface((self.w, self.h), pygame.SRCALPHA)

        pygame.draw.rect(
            shadow,
            (0, 0, 0, 60),
            shadow.get_rect(),
            border_radius=6
        )

        surface.blit(shadow, (sx + 5, sy + 5))