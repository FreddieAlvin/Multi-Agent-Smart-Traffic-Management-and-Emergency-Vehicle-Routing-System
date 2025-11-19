# environment/events.py
import time
from typing import Tuple, Dict, List, Optional


class Incident:
    """Represents an incident (roadblock/accident) on an edge."""

    def __init__(self, edge: Tuple, severity: float = 1.0, ttl: float = 30.0):
        self.edge = tuple(edge)
        self.severity = max(severity, 0.0)
        self.created_at = time.time()
        self.expires_at = self.created_at + float(ttl)

    def is_active(self) -> bool:
        return time.time() < self.expires_at

    def remaining_time(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def __repr__(self):
        return f"Incident(edge={self.edge}, severity={self.severity}, expires_in={self.remaining_time():.1f}s)"


class EventManager:
    """Manages incidents (roadblocks) locally."""

    def __init__(self):
        self.incidents: Dict[Tuple, Incident] = {}

    def _normalize_edge(self, edge: Tuple) -> Tuple:
        u, v = edge
        u, v = tuple(u), tuple(v)
        return (u, v) if u <= v else (v, u)

    def spawn_incident(self, edge: Tuple, severity: float = 1.0, ttl: float = 30.0):
        edge = self._normalize_edge(edge)
        if edge in self.incidents and self.incidents[edge].is_active():
            inc = self.incidents[edge]
            inc.severity = max(inc.severity, severity)
            inc.expires_at = time.time() + ttl
        else:
            self.incidents[edge] = Incident(edge, severity=severity, ttl=ttl)

    def spawn_temporary_block(self, edge: Tuple, ttl: float = 8.0):
        self.spawn_incident(edge, severity=10.0, ttl=ttl)

    def clear_expired(self):
        for edge in list(self.incidents.keys()):
            if not self.incidents[edge].is_active():
                del self.incidents[edge]

    def is_blocked(self, edge: Tuple, threshold: float = 3.0) -> bool:
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return bool(inc and inc.severity >= threshold)

    def penalty(self, edge: Tuple) -> float:
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return float(inc.severity) if inc else 0.0

    def blocked_edges(self, threshold: float = 3.0) -> List[Tuple]:
        self.clear_expired()
        return [e for e, inc in self.incidents.items() if inc.severity >= threshold]

    def blocked_nodes(self) -> List[Tuple]:
        nodes = set()
        for u, v in self.blocked_edges():
            nodes.add(u)
            nodes.add(v)
        return list(nodes)

    def __repr__(self):
        self.clear_expired()
        return f"EventManager({len(self.incidents)} active: {list(self.incidents.values())})"
