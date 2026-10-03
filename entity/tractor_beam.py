"""T-11 · Tractor beam (MMA-6059, covers R7).

Boss Galaga emits a tractor beam that captures the player's fighter (player becomes an
enemy entity). Destroying that boss while it dives releases the captured ship, which
then docks adjacently to the current player ship.
"""
from __future__ import annotations
from enum import Enum, auto


class CaptureState(Enum):
    FREE = auto()
    CAPTURED = auto()
    RELEASED = auto()


@dataclass
class TractorBeam:
    boss_dive: bool = False
    capture_active: bool = False

    def grab(self):
        self.capture_active = True

    def release(self):
        self.capture_active = False

    def try_capture(self, player_state: CaptureState) -> CaptureState:
        """Begin capture while the boss dives and holds the player."""
        if self.boss_dive:
            self.grab()
            return CaptureState.CAPTURED
        return player_state

    def release_captured(self, state: CaptureState) -> CaptureState:
        """Releasing on a boss dive returns the player to FREE (then docks)."""
        if self.boss_dive:
            self.release()
            return CaptureState.RELEASED
        return state


def main():
    beam = TractorBeam()
    print(beam.try_capture(CaptureState.FREE))


if __name__ == "__main__":
    main()
