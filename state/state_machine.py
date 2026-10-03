"""T-05 · Game state machine (MMA-6053, covers R4).

Rigid six-state machine for Galaga. Each state implements enter/update/exit so the
loop can transition deterministically (boot diagnostic -> attract -> stage start ->
gameplay -> challenging bonus -> game over).
"""
from __future__ import annotations
from enum import Enum, auto
from typing import Callable


class State(Enum):
    BOOT_DIAGNOSTIC = auto()
    ATTRACT_MODE = auto()
    STAGE_START = auto()          # freeze "STAGE X" + intro melody
    GAMEPLAY = auto()
    CHALLENGING_STAGE = auto()    # bonus round counter
    GAME_OVER = auto()


class GameStateMachine:
    """Minimal state machine: current state plus optional per-state hooks."""

    def __init__(self):
        self.current = State.BOOT_DIAGNOSTIC
        self._hooks: dict[State, dict] = {}

    def register(self, state: State, hooks: dict):
        self._hooks[state] = hooks

    def transition(self, state: State):
        self._fire("exit", self.current)
        self.current = state
        self._fire("enter", state)

    def update(self, **ctx):
        if self.current not in self._hooks:
            return
        handler = self._hooks[self.current].get("update")
        if callable(handler):
            return handler(**ctx)

    def _fire(self, kind: str, state: State):
        hook = self._hooks.get(state, {}).get(kind)
        if callable(hook):
            hook()


# Convenience: the six states, ordered as a boot-to-over progression.
STATES = list(State)


def main():
    sm = GameStateMachine()
    print(f"boot: {sm.current.name}")
    for nxt in [State.ATTRACT_MODE, State.STAGE_START, State.GAMEPLAY,
                State.CHALLENGING_STAGE, State.GAME_OVER]:
        sm.transition(nxt)
    print(f"final: {sm.current.name}")


if __name__ == "__main__":
    main()
