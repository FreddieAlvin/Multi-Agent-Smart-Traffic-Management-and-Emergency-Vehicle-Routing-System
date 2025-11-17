import csv
import time
from statistics import mean


class Metrics:
    """
    Collects simulation metrics:
      - travel time per vehicle
      - emergency vehicle (EV) response time
      - average road occupancy (rho)
      - number of replans per vehicle / total replans
    """

    def __init__(self, filename: str = "metrics.csv"):
        self.filename = filename

        # Trip timing
        self._trip_start = {}      # vehicle_id -> start_time

        # Emergency timing
        self._ev_start = None      # start_time of the emergency

        # Generic records written directly to CSV
        self.records = []          # list[dict(type, id, value)]

        # Congestion snapshots (rho in [0, 1])
        self._rho_snapshots = []   # list[float]

        # Replans
        self.total_replans = 0
        self._replans_per_vehicle = {}  # vehicle_id -> int

    # ---------- Vehicle trips ----------
    def start_trip(self, vehicle_id: str) -> None:
        """Mark the start time of a vehicle's trip."""
        self._trip_start[vehicle_id] = time.time()

    def end_trip(self, vehicle_id: str) -> None:
        """Mark the end time of a vehicle's trip and store its duration."""
        t0 = self._trip_start.pop(vehicle_id, None)
        if t0 is not None:
            dt = time.time() - t0
            self.records.append({"type": "trip", "id": vehicle_id, "value": dt})

    # ---------- Emergency vehicle (EV) ----------
    def start_emergency(self) -> None:
        """Mark the start of an emergency response."""
        self._ev_start = time.time()

    def end_emergency(self) -> None:
        """Mark the end of an emergency response and record the duration."""
        if self._ev_start is not None:
            dt = time.time() - self._ev_start
            self.records.append({"type": "ev_response", "id": "EV", "value": dt})
            self._ev_start = None

    # ---------- Congestion ----------
    def log_congestion(self, avg_rho: float) -> None:
        """Store one congestion snapshot (average rho over all edges)."""
        self._rho_snapshots.append(float(avg_rho))

    # ---------- Replans ----------
    def log_replan(self, vehicle_id: str) -> None:
        """
        Register that a vehicle has replanned its route.
        Called from VehicleAgent._plan_to(...).
        """
        self.total_replans += 1
        self._replans_per_vehicle[vehicle_id] = (
            self._replans_per_vehicle.get(vehicle_id, 0) + 1
        )

    # ---------- Persistence ----------
    def save(self) -> None:
        """
        Write metrics to a CSV file with columns: type, id, value.
        Example:
            trip, veh1, 17.42
            ev_response, EV, 12.08
            avg_rho, -, 0.31
            rho_snap, 0, 0.28
            rho_snap, 1, 0.35
            ...
        """
        with open(self.filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["type", "id", "value"])
            writer.writeheader()

            # Basic records (trips, ev_response, etc.)
            for record in self.records:
                writer.writerow(record)

            # Congestion: write snapshots and global average
            if self._rho_snapshots:
                # global average
                writer.writerow(
                    {"type": "avg_rho", "id": "-", "value": self.avg_rho()}
                )
                # time series
                for i, rho in enumerate(self._rho_snapshots):
                    writer.writerow(
                        {"type": "rho_snap", "id": str(i), "value": rho}
                    )

            # Replans: export total (optional but nice to have in CSV)
            writer.writerow(
                {"type": "total_replans", "id": "-", "value": float(self.total_replans)}
            )

    # ---------- Quick summaries ----------
    def avg_trip_time(self):
        """Return the average trip time of all vehicles."""
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        return mean(trips) if trips else None

    def last_ev_response(self):
        """Return the duration of the most recent emergency vehicle response."""
        evs = [r["value"] for r in self.records if r["type"] == "ev_response"]
        return evs[-1] if evs else None

    def avg_rho(self):
        """Return the average of all recorded congestion snapshots."""
        return mean(self._rho_snapshots) if self._rho_snapshots else None

    def summary(self) -> dict:
        """Return a summary of the main metrics."""
        return {
            "avg_trip_time": self.avg_trip_time(),
            "ev_response_time": self.last_ev_response(),
            "avg_rho": self.avg_rho(),
            "n_trips": len([r for r in self.records if r["type"] == "trip"]),
            "total_replans": self.total_replans,
        }