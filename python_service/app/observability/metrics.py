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
    """Metrics collector with tag-based filtering, auto-flush, and size cap."""

    MAX_POINTS = 5000

    def __init__(self, db_path="metrics.db"):
        self._points: List[MetricPoint] = []
        self._db_path = db_path

    def record(self, name: str, value: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a metric data point. Auto-flushes when buffer is full."""
        self._points.append(MetricPoint(name=name, value=value, tags=tags or {}))
        if len(self._points) >= self.MAX_POINTS:
            self.flush()

    def flush(self) -> None:
        """Write all pending in-memory points to the SQLite database."""
        if not self._points:
            return
            
        import sqlite3
        import json
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                value REAL,
                tags TEXT,
                timestamp TEXT
            )
        """)
        
        # Insert all points
        for p in self._points:
            tags_json = json.dumps(p.tags)
            ts_str = p.timestamp.isoformat()
            cursor.execute("""
                INSERT INTO metrics_log (name, value, tags, timestamp)
                VALUES (?, ?, ?, ?)
            """, (p.name, p.value, tags_json, ts_str))
            
        conn.commit()
        conn.close()
        
        # Clear points in memory
        self._points.clear()

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
