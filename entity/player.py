"""T-06 · Player fighter (MMA-6054, covers R6).

The player fighter: 16x16 bounding box, horizontal-only motion along the baseline
Y=260, X clamped between 16 and 208, base velocity 2 px/frame (120 px/s), capped at
2 missiles on screen, each missile travelling upward at 6 px/frame.
"""
from __future__ import annotations
from dataclasses import dataclass, field


# Hardware constraints from the spec.
PLAYER_SIZE = 16
BASELINE_Y = 260
MIN_X, MAX_X = 16, 208
BASE_VEL = 2          # px/frame
MAX_MISSILES = 2
MISSILE_VEL = 6       # px/frame (upward, so negative Y)


@dataclass
class Missile:
    x: float
    y: float


@dataclass
class Player:
    x: float = (MIN_X + MAX_X) // 2
    y: float = BASELINE_Y

    _missiles: list[Missile] = field(default_factory=list)
    _dir: int = 0          # -1 left, +1 right, 0 idle

    def move(self, direction: int):
        """Clamp horizontal motion to the playfield along the baseline."""
        self._dir = max(-1, min(1, direction))
        self.x = self._clamp(self.x + self._dir * BASE_VEL)

    def _clamp(self, value: float) -> float:
        return float(max(MIN_X, min(MAX_X, value)))

    def fire(self) -> Missile | None:
        """Launch a missile upward; capped at MAX_MISSILES on screen."""
        if len(self._missiles) >= MAX_MISSILES:
            return None
        m = Missile(x=self.x + PLAYER_SIZE / 2, y=self.y)
        self._missiles.append(m)
        return m

    def step(self):
        """Advance missiles upward; drop those that leave the top of the screen."""
        kept = []
        for m in self._missiles:
            m.y -= MISSILE_VEL
            if m.y > 0:
                kept.append(m)
        self._missiles = kept

    def active_missiles(self) -> int:
        return len(self._missiles)
