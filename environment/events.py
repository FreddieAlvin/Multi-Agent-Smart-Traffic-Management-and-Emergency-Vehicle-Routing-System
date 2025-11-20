"""
events.py

Local incident / roadblock management for the grid environment.

This module defines:
- Incident: dataclass that represents a temporary event on an edge.
- EventManager: keeps track of all active incidents and exposes helpers
  to query blocked edges / nodes and penalties for routing.
"""

import time
from dataclasses import dataclass
from typing import Dict, Tuple, List


@dataclass
class Incident:
    """
    Represent a single incident (e.g. accident / roadblock) on an edge.

    Attributes:
        edge:   Normalized edge as a pair of nodes ((x1, y1), (x2, y2)).
        severity:
            Positive value that encodes how "bad" the incident is.
            Large values typically mean the edge should be avoided.
        ttl:
            Time-to-live in seconds. After this time passes, the incident
            is automatically removed.
        created_at:
            Wall-clock time when the incident was created.
        expires_at:
            Wall-clock time when the incident should be considered expired.
    """
    edge: Tuple
    severity: float = 1.0
    ttl: float = 30.0
    created_at: float | None = None
    expires_at: float | None = None

    def __post_init__(self) -> None:
        """Fill in creation / expiration timestamps when not provided."""
        now = time.time()
        if self.created_at is None:
            self.created_at = now
        if self.expires_at is None:
            self.expires_at = now + self.ttl

    def is_active(self) -> bool:
        """
        Check if this incident is still active.

        Returns:
            True if the current time is before the expiration time.
        """
        return time.time() < self.expires_at


class EventManager:
    """
    Manage temporary incidents (roadblocks) on edges of the city graph.

    The manager:
      * stores incidents keyed by normalized edges;
      * automatically removes expired incidents;
      * exposes convenience methods for:
          - checking if an edge is blocked;
          - providing a penalty value for routing;
          - enumerating blocked edges and their endpoints.
    """

    def __init__(self) -> None:
        # key: normalized edge ((x1, y1), (x2, y2))
        # val: Incident instance
        self.incidents: Dict[Tuple, Incident] = {}

    # ---------- internal helpers ----------

    def _normalize_edge(self, edge: Tuple) -> Tuple:
        """
        Normalize an edge so that (u, v) and (v, u) map to the same key.

        Args:
            edge: Tuple of two nodes, each node being a coordinate tuple.

        Returns:
            A tuple (u, v) with u <= v in lexicographic order.
        """
        u, v = edge
        u, v = tuple(u), tuple(v)
        return (u, v) if u <= v else (v, u)

    def clear_expired(self) -> None:
        """
        Remove incidents whose TTL has passed.

        This method is called by most public helpers before returning
        information, so the map stays clean over time.
        """
        now = time.time()
        for edge in list(self.incidents.keys()):
            inc = self.incidents[edge]
            if inc.expires_at <= now or not inc.is_active():
                del self.incidents[edge]

    # ---------- public API used elsewhere ----------

    def spawn_incident(self, edge: Tuple, severity: float = 1.0, ttl: float = 30.0) -> None:
        """
        Create or refresh an incident on a given edge.

        If an incident on that edge already exists and is active, its
        severity and expiration time are updated instead of creating
        a new object.

        Args:
            edge:     Edge where the incident occurs.
            severity: Intensity / importance of the incident.
            ttl:      Time-to-live in seconds.
        """
        edge = self._normalize_edge(edge)
        self.clear_expired()

        if edge in self.incidents and self.incidents[edge].is_active():
            # refresh existing incident
            inc = self.incidents[edge]
            inc.severity = max(inc.severity, severity)
            inc.expires_at = time.time() + ttl
        else:
            self.incidents[edge] = Incident(edge, severity=severity, ttl=ttl)

    def spawn_temporary_block(self, edge: Tuple, ttl: float = 8.0) -> None:
        """
        Convenience: spawn a very severe incident on an edge.

        This is used by the random roadblock generator to create edges
        that should be treated as fully blocked for a short period.

        Args:
            edge: Edge to temporarily block.
            ttl:  Time-to-live in seconds for this block.
        """
        self.spawn_incident(edge, severity=10.0, ttl=ttl)

    def is_blocked(self, edge: Tuple, threshold: float = 3.0) -> bool:
        """
        Check if an edge should be considered blocked.

        Args:
            edge:      Edge to query.
            threshold: Minimum severity to count as "blocked".

        Returns:
            True if there is an incident on the edge with severity
            greater or equal to the given threshold.
        """
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return bool(inc and inc.severity >= threshold)

    def penalty(self, edge: Tuple) -> float:
        """
        Get an extra routing cost for a given edge.

        Args:
            edge: Edge to query.

        Returns:
            A positive penalty based on severity if an incident exists,
            or 0.0 if the edge is clear.
        """
        edge = self._normalize_edge(edge)
        self.clear_expired()
        inc = self.incidents.get(edge)
        return float(inc.severity) if inc else 0.0

    def blocked_edges(self, threshold: float = 3.0) -> List[Tuple]:
        """
        Return a list of edges that should be drawn as blocked.

        Args:
            threshold: Minimum severity to be considered blocked.

        Returns:
            A list of normalized edges with severity above the threshold.
        """
        self.clear_expired()
        return [e for e, inc in self.incidents.items() if inc.severity >= threshold]

    def blocked_nodes(self) -> List[Tuple]:
        """
        Return the set of nodes that belong to any blocked edge.

        This is mostly used by the visualizer to plot roadblock icons
        at the endpoints of blocked edges.

        Returns:
            List of node coordinate tuples.
        """
        nodes: set[Tuple] = set()
        for u, v in self.blocked_edges():
            nodes.add(u)
            nodes.add(v)
        return list(nodes)

    def __repr__(self) -> str:
        """Debug representation listing the number of active incidents."""
        self.clear_expired()
        return f"EventManager({len(self.incidents)} active: {list(self.incidents.values())})"
