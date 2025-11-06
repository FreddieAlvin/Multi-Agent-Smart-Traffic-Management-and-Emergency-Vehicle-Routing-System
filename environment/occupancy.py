import math
from collections import defaultdict
from typing import Tuple, Set, Dict, List
import networkx as nx


class Occupancy:
    """
    Tracks vehicle distribution across the city graph.
    Computes smoothed traffic density using an Exponential Moving Average (EMA)
    and optionally spatially-averaged local congestion.
    """

    def __init__(self, city_graph: nx.Graph, default_capacity: int = 5, alpha: float = 0.3):
        """
        :param city_graph: The NetworkX graph of the city.
        :param default_capacity: Default capacity per edge (vehicles).
        :param alpha: EMA smoothing factor (0..1). Higher = more responsive.
        """
        self.G = city_graph
        self.road_usage: Dict[Tuple, Set[str]] = defaultdict(set)
        self.capacity: Dict[Tuple, int] = defaultdict(lambda: default_capacity)
        self.smoothed_density: Dict[Tuple, float] = defaultdict(float)
        self.alpha = alpha  # EMA smoothing factor

    # -------------------------------
    # Capacity configuration
    # -------------------------------
    def set_capacity(self, u, v, cap: int) -> None:
        """Sets specific capacity for the edge (u, v)."""
        edge = self._normalize_edge((u, v))
        self.capacity[edge] = max(int(cap), 1)

    def _normalize_edge(self, edge: Tuple) -> Tuple:
        """Ensure consistent edge ordering."""
        u, v = edge
        return tuple(sorted((u, v)))

    # -------------------------------
    # Vehicle movement tracking
    # -------------------------------
    def enter(self, u, v, vehicle_id: str) -> None:
        edge = self._normalize_edge((u, v))
        self.road_usage[edge].add(vehicle_id)

    def leave(self, u, v, vehicle_id: str) -> None:
        edge = self._normalize_edge((u, v))
        self.road_usage[edge].discard(vehicle_id)

    # -------------------------------
    # Density and smoothing
    # -------------------------------
    def _instant_rho(self, edge: Tuple) -> float:
        """Instantaneous occupancy ratio."""
        edge = self._normalize_edge(edge)
        count = len(self.road_usage[edge])
        cap = max(self.capacity[edge], 1)
        return min(count / cap, 1.0)

    def rho(self, edge: Tuple) -> float:
        """
        Returns smoothed (EMA) density for the edge.
        Updates EMA every time it's queried.
        """
        edge = self._normalize_edge(edge)
        instant = self._instant_rho(edge)
        prev = self.smoothed_density[edge]
        ema = self.alpha * instant + (1 - self.alpha) * prev
        self.smoothed_density[edge] = ema
        return ema

    def is_full(self, edge: Tuple, threshold: float = 0.9) -> bool:
        """Indicates whether the edge is considered 'full'."""
        return self.rho(edge) >= threshold

    # -------------------------------
    # Spatial congestion estimation
    # -------------------------------
    def local_density(self, position: Tuple[int, int], radius: int = 2) -> float:
        """
        Estimate congestion around a node based on nearby edges within 'radius'.
        """
        edges_nearby = []
        for u, v in self.G.edges:
            if self._distance(position, u) <= radius or self._distance(position, v) <= radius:
                edges_nearby.append((u, v))

        if not edges_nearby:
            return 0.0

        densities = [self.rho((u, v)) for (u, v) in edges_nearby]
        return sum(densities) / len(densities)

    @staticmethod
    def _distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Euclidean distance between two nodes."""
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)