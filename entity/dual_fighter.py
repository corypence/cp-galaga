"""T-10 · Dual fighter (MMA-6058, covers R7).

When a second fighter docks (from a tractor-beam capture + release), the player
becomes the dual fighter: two ships side by side and up to 4 missiles on screen.
"""
from __future__ import annotations
from dataclasses import dataclass, field

DUAL_MAX_MISSILES = 4


@dataclass
class DualFighter:
    """Two docked ships with a doubled weapon capacity."""

    slots: int = 2
    _missiles: list = field(default_factory=list)
    docked: bool = False

    def dock(self):
        self.docked = True
        self.slots = 2

    def undock(self):
        self.docked = False

    def fire(self) -> bool:
        """Fire one missile; dual mode caps the screen at DUAL_MAX_MISSILES."""
        if self.docked and len(self._missiles) >= DUAL_MAX_MISSILES:
            return False
        if not self.docked and len(self._missiles) >= 2:
            return False
        self._missiles.append(0)
        return True

    def active_missiles(self) -> int:
        return len(self._missiles)
