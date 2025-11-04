from collections import defaultdict

class Occupancy:
    """
    Guarda quem está em cada aresta (u, v) e calcula
    ocupação (contagem) e densidade (0..1) com base na capacidade.
    """

    def __init__(self, default_capacity: int = 5):
        # Ex.: road_usage[(u, v)] = {"veh1", "veh7", ...}
        self.road_usage = defaultdict(set)
        # Capacidade por aresta; por omissão usamos default_capacity
        self.capacity = defaultdict(lambda: default_capacity)

    # --- Configuração da capacidade (opcional por aresta) ---
    def set_capacity(self, u, v, cap: int) -> None:
        """Define capacidade específica para a aresta (u, v)."""
        self.capacity[(u, v)] = max(int(cap), 1)

    # --- Entrar / sair de uma aresta ---
    def enter(self, u, v, vehicle_id: str) -> None:
        """Regista que um veículo entrou na aresta (u, v)."""
        self.road_usage[(u, v)].add(vehicle_id)

    def leave(self, u, v, vehicle_id: str) -> None:
        """Regista que um veículo saiu da aresta (u, v)."""
        self.road_usage[(u, v)].discard(vehicle_id)

    # --- Leituras rápidas ---
    def count(self, u, v) -> int:
        """Número de veículos atualmente na aresta (u, v)."""
        return len(self.road_usage[(u, v)])

    def rho(self, u, v) -> float:
        """
        Densidade normalizada: count / capacidade, limitada a 1.0.
        Útil para custo dinâmico no routing e para semáforos adaptarem fases.
        """
        cap = max(self.capacity[(u, v)], 1)
        return min(self.count(u, v) / cap, 1.0)

    def is_full(self, u, v, threshold: float = 1.0) -> bool:
        """
        Indica se a aresta está "cheia" (rho >= threshold).
        Por omissão, considera cheia quando rho==1.0.
        """
        return self.rho(u, v) >= threshold