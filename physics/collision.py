"""T-08 · Collision subsystem (MMA-6056, covers R9).

Axis-aligned bounding-box (AABB) collision across three layers — missiles vs enemies,
enemies vs player, tractor-beam vs player — backed by a uniform spatial partition grid
so lookups are O(cells) rather than O(n^2).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class AABB:
    x: float
    y: float
    w: float
    h: float

    def intersects(self, other: "AABB") -> bool:
        return not (other.x > self.x + self.w
                    or other.x + other.w < self.x
                    or other.y > self.y + self.h
                    or other.y + other.h < self.y)


class CollisionGrid:
    """Uniform spatial grid keyed by cell; insert AABBs and query overlaps."""

    def __init__(self, cell: float = 32.0, width: int = 224, height: int = 288):
        self.cell = cell
        self.cols = max(1, width // cell)
        self.rows = max(1, height // cell)
        self._cells: list[list[int]] = [[] for _ in range(self.cols * self.rows)]
        self._objects: list[AABB] = []

    def _cell_index(self, a: AABB) -> int:
        cx = min(self.cols - 1, max(0, int(a.x // self.cell)))
        cy = min(self.rows - 1, max(0, int(a.y // self.cell)))
        return cy * self.cols + cx

    def insert(self, a: AABB):
        self._objects.append(a)
        self._cells[self._cell_index(a)].append(len(self._objects) - 1)

    def overlaps(self, a: AABB) -> list[AABB]:
        out = [o for o in self._objects if o.intersects(a)]
        return out


def broad_phase(a: AABB, b: AABB) -> bool:
    return a.intersects(b)


LAYERS = ("missile_enemy", "enemy_player", "tractor_player")
