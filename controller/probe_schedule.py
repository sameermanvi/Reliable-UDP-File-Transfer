"""Adaptive per-path, per-direction probe scheduling."""
import time


class AdaptiveProbeSchedule:
    def __init__(
        self,
        min_interval=0.1,
        # Leave the 500 ms response deadline inside the tracker's 2 s freshness.
        max_interval=1.5,
        initial_interval=0.25,
        healthy_threshold=0.05,
        degraded_threshold=0.10,
    ):
        if not 0 < min_interval <= initial_interval <= max_interval:
            raise ValueError("Invalid probe interval bounds")
        if not 0 <= healthy_threshold < degraded_threshold:
            raise ValueError("Invalid health thresholds")

        self.min_interval = min_interval
        self.max_interval = max_interval
        self.healthy_threshold = healthy_threshold
        self.degraded_threshold = degraded_threshold
        self.interval = initial_interval
        self.degraded = True
        self.last_result_ns = None

    def set_degraded(self, degraded, now_ns=None):
        """Update health state and optionally record its update time."""
        self.degraded = bool(degraded)
        if now_ns is not None:
            self.last_result_ns = now_ns

    def record_result(self, success, now_ns=None):
        """Record a probe result and adapt the next interval."""
        if now_ns is None:
            now_ns = time.monotonic_ns()
        self.last_result_ns = now_ns

        if success:
            if not self.degraded:
                self.interval = min(self.max_interval, self.interval * 1.25)
        else:
            self.degraded = True
            self.interval = max(self.min_interval, self.interval / 2)

        return self.interval

    def interval_seconds(self, now_ns=None):
        """Return the interval used by the controller's next deadline."""
        if self.degraded:
            return max(self.min_interval, min(self.interval, 0.25))
        return min(self.max_interval, self.interval)
