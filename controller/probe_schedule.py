"""Adaptive scheduling intervals for SDN health probes."""


class AdaptiveProbeSchedule:
    """Choose probe frequency based on recent results and path health.

    Normal operation:       1000 ms
    Uncertain/degraded:      250 ms
    After a probe failure:   100 ms until three consecutive successes
    Recovery period:         250 ms for two seconds
    """

    STABLE_NS = 1_000_000_000
    UNCERTAIN_NS = 250_000_000
    FAILURE_NS = 100_000_000
    RECOVERY_NS = 250_000_000
    RECOVERY_HOLD_NS = 2_000_000_000
    SUCCESS_THRESHOLD = 3

    def __init__(self):
        self.degraded = False
        self.consecutive_successes = 0
        self.recovery_started_ns = None
        self.failure_seen = False

    def record_result(self, success, now_ns):
        """Record a completed probe result using monotonic nanoseconds."""
        if not success:
            self.failure_seen = True
            self.consecutive_successes = 0
            self.recovery_started_ns = None
            return

        self.consecutive_successes += 1

        if (
            self.failure_seen
            and self.consecutive_successes >= self.SUCCESS_THRESHOLD
            and self.recovery_started_ns is None
        ):
            self.recovery_started_ns = now_ns

    def set_degraded(self, degraded, now_ns):
        """Mark whether current path health is uncertain or degraded."""
        degraded = bool(degraded)

        if degraded:
            self.degraded = True
            self.recovery_started_ns = None
        elif self.degraded:
            self.degraded = False
            self.recovery_started_ns = now_ns

    def interval_ns(self, now_ns):
        """Return the appropriate interval in nanoseconds."""
        if self.failure_seen and self.consecutive_successes < self.SUCCESS_THRESHOLD:
            return self.FAILURE_NS

        if self.degraded:
            return self.UNCERTAIN_NS

        if self.recovery_started_ns is not None:
            if now_ns - self.recovery_started_ns < self.RECOVERY_HOLD_NS:
                return self.RECOVERY_NS

            self.failure_seen = False
            self.recovery_started_ns = None

        return self.STABLE_NS

    def interval_seconds(self, now_ns):
        """Return the interval in seconds for scheduler integrations."""
        return self.interval_ns(now_ns) / 1_000_000_000
