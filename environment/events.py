import time

class Incident:
    """
    Represents an incident on an edge (u, v) of the graph.
    Stores its severity and time-to-live (TTL) until it disappears.
    """

    def __init__(self, edge, severity: float = 1.0, ttl: float = 30.0):
        self.edge = edge                # Example: ("A", "B")
        self.severity = max(severity, 0.0)
        self.expires_at = time.time() + ttl

    def is_active(self) -> bool:
        """Returns True if the incident has not yet expired."""
        return time.time() < self.expires_at


class EventManager:
    """
    Manages all active incidents in the city.
    Allows creating, checking, and automatically removing expired ones.
    """

    def __init__(self):
        # Dictionary storing edges and their corresponding incidents
        self.incidents = {}

    def spawn_incident(self, edge, severity: float = 1.0, ttl: float = 30.0):
        """
        Creates a new incident on edge (u, v) with the given severity and duration.
        """
        self.incidents[edge] = Incident(edge, severity, ttl)

    def clear_expired(self):
        """Removes all incidents whose TTL has expired."""
        for edge in list(self.incidents.keys()):
            if not self.incidents[edge].is_active():
                del self.incidents[edge]

    def is_blocked(self, edge) -> bool:
        """
        Returns True if the edge is blocked (severity >= 1.0).
        """
        self.clear_expired()
        inc = self.incidents.get(edge)
        return bool(inc and inc.severity >= 1.0)

    def penalty(self, edge) -> float:
        """
        Returns an additional penalty cost for a route.
        (0.0 if there is no incident or it has already expired.)
        """
        self.clear_expired()
        inc = self.incidents.get(edge)
        return inc.severity if inc else 0.0