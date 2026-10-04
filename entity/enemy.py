"""T-07 · Enemy matrix (MMA-6055, covers R8).

Enemy archetypes — Zako (grunt), Goei (elite) and Boss Galaga — with formation grid
placement and a dive behavior. Supports a 40-enemy formation grid and a simple dive
state machine (dip -> retreat / dive -> attack -> return).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto


class EnemyType(Enum):
    ZAKO = auto()
    GOEI = auto()
    BOSS = auto()


class EnemyState(Enum):
    FORMATION = auto()
    DIPE = auto()
    ATTACK = auto()
    RETURN = auto()


@dataclass
class Enemy:
    etype: EnemyType
    x: float
    y: float
    state: EnemyState = EnemyState.FORMATION
    slot: int = 0
    col: int = 0
    row: int = 0
    cooldown: int = 0
    alive: bool = True

    def shot_ready(self, elapsed: int) -> bool:
        """True when the enemy's shot cooldown has expired (elapsed >= cooldown)."""
        return elapsed >= self.cooldown

    def bee_shot(self, manager) -> None:
        """Fire a single downward bee-shot projectile via the BeeShotManager."""
        manager.fire(self.x + 9.0, self.y + 16.0, 0.0, 1.0)

    def enter_position(self, entrance, fx: float, fy: float, frame: int
                       ) -> tuple[float, float, bool]:
        """Return the entrance-path position (x, y, done) for this enemy at ``frame``.

        Delegates to the shared Entrance choreography (T-17): the enemy sweeps from its
        pattern entry point to its formation-center slot (fx, fy), and ``done`` becomes True
        once the sweep reaches the slot so the renderer returns it to formation sway.
        """
        slot = self.slot
        return entrance.position(slot, fx, fy, frame)

    def enter(self) -> None:
        """Snap to the formation slot position (called once entrance completes)."""
        gap_x = 224.0 / 10
        gap_y = 120.0 / 4
        self.x = gap_x * (self.col + 0.5)
        self.y = gap_y * (self.row + 0.5)

    def enter_position(self, entrance, fx: float, fy: float, frame: int
                       ) -> tuple[float, float, bool]:
        """Return the entrance-path position (x, y, done) for this enemy at ``frame``.

        Delegates to the shared Entrance choreography (T-17): the enemy sweeps from its
        pattern entry point to its formation-center slot (fx, fy), and ``done`` becomes True
        once the sweep reaches the slot so the renderer returns it to formation sway.
        """
        slot = getattr(self, "slot", 0)
        return entrance.position(slot, fx, fy, frame)




# Per-archetype logical pixel size (spec §3-5): the Boss renders larger than a Bee.
ARCHETYPE_LOGICAL_SIZE = {
    EnemyType.ZAKO: (18, 18),
    EnemyType.GOEI: (20, 20),
    EnemyType.BOSS: (24, 24),
}


class FormationGrid:
    """Arrange enemies into a formation grid of up to 40 slots."""

    def __init__(self, cols: int = 10, rows: int = 4):
        self.cols = cols
        self.rows = rows
        self.enemies: list[Enemy | None] = [None] * (cols * rows)

    def place(self, index: int, enemy: Enemy):
        if 0 <= index < len(self.enemies):
            self.enemies[index] = enemy

    def size(self) -> int:
        return sum(1 for e in self.enemies if e is not None)

    def slot_pos(self, index: int) -> tuple[float, float]:
        col, row = index % self.cols, index // self.cols
        return col * 20.0, row * 20.0

    def slot_center(self, index: int) -> tuple[float, float]:
        """Centre of a slot within a 224-wide playfield, upper half (formation area)."""
        col, row = index % self.cols, index // self.cols
        gap_x = 224.0 / self.cols
        gap_y = 120.0 / self.rows
        return (gap_x * (col + 0.5), gap_y * (row + 0.5))




class FormationAnchor:
    """Formation grid anchor: the pivot (x, y) around which all columns are laid out.

    position(slot, fmt, frame) returns the playfield coordinate for a grid slot. Columns are
    spaced around x (column 0 to the left, the middle column near x); rows stack downward from y.
    step() advances the internal frame counter consumed by the fmt motion mode.
    """

    def __init__(self, x: float = 112.0, y: float = 44.0, cols: int = 10, rows: int = 4,
                 col_gap: float = 22.4, row_gap: float = 28.0):
        self.x = float(x)
        self.y = float(y)
        self.cols = cols
        self.rows = rows
        self.col_gap = col_gap
        self.row_gap = row_gap
        self._frame = 0

    def step(self):
        self._frame += 1

    def position(self, slot: int, fmt: str = "sine", frame: int = 0):
        col, row = slot % self.cols, slot // self.cols
        cx = self.x + (col - (self.cols - 1) / 2.0) * self.col_gap
        cy = self.y + row * self.row_gap
        if fmt == "shuffle":
            jx = ((slot * 7 + frame) % 17 - 8) * 2.0
            jy = ((slot * 13 + frame) % 11 - 5) * 2.0
            cx += jx
            cy += jy
        return cx, cy


class BeeShotManager:
    """Bee-fired shot manager: a capped list of on-screen bee projectiles.

    Tracks an elapsed frame counter (used by callers to schedule per-enemy cooldowns) and
    exposes active as an iterable of (x, y) shot positions for the renderer to draw.
    """

    def __init__(self, cap: int = 8):
        self.cap = cap
        self.elapsed = 0
        self._shots = []

    def fire(self, x, y, vx=0.0, vy=1.0):
        if len(self._shots) >= self.cap:
            return
        self._shots.append([float(x), float(y), float(vx), float(vy), 1.0])

    def update(self):
        kept = []
        for s in self._shots:
            s[1] += s[3]
            s[0] += s[2]
            if 0 <= s[1] <= 288 and 0 <= s[0] <= 224:
                kept.append(s)
        self._shots = kept

    @property
    def active(self):
        return [(s[0], s[1]) for s in self._shots]

    def can_fire(self) -> bool:
        """True when there is a free shot slot on screen."""
        return len(self._shots) < self.cap

def main():
    grid = FormationGrid()
    for i in range(grid.size() if hasattr(grid, "size") else 0):
        pass
    print(f"galaga formation grid {grid.cols}x{grid.rows}")


if __name__ == "__main__":
    main()
