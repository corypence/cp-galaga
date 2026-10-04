"""T-03 · Display + hardware matrix (MMA-6051, covers R3).

Emulates the Namco/Midway Galaga hardware screen: 224x288 vertical (3:4 CRT), origin
(0,0) at top-left, a 16-color per-sprite palette (PROM), and a 3-layer starfield that
scrolls at fast/medium/slow rates and blinks between yellow, cyan and white.
"""
from __future__ import annotations
from dataclasses import dataclass

RES_W, RES_H = 224, 288          # 3:4 vertical CRT aspect
ORIGIN_X, ORIGIN_Y = 0, 0        # top-left origin

# 16-color palette index (PROM-style color lookup table).
PALETTE = ["#000000", "#0000AA", "#00AA00", "#00AAAA",
           "#AA0000", "#AA00AA", "#AA5500", "#AAAAAAAA",
           "#000000", "#0000FF", "#00FF00", "#00FFFF",
           "#FF0000", "#FF00FF", "#FFFF00", "FFFFFF"]

STAR_COLORS = ["#FFFF00", "#00FFFF", "FFFFFF"]     # yellow / cyan / white blink


@dataclass
class Display:
    """224x288 framebuffer with a 16-color palette."""

    width: int = RES_W
    height: int = RES_H
    palette: list[str] = None
    _pixels: list[int] = None

    def __post_init__(self):
        self.palette = PALETTE if self.palette is None else self.palette
        self._pixels = [0] * (self.width * self.height)

    def set_pixel(self, x: int, y: int, color_index: int):
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[y * self.width + x] = color_index & 0x0F

    def pixel(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._pixels[y * self.width + x]
        return 0

    def color(self, x: int, y: int) -> str:
        return self.palette[self.pixel(x, y)]


class StarfieldLayer:
    """A single scrolling star layer at a fixed px/frame rate."""

    def __init__(self, rate: float, size: int, color_idx: int):
        self.rate = rate
        self.size = size
        self.color_idx = color_idx
        self.stars = [[(i % size) % 224, (i * 7) % 288] for i in range(size)]

    def step(self, blink: int):
        """Advance rows downward; wrap at the bottom. Blink on every 3rd frame."""
        for s in self.stars:
            s[1] += int(self.rate)
            if s[1] >= 288:
                s[1] -= 288
                s[0] = (s[0] + 1) % 224
        # blink: alternate the layer's color through the palette on cycle
        self.color_idx = blink % len(STAR_COLORS)


class Starfield:
    """Three star layers: fast (2px), medium (1px), slow (0.5px)."""

    def __init__(self):
        self.layers = [
            StarfieldLayer(2.0, 40, 0),   # fast
            StarfieldLayer(1.0, 24, 1),   # medium
            StarfieldLayer(0.5, 12, 2),   # slow
        ]

    def step(self, frame: int):
        for layer in self.layers:
            layer.step(frame)

class TwinklingStarfield:
    """A twinkling star backdrop (ihalseide/Galaga style).

    Each frame, stars shimmer by toggling brightness between a dim and a bright
    colour, and drift slowly downward so the backdrop reads as living space.
    ``step(dt)`` advances the shimmer by a wall-clock delta and ``draw`` paints
    the layers onto a surface at a per-pixel scale.
    """

    # dim/bright colour pairs (r, g, b) per layer; [0]=dim, [1]=bright
    _SWITCHES = [
        ((30, 30, 60), (200, 200, 255)),
        ((20, 60, 60), (120, 255, 255)),
        ((60, 60, 30), (255, 255, 200)),
    ]

    def __init__(self, width: int = RES_W, height: int = RES_H, layers: int = 3):
        import random
        self.w = width
        self.h = height
        rng = random.Random(42)
        self.layers = []
        for i in range(layers):
            count = 40 - i * 8
            stars = []
            for k in range(count):
                stars.append([rng.randrange(width), rng.randrange(height)])
            self.layers.append(stars)
        self._t = 0

    def step(self, dt: float):
        """Advance the shimmer by the wall-clock delta (min 1 frame tick)."""
        self._t += max(1.0, dt)

    def draw(self, surface, scale: float):
        """Paint the twinkling backdrop at the given per-pixel scale."""
        import pygame
        t = self._t
        for li, layer in enumerate(self.layers):
            dim, bright = self._SWITCHES[li]
            bright_on = int(t // 120) % 2 == 0
            col = bright if bright_on else dim
            for x, y in layer:
                px = int(x * scale) % surface.get_width()
                py = int(y * scale) % surface.get_height()
                surface.set_at((px, py), col)
