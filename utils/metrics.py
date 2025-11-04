import csv
import time
from statistics import mean

class Metrics:
    """
    Coleta métricas básicas da simulação de forma simples:
      - tempo de viagem por veículo
      - tempo de resposta da ambulância (EV)
      - (opcional) snapshots de congestão média
    """

    def __init__(self, filename: str = "metrics.csv"):
        self.filename = filename
        self._trip_start = {}      # vehicle_id -> t0
        self._ev_start = None      # t0 da emergência
        self.records = []          # lista de dicts (linhas do CSV)
        self._rho_snapshots = []   # valores float (0..1)

    # ---------- Viagens dos veículos ----------
    def start_trip(self, vehicle_id: str) -> None:
        self._trip_start[vehicle_id] = time.time()

    def end_trip(self, vehicle_id: str) -> None:
        t0 = self._trip_start.pop(vehicle_id, None)
        if t0 is not None:
            dt = time.time() - t0
            self.records.append({"type": "trip", "id": vehicle_id, "value": dt})

    # ---------- Emergência (EV) ----------
    def start_emergency(self) -> None:
        self._ev_start = time.time()

    def end_emergency(self) -> None:
        if self._ev_start is not None:
            dt = time.time() - self._ev_start
            self.records.append({"type": "ev_response", "id": "EV", "value": dt})
            self._ev_start = None

    # ---------- Congestão (opcional) ----------
    def log_congestion(self, avg_rho: float) -> None:
        """Guarda uma leitura de congestão média (0..1)."""
        self._rho_snapshots.append(float(avg_rho))

    # ---------- Persistência ----------
    def save(self) -> None:
        """
        Grava para CSV com colunas: type, id, value.
        Ex.: trip, veh3, 17.42   |   ev_response, EV, 12.08
        """
        with open(self.filename, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["type", "id", "value"])
            w.writeheader()
            for r in self.records:
                w.writerow(r)
            # Se houver snapshots de congestão, grava também linhas agregadas
            if self._rho_snapshots:
                w.writerow({"type": "avg_rho", "id": "-", "value": self.avg_rho()})

    # ---------- Resumo rápido ----------
    def avg_trip_time(self):
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        return mean(trips) if trips else None

    def last_ev_response(self):
        evs = [r["value"] for r in self.records if r["type"] == "ev_response"]
        return evs[-1] if evs else None

    def avg_rho(self):
        return mean(self._rho_snapshots) if self._rho_snapshots else None

    def summary(self) -> dict:
        return {
            "avg_trip_time": self.avg_trip_time(),
            "ev_response_time": self.last_ev_response(),
            "avg_rho": self.avg_rho(),
            "n_trips": len([r for r in self.records if r["type"] == "trip"]),
        }