"""T-02 · Input abstraction (MMA-6050, covers R2).

Keyboard / virtual-controller input abstraction for Galaga. Maps physical keys to
named player actions, exposes a ring-buffer of input events so the game loop can
drain and replay them deterministically, and provides a virtual-controller matrix
for scripted / automated input.
"""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


class Action(Enum):
    """Player actions the input layer resolves into."""
    LEFT = auto()
    RIGHT = auto()
    FIRE = auto()
    COIN = auto()
    START = auto()
    UP = auto()
    DOWN = auto()


# Physical keys -> action. Arrows + WASD, J/K/L for fire, Enter for start, Space coin.
_KEY_TO_ACTION = {
    "left": Action.LEFT, "a": Action.LEFT,
    "right": Action.RIGHT, "d": Action.RIGHT,
    "up": Action.UP, "w": Action.UP,
    "down": Action.DOWN, "s": Action.DOWN,
    "space": Action.COIN, " ": Action.COIN,
    "enter": Action.START,
    "j": Action.FIRE, "k": Action.FIRE, "l": Action.FIRE,
}


@dataclass
class InputMap:
    """Maps keys to actions and lets a player rebind them."""

    keymap: dict[str, Action] = None

    def __post_init__(self):
        self.keymap = dict(_KEY_TO_ACTION)

    def bind(self, key: str, action: Action | str):
        action = action if isinstance(action, Action) else Action(action)
        self.keymap[key] = action

    def action_for(self, key: str) -> Action | None:
        return self.keymap.get(key.lower())


class InputBuffer:
    """Ring buffer of keyed input events consumed by the game loop."""

    def __init__(self, capacity: int = 16):
        self.capacity = capacity
        self._events = deque()

    def push(self, key: str, down: bool):
        action = Action
        self._events.append((key, down))
        while len(self._events) > self.capacity:
            self._events.popleft()

    def drain(self, keymap: InputMap | None = None) -> list[tuple[Action, bool]]:
        """Return pending (action, down) pairs and clear the buffer."""
        out = []
        while self._events:
            key, down = self._events.popleft()
            action = None
            if keymap is not None:
                action = keymap.action_for(key)
            else:
                try:
                    action = Action[key.upper()]
                except KeyError:
                    continue
            if action is not None:
                out.append((action, down))
        return out

    def any_action(self, keymap: InputMap | None = None) -> list[Action]:
        return {a for a, _ in self.drain(keymap)}


class VirtualController:
    """Programmatic input matrix — a grid of buttons for scripted input."""

    def __init__(self, n_buttons: int = 16):
        self.buttons = [False] * n_buttons

    def press(self, index: int, down: bool = True):
        self.buttons[index] = down

    def held(self) -> list[int]:
        return [i for i, b in enumerate(self.buttons) if b]
