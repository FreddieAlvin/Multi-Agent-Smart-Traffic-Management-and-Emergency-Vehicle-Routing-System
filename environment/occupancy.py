import math
from collections import defaultdict
from typing import Tuple, Set, Dict, List
import networkx as nx


class Occupancy:
    """
    Tracks traffic occupancy and congestion levels across the city graph.

    This module maintains:
      • Which vehicles are present on each edge.
      • Edge capacities and “fullness”.
      • Smoothed density values (Exponential Moving Average).
      • Local congestion estimation around a node.

    It is used by routing agents to avoid congested edges and to compute
    dynamic path costs during A* navigation.
    """

    def __init__(self, city_graph: nx.Graph, default_capacity: int = 5, alpha: float = 0.3):
        """
        Initialize the occupancy manager.

        Args:
            city_graph (nx.Graph):
                The city road graph. Nodes are intersections; edges are roads.
            default_capacity (int):
                Default max number of vehicles per edge before it is considered full.
            alpha (float):
                Smoothing factor for the Exponential Moving Average (0 to 1).
                Larger values make density react faster to instantaneous changes.
        """
        self.G = city_graph
        self.road_usage: Dict[Tuple, Set[str]] = defaultdict(set)
        self.capacity: Dict[Tuple, int] = defaultdict(lambda: default_capacity)
        self.smoothed_density: Dict[Tuple, float] = defaultdict(float)
        self.alpha = alpha

    # -------------------------------------------------------------
    # Capacity configuration
    # -------------------------------------------------------------
    def set_capacity(self, u, v, cap: int) -> None:
        """Set a custom capacity for edge (u, v).

        Args:
            u (tuple): First node of the edge.
            v (tuple): Second node of the edge.
            cap (int): Maximum number of vehicles allowed on that edge.
        """
        edge = self._normalize_edge((u, v))
        self.capacity[edge] = max(int(cap), 1)

    def _normalize_edge(self, edge: Tuple) -> Tuple:
        """Normalize an edge tuple to ensure consistent ordering.

        Args:
            edge (tuple): An unordered pair (u, v).

        Returns:
            tuple: A sorted version of the edge (min, max).
        """
        u, v = edge
        return tuple(sorted((u, v)))

    # -------------------------------------------------------------
    # Vehicle tracking
    # -------------------------------------------------------------
    def enter(self, u, v, vehicle_id: str) -> None:
        """Register a vehicle entering edge (u, v).

        Args:
            u (tuple): Previous node.
            v (tuple): Next node.
            vehicle_id (str): Vehicle identifier.
        """
        edge = self._normalize_edge((u, v))
        self.road_usage[edge].add(vehicle_id)

    def leave(self, u, v, vehicle_id: str) -> None:
        """Register a vehicle leaving edge (u, v).

        Args:
            u (tuple): Previous node.
            v (tuple): Next node.
            vehicle_id (str): Vehicle identifier.
        """
        edge = self._normalize_edge((u, v))
        self.road_usage[edge].discard(vehicle_id)

    # -------------------------------------------------------------
    # Density (instantaneous + smoothed)
    # -------------------------------------------------------------
    def _instant_rho(self, edge: Tuple) -> float:
        """Compute instantaneous occupancy ratio for the edge.

        Args:
            edge (tuple): Edge (u, v).

        Returns:
            float: Current occupancy level, clipped to [0, 1].
        """
        edge = self._normalize_edge(edge)
        count = len(self.road_usage[edge])
        cap = max(self.capacity[edge], 1)
        return min(count / cap, 1.0)

    def rho(self, edge: Tuple) -> float:
        """Return smoothed traffic density (EMA) for the edge.

        This updates the exponential moving average every time it is called.

        Args:
            edge (tuple): Edge (u, v).

        Returns:
            float: Smoothed density value (0 to 1).
        """
        edge = self._normalize_edge(edge)
        instant = self._instant_rho(edge)
        prev = self.smoothed_density[edge]
        ema = self.alpha * instant + (1 - self.alpha) * prev
        self.smoothed_density[edge] = ema
        return ema

    def is_full(self, edge: Tuple, threshold: float = 0.9) -> bool:
        """Check if the edge is considered congested.

        Args:
            edge (tuple): The edge to check.
            threshold (float):
                Density threshold above which the edge is considered full.

        Returns:
            bool: True if edge density >= threshold.
        """
        return self.rho(edge) >= threshold

    # -------------------------------------------------------------
    # Spatial congestion estimation
    # -------------------------------------------------------------
    def local_density(self, position: Tuple[int, int], radius: int = 2) -> float:
        """Estimate congestion around a location.

        Args:
            position (tuple): Node coordinates (x, y).
            radius (int):
                Graph-distance radius within which nearby edges are averaged.

        Returns:
            float: Average smoothed density of neighboring edges.
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
        """Compute Euclidean distance between two points.

        Args:
            a (tuple): First coordinate (x, y).
            b (tuple): Second coordinate (x, y).

        Returns:
            float: Euclidean distance.
        """
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
