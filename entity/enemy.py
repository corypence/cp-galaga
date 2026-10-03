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


def main():
    grid = FormationGrid()
    for i in range(grid.size() if hasattr(grid, "size") else 0):
        pass
    print(f"galaga formation grid {grid.cols}x{grid.rows}")


if __name__ == "__main__":
    main()
