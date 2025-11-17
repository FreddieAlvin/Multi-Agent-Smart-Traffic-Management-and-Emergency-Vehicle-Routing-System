# environment/city.py

import networkx as nx
from environment.events import EventManager
from environment.occupancy import Occupancy


class CityEnvironment:
    """
    Representa a cidade, incluindo:
      • grafo 2D da cidade (20x20 por defeito)
      • semáforos automáticos (em grelha 4x4)
      • edifícios e hospitais
      • gestor de eventos (acidentes)
      • gestor de ocupação (densidade de tráfego)
      • ligação ao módulo de métricas

    A cada chamada de update_edge_weights():
      – atualiza pesos das arestas com incidentes + congestionamento
      – calcula densidade média ρ
      – regista snapshot ρ no objeto de métricas (se existir)
    """

    def __init__(self, width=20, height=20, congestion_weight=2.0, metrics=None):
        self.width = width
        self.height = height

        # Grafo base (grid 2D)
        self.graph = nx.grid_2d_graph(width, height)

        # Infraestruturas
        self.traffic_lights = self._generate_traffic_lights()
        self.buildings = self._generate_buildings()
        self.hospitals = self._generate_hospitals()

        # Gestores
        self.event_manager = EventManager()
        self.occupancy = Occupancy(self.graph)
        self.congestion_weight = congestion_weight

        # Referência ao objeto Metrics (pode ser None)
        self.metrics = metrics

        # Inicializações
        self._initialize_edge_weights()
        self._annotate_graph()

    # ----------------------------------------------------------
    # Inicialização da Cidade
    # ----------------------------------------------------------

    def _initialize_edge_weights(self):
        """Define peso base=1.0 para todas as arestas."""
        for u, v in self.graph.edges:
            self.graph[u][v]["weight"] = 1.0

    def _generate_traffic_lights(self):
        """Gera semáforos de 4 em 4 interseções."""
        return {
            f"light_{x}_{y}": (x, y)
            for x in range(0, self.width, 4)
            for y in range(0, self.height, 4)
        }

    def _generate_buildings(self):
        """Gera edifícios em todas as células exceto nas interseções 4x4."""
        return {
            f"building_{x}_{y}": (x + 0.5, y + 0.5)
            for x in range(self.width - 1)
            for y in range(self.height - 1)
            if (x % 4 != 0 or y % 4 != 0)
        }

    def _generate_hospitals(self):
        return {
            "hospital_north": (2, self.height - 2),
            "hospital_south": (self.width - 3, 2),
            "hospital_central": (self.width // 2, self.height // 2),
        }

    def _annotate_graph(self):
        """Anota no grafo as posições com semáforos e hospitais."""
        for light in self.traffic_lights.values():
            self.graph.nodes[light]["traffic_light"] = True
        for hosp in self.hospitals.values():
            self.graph.nodes[hosp]["hospital"] = True

    # ----------------------------------------------------------
    # Atualização Dinâmica de Pesos + Métrica ρ
    # ----------------------------------------------------------

    def update_edge_weights(self):
        """
        Recalcula pesos dinamicamente com base em:
          – incidentes
          – densidade (ρ) da ocupação
        Também calcula a ocupação média total e regista no objeto Metrics.
        """

        # Limpar eventos expirados (acidentes)
        self.event_manager.clear_expired()

        total_density = 0.0
        edge_count = 0

        for u, v in self.graph.edges:

            base = 1.0

            # penalização por incidentes (se existir)
            incident_penalty = self.event_manager.penalty((u, v))

            # densidade (rho) da ocupação
            try:
                density = self.occupancy.rho((u, v))
            except Exception:
                density = 0.0

            # novo peso dinâmico
            weight = base + incident_penalty + self.congestion_weight * float(density)
            self.graph[u][v]["weight"] = weight

            total_density += float(density)
            edge_count += 1

        # Registar métrica de ocupação média (snapshot ρ)
        if self.metrics is not None and edge_count > 0:
            avg_rho = total_density / edge_count
            self.metrics.log_congestion(avg_rho)

    # ----------------------------------------------------------
    # Cálculo de Rotas (A* ou Dijkstra)
    # ----------------------------------------------------------

    def get_shortest_route(self, start, end, method="astar"):
        """
        Calcula o caminho mais rápido entre start e end.
        Antes do cálculo:
           → chama update_edge_weights()
              (importante para ter ρ atualizado e eventos!)
        """
        self.update_edge_weights()

        if method == "astar":
            try:
                return nx.astar_path(
                    self.graph,
                    start,
                    end,
                    heuristic=lambda a, b: abs(a[0] - b[0]) + abs(a[1] - b[1]),
                    weight="weight",
                )
            except nx.NetworkXNoPath:
                return []
        else:
            try:
                return nx.dijkstra_path(
                    self.graph, start, end, weight="weight"
                )
            except nx.NetworkXNoPath:
                return []