"""T-13 · Particle explosions (MMA-6061, covers R8).

A pooled pool of short-lived sprites that expand + fade in the color of the killed enemy
(Galaga5 Particle.js). Collision emits a burst; each particle carries a velocity, a lifetime,
and a per-frame alpha decay.
"""
from __future__ import annotations
import random


class Particle:
    def __init__(self, x, y, color, vx=None, vy=None, lifetime=30):
        self.x = float(x)
        self.y = float(y)
        self.color = color
        self.vx = vx if vx is not None else random.uniform(-1.5, 1.5)
        self.vy = vy if vy is not None else random.uniform(-1.5, 1.5)
        self.life = float(lifetime)
        self.max_life = self.life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.05  # slight gravity
        self.life -= 1.0

    @property
    def alive(self):
        return self.life > 0.0

    @property
    def alpha(self):
        return max(0.0, min(1.0, self.life / self.max_life))


class ParticleSystem:
    """Pooled burst emitter. Spawn in a color; particles fade over their lifetime."""

    def __init__(self, capacity=128):
        self.capacity = capacity
        self._pool = [None] * capacity
        self._free = list(range(capacity))

    def spawn_burst(self, x, y, color, count=12):
        n = min(count, len(self._free))
        for _ in range(n):
            idx = self._free.pop()
            self._pool[idx] = Particle(x, y, color, lifetime=random.uniform(18, 34))

    def update(self):
        for i, p in enumerate(self._pool):
            if p is not None:
                p.update()
                if not p.alive:
                    self._free.append(i)
                    self._pool[i] = None
