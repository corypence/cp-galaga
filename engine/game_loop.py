"""T-01 · Core game loop (MMA-6049, covers R1).

Fixed-timestep 60 FPS game loop for a 1981 Galaga arcade simulator.

Invariant: fixed dt = 1/60 s (~16.67 ms) per tick so physics / AI stay deterministic
across machines and don't drift between runs. Execution order per tick follows the
spec's tick order:
    1. Process Input Buffer
    2. Update Game State (player, enemies, starfield)
    3. Resolve Collisions (spatial-partitioning grid lookup)
    4. Emit Audio Triggers
    5. Render Frame
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field

FIXED_DT = 1.0 / 60.0      # seconds — 60 FPS, fixed timestep (~16.67 ms)
TARGET_FPS = 60
FRAME_BUDGET_S = FIXED_DT

# The ordered tick steps the spec calls for.
_TICK_ORDER = ("input", "update", "collision", "audio", "render")


@dataclass
class GameLoop:
    """Deterministic fixed-timestep loop over a subsystems object.

    Runs ``target_fps`` simulation steps per wall-clock second and consumes a
    subsystems object exposing the five ordered hooks (``input``, ``update``,
    ``collision``, ``audio``, ``render``). Each hook receives the fixed dt.
    """

    target_fps: int = TARGET_FPS
    subsystems: object = None

    _accumulator: float = field(default=0.0, init=False)
    _last: float | None = field(default=None, init=False)
    running: bool = field(default=True, init=False)
    steps: int = field(default=0, init=False)

    def __post_init__(self):
        self._accumulator = 0.0
        self._last = None
        self.steps = 0

    def start(self):
        """Run until ``subsystems.stop()`` returns True. Blocks the caller thread."""
        self._last = time.perf_counter()
        while self.running:
            self._step_frame()

    def _step_frame(self):
        now = time.perf_counter()
        if self._last is None:
            self._last = now
            return
        frame_s = max(0.0, now - self._last)
        self._last = now
        # Cap the accumulator so a stalled frame can't trigger a spiral-of-death.
        self._accumulator += min(frame_s, FRAME_BUDGET_S * 10)
        while self._accumulator >= FRAME_BUDGET_S:
            self._accumulator -= FRAME_BUDGET_S
            self._run_tick()

    def _run_tick(self):
        """Advance one fixed step in the spec's tick order."""
        subs = self.subsystems
        if subs is None:
            return
        for step in _TICK_ORDER:
            handler = getattr(subs, step, None)
            if callable(handler):
                handler(FIXED_DT)
        self.steps += 1

    def stop(self):
        self.running = False


def main():
    loop = GameLoop()
    loop.start()
    print(f"loop ran {loop.steps} fixed steps at {TARGET_FPS} fps")


if __name__ == "__main__":
    main()
