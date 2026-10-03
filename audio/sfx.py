"""T-04 · Audio architecture (MMA-6052, covers R10).

Five audio tracks for Galaga: intro, fire, enemy explosion, player explosion and
tractor beam. Tracks are enabled/disabled per subsystem trigger so the game loop can
emit audio events without a concrete sound backend attached.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto


class Track(Enum):
    INTRO = auto()
    FIRE = auto()
    EXPLOSION_EN = auto()     # enemy explosion
    EXPLOSION_PL = auto()     # player explosion
    TRACTOR = auto()


@dataclass
class AudioBus:
    """Route triggers to named tracks; tracks play enabled/disabled."""

    tracks: dict[str, Track] = None
    enabled: set[Track] = None
    _played: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.tracks = {
            "intro": Track.INTRO,
            "fire": Track.FIRE,
            "enemy_explosion": Track.EXPLOSION_EN,
            "player_explosion": Track.EXPLOSION_PL,
            "tractor": Track.TRACTOR,
        }
        self.enabled = set(self.tracks.values())

    def enable(self, track: Track, on: bool = True):
        if on:
            self.enabled.add(track)
        elif track in self.enabled:
            self.enabled.discard(track)

    def emit(self, event: str):
        """Fire an audio trigger mapped to a track. No-op when disabled."""
        if event not in self.tracks:
            return
        track = self.tracks[event]
        if track in self.enabled:
            self._played.append(event)
