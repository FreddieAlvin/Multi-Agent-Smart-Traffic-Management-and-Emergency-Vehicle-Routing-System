# environment/city.py
import networkx as nx
from environment.events import EventManager          # <- file name is 'events.py'
from environment.occupancy import Occupancy          # <- needs the graph

class CityEnvironment:
    def __init__(self, width=20, height=20, congestion_weight=2.0):
        self.width = width
        self.height = height
        self.graph = nx.grid_2d_graph(width, height)

        self.traffic_lights = self._generate_traffic_lights()
        self.buildings = self._generate_buildings()
        self.hospitals = self._generate_hospitals()

        self.event_manager = EventManager()
        self.occupancy = Occupancy(self.graph)       # <- pass the graph
        self.congestion_weight = congestion_weight

        self._initialize_edge_weights()
        self._annotate_graph()

    def _initialize_edge_weights(self):
        for u, v in self.graph.edges:
            self.graph[u][v]['weight'] = 1.0

    def update_edge_weights(self):
        """Recalculate weights dynamically based on incidents and congestion."""
        self.event_manager.clear_expired()
        for u, v in self.graph.edges:
            base = 1.0
            incident_penalty = self.event_manager.penalty((u, v))   # from events.py
            density = self.occupancy.rho((u, v))                    # <- use rho()
            self.graph[u][v]['weight'] = base + incident_penalty + self.congestion_weight * density

    def _generate_traffic_lights(self):
        return {f"light_{x}_{y}": (x, y)
                for x in range(0, self.width, 4)
                for y in range(0, self.height, 4)}

    def _generate_buildings(self):
        return {f"building_{x}_{y}": (x+0.5, y+0.5)
                for x in range(self.width-1)
                for y in range(self.height-1)
                if (x % 4 != 0 or y % 4 != 0)}

    def _generate_hospitals(self):
        return {
            "hospital_north": (2, self.height - 2),
            "hospital_south": (self.width - 3, 2),
            "hospital_central": (self.width // 2, self.height // 2)
        }

    def _annotate_graph(self):
        for light in self.traffic_lights.values():
            self.graph.nodes[light]["traffic_light"] = True
        for hosp in self.hospitals.values():
            self.graph.nodes[hosp]["hospital"] = True

    def get_shortest_route(self, start, end, method="astar"):
        """Compute shortest route using A* or Dijkstra with dynamic weights."""
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
