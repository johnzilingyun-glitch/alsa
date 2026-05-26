"""Metrics collection for system observability.

Records time-series metrics with tags for filtering and aggregation.
In production, this would emit to Prometheus/StatsD; here it's in-memory.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MetricType(str, Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class MetricPoint:
    name: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MetricsCollector:
    """In-memory metrics collector with tag-based filtering."""

    def __init__(self):
        self._points: List[MetricPoint] = []

    def record(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a metric data point."""
        self._points.append(MetricPoint(name=name, value=value, tags=tags or {}))

    def get_stats(self, name: str, filter_tags: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Get aggregated stats (count, avg, min, max) for a metric."""
        points = [p for p in self._points if p.name == name]
        if filter_tags:
            points = [p for p in points if all(p.tags.get(k) == v for k, v in filter_tags.items())]

        if not points:
            return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}

        values = [p.value for p in points]
        return {
            "count": len(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def get_rate(self, name: str, success_tag: str, success_value: str) -> float:
        """Calculate the rate of points where tag matches success_value."""
        points = [p for p in self._points if p.name == name]
        if not points:
            return 0.0
        matched = sum(1 for p in points if p.tags.get(success_tag) == success_value)
        return matched / len(points)
