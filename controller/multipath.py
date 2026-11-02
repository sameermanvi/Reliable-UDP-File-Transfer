"""Multipath scheduling logic for Reliable UDP File Transfer.

Selects a path for each outgoing data packet using weighted scheduling.
This module is independent of OS-Ken so its scheduling logic is testable.
"""

from dataclasses import dataclass
from itertools import cycle
from threading import Lock


@dataclass(frozen=True)
class PathState:
    """Current scheduling state for a network path."""

    name: str
    healthy: bool = True
    weight: int = 1


class MultipathScheduler:
    """Thread-safe weighted scheduler for healthy network paths."""

    def __init__(self, paths=("upper", "lower")):
        if not paths:
            raise ValueError("At least one path is required")

        self._lock = Lock()
        self._paths = {
            name: PathState(name=name)
            for name in paths
        }
        self._schedule = cycle(paths)

    def update_path(self, name, *, healthy=None, weight=None):
        """Update a path's health or scheduling weight."""
        with self._lock:
            if name not in self._paths:
                raise ValueError(f"Unknown path: {name}")

            current = self._paths[name]
            new_weight = current.weight if weight is None else weight

            if new_weight < 1:
                raise ValueError("Path weight must be at least 1")

            self._paths[name] = PathState(
                name=name,
                healthy=current.healthy if healthy is None else healthy,
                weight=new_weight,
            )
            self._rebuild_schedule()

    def _rebuild_schedule(self):
        """Build a weighted cycle from currently healthy paths."""
        entries = []

        for path in self._paths.values():
            if path.healthy:
                entries.extend([path.name] * path.weight)

        self._schedule = cycle(entries)

    def select_path(self):
        """Return the next healthy path, or None if all paths are down."""
        with self._lock:
            if not any(path.healthy for path in self._paths.values()):
                return None

            return next(self._schedule)

    def get_paths(self):
        """Return a snapshot of the configured path states."""
        with self._lock:
            return dict(self._paths)
