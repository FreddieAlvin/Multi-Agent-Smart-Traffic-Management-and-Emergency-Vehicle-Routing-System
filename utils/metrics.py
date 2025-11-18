import csv
import time
from statistics import mean

class Metrics:
    """
    Collects basic simulation metrics in a simple way:
      - travel time per vehicle
      - emergency vehicle (EV) response time
      - (optional) average congestion snapshots
    """

    def __init__(self, filename: str = "metrics.csv"):
        self.filename = filename
        self._trip_start = {}      # vehicle_id -> start_time
        self._ev_start = None      # start_time of the emergency
        self.records = []          # list of dicts (CSV rows)
        self._rho_snapshots = []   # float values (0..1)
                # contagem de replans (planeamentos de rota)
        self.total_replans = 0

    # ---------- Vehicle trips ----------
    def start_trip(self, vehicle_id: str) -> None:
        """Marks the start time of a vehicle’s trip."""
        self._trip_start[vehicle_id] = time.time()

    def end_trip(self, vehicle_id: str) -> None:
        """Marks the end time of a vehicle’s trip and stores its duration."""
        t0 = self._trip_start.pop(vehicle_id, None)
        if t0 is not None:
            dt = time.time() - t0
            self.records.append({"type": "trip", "id": vehicle_id, "value": dt})

    # ---------- Emergency vehicle (EV) ----------
    def start_emergency(self) -> None:
        """Marks the start of an emergency response."""
        self._ev_start = time.time()

    def end_emergency(self) -> None:
        """Marks the end of an emergency response and records the duration."""
        if self._ev_start is not None:
            dt = time.time() - self._ev_start
            self.records.append({"type": "ev_response", "id": "EV", "value": dt})
            self._ev_start = None

    # ---------- Congestion (optional) ----------
    def log_congestion(self, avg_rho: float) -> None:
        """Stores a single average congestion reading (0..1)."""
        self._rho_snapshots.append(float(avg_rho))

    # ---------- Replans ----------
    def log_replan(self, vehicle_id: str) -> None:
        """
        Regista que um agente replaneou a rota.
        Chamado em VehicleAgent._plan_to(...) e EmergencyVehicleAgent._plan_to(...).
        """
        self.total_replans += 1


    # ---------- Persistence ----------
    def save(self) -> None:
        """
        Writes metrics to a CSV file with columns: type, id, value.
        Example:
            trip, veh3, 17.42
            ev_response, EV, 12.08
        """
        with open(self.filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["type", "id", "value"])
            writer.writeheader()
            for record in self.records:
                writer.writerow(record)
            # If congestion snapshots exist, also write an aggregated average
            if self._rho_snapshots:
                writer.writerow({"type": "avg_rho", "id": "-", "value": self.avg_rho()})

    # ---------- Quick summaries ----------
    def avg_trip_time(self):
        """Returns the average trip time of all vehicles."""
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        return mean(trips) if trips else None

    def last_ev_response(self):
        """Returns the duration of the most recent emergency vehicle response."""
        evs = [r["value"] for r in self.records if r["type"] == "ev_response"]
        return evs[-1] if evs else None

    def avg_rho(self):
        """Returns the average of all recorded congestion snapshots."""
        return mean(self._rho_snapshots) if self._rho_snapshots else None

    def summary(self) -> dict:
        """Returns a summary of the main metrics."""
        return {
            "avg_trip_time": self.avg_trip_time(),
            "ev_response_time": self.last_ev_response(),
            "avg_rho": self.avg_rho(),
            "n_trips": len([r for r in self.records if r["type"] == "trip"]),
        }