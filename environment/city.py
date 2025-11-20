"""
city.py

Definition of the grid-based city environment used by all agents.

The CityEnvironment class:
  * creates a rectangular grid as a NetworkX graph;
  * attaches edge weights that can change with congestion;
  * keeps track of traffic lights and hospitals;
  * exposes helper methods to:
      - sample free nodes;
      - compute average congestion;
      - randomly spawn and remove temporary roadblocks.
"""

import asyncio
import random
from typing import Dict, Tuple, List

import networkx as nx

from .occupancy import Occupancy
from .events import EventManager


class CityEnvironment:
    """
    Grid city with dynamic edge weights, occupancy, and incidents.

    Attributes:
        width:   Number of columns in the grid.
        height:  Number of rows in the grid.
        graph:   NetworkX graph representing the road network.
        traffic_lights:
            Map from light id (e.g. "light_4_4") to node coordinates.
        hospitals:
            Map from hospital id to node coordinates.
        occupancy:
            Occupancy helper that tracks how many vehicles use each edge.
        event_manager:
            EventManager that stores temporary incidents / roadblocks.
        metrics:
            Optional Metrics object, filled by main.py.
        vehicle_jids:
            List of JIDs for all vehicle agents (for broadcast if needed).
    """

    def __init__(self, width: int = 20, height: int = 20) -> None:
        """
        Build a new grid city.

        Args:
            width:  Grid width in cells.
            height: Grid height in cells.
        """
        self.width = width
        self.height = height

        # Underlying road network
        self.graph: nx.Graph = nx.grid_2d_graph(width, height)

        # Basic static attributes
        self.traffic_lights: Dict[str, Tuple[int, int]] = {}
        self.hospitals: Dict[str, Tuple[int, int]] = {}
        self.vehicle_jids: List[str] = []

        # Dynamic components
        self.occupancy = Occupancy(self.graph)
        self.event_manager = EventManager()

        # Optional metrics object set from outside
        self.metrics = None

        # Initialize structure of the city
        self._build_grid()
        self._add_traffic_lights()
        self._add_hospitals()

    # ------------------------------------------------------------------
    # Grid construction helpers
    # ------------------------------------------------------------------

    def _build_grid(self) -> None:
        """
        Attach default weights to each edge of the grid.

        Currently every edge starts with weight = 1.0. This value
        is later adjusted to reflect congestion (via Occupancy).
        """
        for u, v in self.graph.edges():
            # All roads start with the same base cost.
            self.graph[u][v]["weight"] = 1.0

    def _add_traffic_lights(self) -> None:
        """
        Place traffic lights at some intersections.

        For simplicity, this places one light at each 4x4 intersection
        inside the grid. The key in the dictionary encodes the position.
        """
        for x in range(0, self.width, 4):
            for y in range(0, self.height, 4):
                lid = f"light_{x}_{y}"
                self.traffic_lights[lid] = (x, y)

    def _add_hospitals(self) -> None:
        """
        Add a small number of hospitals in the city.

        This is intentionally simple and deterministic so that
        emergency vehicles always have a few obvious destinations.
        """
        # Place 3 hospitals in different zones of the grid.
        self.hospitals = {
            "hospital_nw": (2, self.height - 2),
            "hospital_ne": (self.width - 3, self.height - 3),
            "hospital_central": (self.width // 2, self.height // 2),
        }

    # ------------------------------------------------------------------
    # Graph convenience helpers
    # ------------------------------------------------------------------

    def neighbors(self, node: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Get the neighbors of a given node in the grid.

        Args:
            node: Node coordinate (x, y).

        Returns:
            List of adjacent node coordinates.
        """
        return list(self.graph.neighbors(node))

    def get_drivable_edges(self) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        Return all edges that can be used by vehicles.

        At the moment this is simply the full edge set of the grid.

        Returns:
            List of edges as ((x1, y1), (x2, y2)).
        """
        return list(self.graph.edges())

    def random_free_node(self) -> Tuple[int, int]:
        """
        Pick a random node in the grid.

        This helper does not check congestion or incidents, so it is
        mainly used for choosing random vehicle goals.
        """
        return random.choice(list(self.graph.nodes()))

    # ------------------------------------------------------------------
    # Dynamic behaviour: congestion and roadblocks
    # ------------------------------------------------------------------

    def compute_avg_rho(self) -> float | None:
        """
        Compute the average congestion (rho) across all edges.

        Returns:
            Average occupancy value across edges, or None if no
            occupancy information is available.
        """
        if not hasattr(self, "occupancy") or not self.occupancy.edge_counts:
            return None

        values = list(self.occupancy.edge_counts.values())
        if not values:
            return None
        return sum(values) / len(values)

    def update_edge_weights(self) -> None:
        """
        Update edge weights based on current congestion.

        The Occupancy object keeps a "density" estimate for every edge.
        This method writes that value into the graph's "weight" field,
        which is then used by the routing algorithms (A*).
        """
        for (u, v) in self.graph.edges():
            # Base cost is 1.0; add a fraction of the occupancy density.
            rho = self.occupancy.edge_density(u, v)
            self.graph[u][v]["weight"] = 1.0 + rho

    async def random_roadblocks_loop(
        self,
        interval: float = 3.0,
        ttl: float = 8.0,
        max_blocks: int = 3,
    ) -> None:
        """
        Periodically spawn and clear temporary roadblocks.

        This coroutine runs forever (until the simulation exits) and
        uses the EventManager to create high-severity incidents on
        random edges that are not currently blocked.

        Args:
            interval:
                Time in seconds between iterations of the loop.
            ttl:
                Time-to-live in seconds for each spawned roadblock.
            max_blocks:
                Maximum number of new blocks to spawn per iteration.
        """
        while True:
            await asyncio.sleep(interval)

            # Start from all drivable edges.
            drivable_edges = self.get_drivable_edges()

            # Pick edges that are not already blocked.
            candidates = [
                e for e in drivable_edges
                if not self.event_manager.is_blocked(e)
            ]
            if not candidates:
                continue

            # Sample up to max_blocks edges and block them temporarily.
            for edge in random.sample(candidates, min(max_blocks, len(candidates))):
                self.event_manager.spawn_temporary_block(edge, ttl=ttl)
