"""Bounded, process-local telemetry: no database writes and no user/song IDs."""
from collections import Counter, deque
from datetime import datetime, timezone
from threading import Lock


class RecommendationMetrics:
    OUTCOMES = ('content_based', 'collaborative_filtering', 'popular', 'cold_start', 'error')

    def __init__(self, window_size: int = 100):
        if window_size < 1:
            raise ValueError('window_size must be positive')
        self._events = deque(maxlen=window_size)
        self._lock = Lock()
        self._started_at = datetime.now(timezone.utc).isoformat()

    def record(self, source: str, priority: str, fallback_reason: str | None = None):
        if source not in self.OUTCOMES:
            raise ValueError('Unknown recommendation outcome')
        with self._lock:
            self._events.append((datetime.now(timezone.utc).isoformat(), source, priority, fallback_reason))

    def snapshot(self) -> dict:
        with self._lock:
            events = list(self._events)
        total = len(events)
        counts = Counter(event[1] for event in events)
        reasons = Counter(event[3] or 'unknown' for event in events if event[1] in ('popular', 'cold_start'))
        return {
            'window_type': 'last_requests',
            'window_size': self._events.maxlen,
            'observed_requests': total,
            'scope': 'process_local',
            'resets_on_restart': True,
            'tracking_started_at': self._started_at,
            'oldest_request_at': events[0][0] if events else None,
            'newest_request_at': events[-1][0] if events else None,
            'distribution': {
                source: {'count': counts[source], 'percent': round(100 * counts[source] / total, 2) if total else 0.0}
                for source in self.OUTCOMES
            },
            'fallback_reasons': dict(reasons),
            'priority_counts': dict(Counter(event[2] for event in events)),
        }


recommendation_metrics = RecommendationMetrics()
