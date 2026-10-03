"""T-09 · Stage structuring (MMA-6057, covers R5).

Normal stages run alternating enemy-formation waves; challenging stages (3, 7, 11, 15
and every 4th stage after 15) fly enemies across the screen in fixed curves without a
stationary grid, exiting without attacking.
"""
from __future__ import annotations


def is_challenging(stage: int) -> bool:
    """Challenging on 3,7,11,15 and every 4th stage subsequently."""
    if stage < 3:
        return False
    if stage in (3, 7, 11, 15):
        return True
    return stage > 15 and (stage - 15) % 4 == 0


def stage_kind(stage: int) -> str:
    return "challenging" if is_challenging(stage) else "normal"


def make_wave(stage: int, formation: object):
    """Build the enemy wave for a stage.

    Normal stages place an alternating formation wave; challenging stages emit a
    free-flying curve wave with no grid.
    """
    kind = stage_kind(stage)
    if kind == "challenging":
        return {"kind": kind, "wave": "curve", "stage": stage}
    return {"kind": kind, "wave": "formation", "stage": stage, "grid": formation}


def main():
    for s in range(1, 9):
        print(f"stage {s}: {stage_kind(s)}")


if __name__ == "__main__":
    main()
