import time
from typing import Tuple, Dict, List


class Incident:
    """
    Represents an incident (e.g. roadblock, accident) on an edge (u, v) of the city graph.
    Stores its severity and time-to-live (TTL) until it disappears.
    """

    def __init__(self, edge: Tuple, severity: float = 1.0, ttl: float = 30.0):
        self.edge = edge  # (u, v)
        self.severity = max(severity, 0.0)
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl

    def is_active(self) -> bool:
        """Return True if the incident has not yet expired."""
        return time.time() < self.expires_at

    def remaining_time(self) -> float:
        """Return remaining lifetime in seconds."""
        return max(0.0, self.expires_at - time.time())

    def __repr__(self):
        return (
            f"Incident(edge={self.edge}, severity={self.severity}, "
            f"expires_in={self.remaining_time():.1f}s)"
        )


class EventManager:
    """
    Manages all active incidents in the city.
    Provides utilities for creating, checking, and clearing expired incidents.
    """

    def __init__(self):
        self.incidents: Dict[Tuple, Incident] = {}

    # -------------------------
    # Utility
    # -------------------------
    def _normalize_edge(self, edge: Tuple) -> Tuple:
        """Ensure edge order consistency (undirected graph)."""
        u, v = edge
        return tuple(sorted((u, v)))

    # -------------------------
    # Core functionality
    # -------------------------
    def spawn_incident(self, edge: Tuple, severity: float = 1.0, ttl: float = 30.0):
        """
        Create or update an incident on an edge.
        If already active, increase its severity and refresh TTL.
        """
        edge = self._normalize_edge(edge)
        if edge in self.incidents:
            existing = self.incidents[edge]
            existing.severity = max(existing.severity, severity)
            existing.expires_at = time.time() + ttl
            print(
                f"⚠️  Updated incident on {edge}: "
                f"severity={existing.severity}, ttl={ttl}s"
            )
        else:
            self.incidents[edge] = Incident(edge, severity, ttl)
            print(f"🚧 New incident on {edge}: severity={severity}, ttl={ttl}s")

    def clear_expired(self):
        """Remove expired incidents."""
        for edge in list(self.incidents.keys()):
            if not self.incidents[edge].is_active():
                print(f"✅ Incident on {edge} resolved (expired).")
                del self.incidents[edge]

    def active_incidents(self) -> List[Incident]:
        """Return a list of currently active incidents."""
        self.clear_expired()
        return list(self.incidents.values())

    # -------------------------
    # Query methods
    # -------------------------
    def is_blocked(self, edge: Tuple, threshold: float = 3.0) -> bool:
        """
        Return True if the edge is considered blocked (severity >= threshold).
        """
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return bool(inc and inc.severity >= threshold)

    def penalty(self, edge: Tuple) -> float:
        """
        Return the penalty weight for routing.
        Higher severity means higher traversal cost.
        """
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return inc.severity if inc else 0.0

    def __repr__(self):
        self.clear_expired()
        if not self.incidents:
            return "EventManager(0 active incidents)"
        return f"EventManager({len(self.incidents)} active: {self.active_incidents()})"