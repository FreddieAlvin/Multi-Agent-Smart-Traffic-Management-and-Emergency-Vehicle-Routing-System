import time

class Incident:
    """
    Representa um incidente numa aresta (u, v) do grafo.
    Guarda a sua severidade e o tempo até desaparecer (TTL).
    """

    def __init__(self, edge, severity: float = 1.0, ttl: float = 30.0):
        self.edge = edge                # Exemplo: ("A", "B")
        self.severity = max(severity, 0.0)
        self.expires_at = time.time() + ttl

    def is_active(self) -> bool:
        """Devolve True se o incidente ainda não expirou."""
        return time.time() < self.expires_at


class EventManager:
    """
    Gere todos os incidentes ativos na cidade.
    Permite criar, verificar e remover automaticamente os expirados.
    """

    def __init__(self):
        # Dicionário com as arestas e os respetivos incidentes
        self.incidents = {}

    def spawn_incident(self, edge, severity: float = 1.0, ttl: float = 30.0):
        """
        Cria um novo incidente na aresta (u, v) com severidade e duração dadas.
        """
        self.incidents[edge] = Incident(edge, severity, ttl)

    def clear_expired(self):
        """Remove todos os incidentes cujo TTL já terminou."""
        for edge in list(self.incidents.keys()):
            if not self.incidents[edge].is_active():
                del self.incidents[edge]

    def is_blocked(self, edge) -> bool:
        """
        Indica se a aresta está bloqueada (severidade >= 1.0).
        """
        self.clear_expired()
        inc = self.incidents.get(edge)
        return bool(inc and inc.severity >= 1.0)

    def penalty(self, edge) -> float:
        """
        Retorna uma penalização adicional para o custo da rota.
        (0.0 se não houver incidente ou se já tiver expirado.)
        """
        self.clear_expired()
        inc = self.incidents.get(edge)
        return inc.severity if inc else 0.0