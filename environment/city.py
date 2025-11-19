# environment/city.py
import networkx as nx
import random
import asyncio
from environment.events import EventManager          # incident/roadblock management
from environment.occupancy import Occupancy          # traffic density tracking


class CityEnvironment:
    def __init__(self, width=20, height=20, congestion_weight=2.0):
        self.width = width
        self.height = height
        self.graph = nx.grid_2d_graph(width, height)

        # Agents / infrastructure
        self.traffic_lights = self._generate_traffic_lights()
        self.buildings = self._generate_buildings()
        self.hospitals = self._generate_hospitals()
        self.vehicle_jids = []  # list of vehicle agent JIDs for incident broadcasting

        # Systems
        self.event_manager = EventManager()
        self.occupancy = Occupancy(self.graph)
        self.congestion_weight = congestion_weight

        # Graph initialization
        self._initialize_edge_weights()
        self._annotate_graph()

    # -------------------------
    # Edge weights / congestion
    # -------------------------
    def _initialize_edge_weights(self):
        for u, v in self.graph.edges:
            self.graph[u][v]['weight'] = 1.0

    def update_edge_weights(self):
        """Recalculate edge weights dynamically based on incidents and congestion."""
        self.event_manager.clear_expired()
        for u, v in self.graph.edges:
            base = 1.0
            incident_penalty = self.event_manager.penalty((u, v))
            density = self.occupancy.rho((u, v))  # current traffic density
            self.graph[u][v]['weight'] = base + incident_penalty + self.congestion_weight * density

    # -------------------------
    # Infrastructure generators
    # -------------------------
    def _generate_traffic_lights(self):
        # Traffic lights every 4x4 grid block
        return {f"light_{x}_{y}": (x, y)
                for x in range(0, self.width, 4)
                for y in range(0, self.height, 4)}

    def _generate_buildings(self):
        # Buildings avoid traffic light intersections
        return {f"building_{x}_{y}": (x + 0.5, y + 0.5)
                for x in range(self.width - 1)
                for y in range(self.height - 1)
                if (x % 4 != 0 or y % 4 != 0)}

    def _generate_hospitals(self):
        return {
            "hospital_north": (2, self.height - 2),
            "hospital_south": (self.width - 3, 2),
            "hospital_central": (self.width // 2, self.height // 2)
        }

    # -------------------------
    # Annotate graph nodes
    # -------------------------
    def _annotate_graph(self):
        for light in self.traffic_lights.values():
            self.graph.nodes[light]["traffic_light"] = True
        for hosp in self.hospitals.values():
            self.graph.nodes[hosp]["hospital"] = True

    # -------------------------
    # Routing helpers
    # -------------------------
    def get_shortest_route(self, start, end, method="astar"):
        """Compute shortest route using A* or Dijkstra with dynamic edge weights."""
        self.update_edge_weights()
        if method == "astar":
            try:
                return nx.astar_path(
                    self.graph, start, end,
                    heuristic=lambda a, b: abs(a[0]-b[0]) + abs(a[1]-b[1]),
                    weight="weight"
                )
            except nx.NetworkXNoPath:
                return []
        else:
            try:
                return nx.dijkstra_path(self.graph, start, end, weight="weight")
            except nx.NetworkXNoPath:
                return []

    # -------------------------
    # Helper for drivable edges
    # -------------------------
    def get_drivable_edges(self):
        """Return edges that are not building corners (suitable for incident placement)."""
        return [e for e in self.graph.edges
                if e[0] not in self.buildings and e[1] not in self.buildings]

    # -------------------------
    # Random roadblocks spawning
    # -------------------------
    async def random_roadblocks_loop(self, interval=5.0, ttl=10.0, max_blocks=3):
        """
        Periodically spawn temporary roadblocks at random drivable edges.
        - interval: seconds between spawn attempts
        - ttl: duration of each roadblock in seconds
        - max_blocks: max number of new blocks per interval
        """
        while True:
            await asyncio.sleep(interval)
            drivable_edges = self.get_drivable_edges()
            # pick edges that are not already blocked
            candidates = [e for e in drivable_edges if not self.event_manager.is_blocked(e)]
            if not candidates:
                continue
            for edge in random.sample(candidates, min(max_blocks, len(candidates))):
                self.event_manager.spawn_temporary_block(edge, ttl=ttl)
