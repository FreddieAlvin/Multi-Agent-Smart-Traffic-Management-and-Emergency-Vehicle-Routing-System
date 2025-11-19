import csv
import time
from statistics import mean
import os
import matplotlib.pyplot as plt


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
        
    # ---------- plotting helpers ----------

    def _save_hist(self, values, title, xlabel, filename, bins=20):
        if not values:
            return

        vals = list(values)
        vals.sort()

        # Handle extreme outliers: clip at 95th percentile for visualization
        import math
        n = len(vals)
        p95 = vals[int(0.95 * (n - 1))] if n > 1 else vals[0]
        vmin = vals[0]
        vmax = p95 if p95 > vmin else vals[-1]

        plt.figure(figsize=(6, 4))
        plt.hist(vals, bins=bins, range=(vmin, vmax), density=False, edgecolor="black")

        # Mean & median lines to make the plot more informative
        from statistics import mean, median
        m = mean(vals)
        med = median(vals)
        plt.axvline(m, linestyle="--", linewidth=1, label=f"mean={m:.1f}")
        plt.axvline(med, linestyle=":", linewidth=1, label=f"median={med:.1f}")

        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel("Frequency")
        plt.legend()
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()


    def _save_series(self, values, title, ylabel, filename):
        if not values:
            return
        plt.figure()
        plt.plot(range(len(values)), values)
        plt.title(title)
        plt.xlabel("Index")
        plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()

    def _save_ecdf(self, values, title, xlabel, filename):
        """Empirical CDF: sorted values vs cumulative prob."""
        if not values:
            return
        vals = sorted(values)
        n = len(vals)
        y = [i / (n - 1) if n > 1 else 1.0 for i in range(n)]
        plt.figure()
        plt.step(vals, y, where="post")
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel("Cumulative probability")
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()

    def _save_box(self, values, title, ylabel, filename):
        if not values:
            return
        plt.figure()
        plt.boxplot(values, vert=True, showmeans=True)
        plt.title(title)
        plt.ylabel(ylabel)
        plt.tight_layout()
        plt.savefig(filename)
        plt.close()

    def save_plots(self, prefix: str | None = None):
        """
        Gera vários gráficos em PNG a partir das métricas recolhidas.
        Cria, por exemplo:
          - <base>_trip_hist.png
          - <base>_trip_ecdf.png
          - <base>_trip_box.png
          - <base>_ev_hist.png
          - <base>_ev_ecdf.png
          - <base>_rho_series.png
          - <base>_rho_hist.png
        """
        if prefix is None:
            base = os.path.splitext(self.filename)[0]  # "metrics.csv" -> "metrics"
        else:
            base = prefix

        # --- trip times ---
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        if trips:
            self._save_hist(
                trips,
                title="Trip time distribution",
                xlabel="Trip time (s)",
                filename=f"{base}_trip_hist.png",
                bins=20,
            )
            self._save_ecdf(
                trips,
                title="Trip time CDF",
                xlabel="Trip time (s)",
                filename=f"{base}_trip_ecdf.png",
            )
            self._save_box(
                trips,
                title="Trip time spread",
                ylabel="Trip time (s)",
                filename=f"{base}_trip_box.png",
            )
            self._save_series(
                trips,
                title="Trip times over completed trips",
                ylabel="Trip time (s)",
                filename=f"{base}_trip_series.png",
            )

        # --- emergency response times ---
        ev_times = [r["value"] for r in self.records if r["type"] == "ev_response"]
        if ev_times:
            self._save_hist(
                ev_times,
                title="Emergency response time distribution",
                xlabel="Response time (s)",
                filename=f"{base}_ev_hist.png",
                bins=max(5, min(20, len(ev_times))),
            )
            self._save_ecdf(
                ev_times,
                title="Emergency response time CDF",
                xlabel="Response time (s)",
                filename=f"{base}_ev_ecdf.png",
            )
            self._save_box(
                ev_times,
                title="Emergency response spread",
                ylabel="Response time (s)",
                filename=f"{base}_ev_box.png",
            )

        # --- congestion (rho) ---
        if getattr(self, "_rho_snapshots", None):
            self._save_series(
                self._rho_snapshots,
                title="Average congestion (rho) over time",
                ylabel="rho",
                filename=f"{base}_rho_series.png",
            )
            self._save_hist(
                self._rho_snapshots,
                title="Distribution of congestion (rho)",
                xlabel="rho",
                filename=f"{base}_rho_hist.png",
                bins=15,
            )
