"""Metrics collection and plotting utilities for the MAS traffic simulation.

This module provides:
    - Recording of trip times for vehicles.
    - Recording of emergency response durations.
    - Optional logging of congestion snapshots (rho).
    - Counting of route replanning events.
    - Saving metrics to CSV.
    - Generating histograms and time-series plots for analysis.
"""

import csv
import time
from statistics import mean
import os
import matplotlib.pyplot as plt


class Metrics:
    """Collect and manage simulation metrics.

    The metrics tracked include:
        - Travel time per vehicle.
        - Emergency vehicle (EV) response time.
        - Optional congestion snapshots.
        - Count of route replanning events.

    Attributes:
        filename (str): Output CSV filename.
        _trip_start (dict): Mapping vehicle_id → trip start timestamp.
        _ev_start (float | None): Start timestamp of the active emergency.
        records (list): Logged metric entries (dictionaries).
        _rho_snapshots (list): Logged congestion values in [0, 1].
        total_replans (int): Number of times an agent replanned its route.
    """

    def __init__(self, filename: str = "metrics.csv"):
        """Initialise the metrics manager.

        Args:
            filename (str, optional): Name of the CSV file where metrics will
                be saved. Defaults to "metrics.csv".
        """
        self.filename = filename
        self._trip_start = {}
        self._ev_start = None
        self.records = []
        self._rho_snapshots = []
        self.total_replans = 0

    # ------------------------------------------------------------------
    # Vehicle trips
    # ------------------------------------------------------------------

    def start_trip(self, vehicle_id: str) -> None:
        """Mark the start of a vehicle trip.

        Args:
            vehicle_id (str): Identifier of the vehicle starting a trip.
        """
        self._trip_start[vehicle_id] = time.time()

    def end_trip(self, vehicle_id: str) -> None:
        """Mark the end of a trip and record its duration.

        Args:
            vehicle_id (str): Identifier of the vehicle that completed a trip.
        """
        t0 = self._trip_start.pop(vehicle_id, None)
        if t0 is not None:
            dt = time.time() - t0
            self.records.append({"type": "trip", "id": vehicle_id, "value": dt})

    # ------------------------------------------------------------------
    # Emergency vehicle metrics
    # ------------------------------------------------------------------

    def start_emergency(self) -> None:
        """Mark the beginning of an emergency response."""
        self._ev_start = time.time()

    def end_emergency(self) -> None:
        """Mark the end of an emergency response and record the duration."""
        if self._ev_start is not None:
            dt = time.time() - self._ev_start
            self.records.append({"type": "ev_response", "id": "EV", "value": dt})
            self._ev_start = None

    # ------------------------------------------------------------------
    # Congestion logging
    # ------------------------------------------------------------------

    def log_congestion(self, avg_rho: float) -> None:
        """Log a congestion snapshot.

        Args:
            avg_rho (float): Average congestion value in [0, 1].
        """
        self._rho_snapshots.append(float(avg_rho))

    # ------------------------------------------------------------------
    # Replanning counter
    # ------------------------------------------------------------------

    def log_replan(self, vehicle_id: str) -> None:
        """Record a route replanning event.

        This method is called by:
            - VehicleAgent._plan_to(...)
            - EmergencyVehicleAgent._plan_to(...)

        Args:
            vehicle_id (str): ID of the agent that replanned.
        """
        self.total_replans += 1

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Write all metrics to a CSV file.

        The CSV contains rows of the form:
            type, id, value

        Example rows:
            trip, veh3, 17.42
            ev_response, EV, 12.08
            avg_rho, -, 0.03
        """
        with open(self.filename, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["type", "id", "value"])
            writer.writeheader()

            for record in self.records:
                writer.writerow(record)

            if self._rho_snapshots:
                writer.writerow({"type": "avg_rho", "id": "-", "value": self.avg_rho()})

    # ------------------------------------------------------------------
    # Quick summaries
    # ------------------------------------------------------------------

    def avg_trip_time(self):
        """Return the average trip duration.

        Returns:
            float | None: Mean of all trip durations, or None if no trips exist.
        """
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        return mean(trips) if trips else None

    def last_ev_response(self):
        """Return the most recent emergency response time.

        Returns:
            float | None: Duration of last emergency response, or None if none exist.
        """
        evs = [r["value"] for r in self.records if r["type"] == "ev_response"]
        return evs[-1] if evs else None

    def avg_rho(self):
        """Return the mean congestion value.

        Returns:
            float | None: Average congestion, or None if no snapshots exist.
        """
        return mean(self._rho_snapshots) if self._rho_snapshots else None

    def summary(self) -> dict:
        """Return a compact summary of all metrics.

        Returns:
            dict: Contains average trip time, emergency response time,
                mean congestion, number of trips logged, and total replans.
        """
        return {
            "avg_trip_time": self.avg_trip_time(),
            "ev_response_time": self.last_ev_response(),
            "avg_rho": self.avg_rho(),
            "n_trips": len([r for r in self.records if r["type"] == "trip"]),
            "total_replans": self.total_replans,
        }

    # ------------------------------------------------------------------
    # Internal plotting utilities
    # ------------------------------------------------------------------

    def _save_hist(self, values, title, xlabel, filename, bins=20):
        """Create and save a histogram of numeric values.

        Args:
            values (list): Values to plot.
            title (str): Plot title.
            xlabel (str): X-axis label.
            filename (str): Output PNG filename.
            bins (int, optional): Number of histogram bins. Defaults to 20.
        """
        if not values:
            return

        vals = list(values)
        vals.sort()

        # Clip at 95th percentile for readability
        n = len(vals)
        p95 = vals[int(0.95 * (n - 1))] if n > 1 else vals[0]
        vmin = vals[0]
        vmax = p95 if p95 > vmin else vals[-1]

        plt.figure(figsize=(6, 4))
        plt.hist(vals, bins=bins, range=(vmin, vmax),
                 density=False, edgecolor="black")

        from statistics import mean as _mean, median as _median
        m = _mean(vals)
        med = _median(vals)
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
        """Create and save a 1-D time-series plot.

        Args:
            values (list): Sequence of values.
            title (str): Plot title.
            ylabel (str): Label for Y-axis.
            filename (str): Output PNG filename.
        """
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

    # ------------------------------------------------------------------
    # Plotting API
    # ------------------------------------------------------------------

    def save_plots(self, prefix: str | None = None):
        """Generate PNG plots for trips, emergency responses and congestion.

        The following files are produced (depending on available data):
            <base>_trip_hist.png
            <base>_trip_series.png
            <base>_ev_hist.png
            <base>_ev_series.png
            <base>_rho_series.png

        Args:
            prefix (str | None, optional): Custom filename prefix. If None,
                the prefix is derived from the CSV filename (without extension).
        """
        if prefix is None:
            base = os.path.splitext(self.filename)[0]
        else:
            base = prefix

        # --- Trip times ---
        trips = [r["value"] for r in self.records if r["type"] == "trip"]
        if trips:
            self._save_hist(
                trips,
                title="Trip time distribution",
                xlabel="Trip time (s)",
                filename=f"{base}_trip_hist.png",
                bins=20,
            )
            self._save_series(
                trips,
                title="Trip times over completed trips",
                ylabel="Trip time (s)",
                filename=f"{base}_trip_series.png",
            )

        # --- Emergency response times ---
        ev_times = [r["value"] for r in self.records if r["type"] == "ev_response"]
        if ev_times:
            self._save_hist(
                ev_times,
                title="Emergency response time distribution",
                xlabel="Response time (s)",
                filename=f"{base}_ev_hist.png",
                bins=max(5, min(20, len(ev_times))),
            )
            self._save_series(
                ev_times,
                title="Emergency response times over events",
                ylabel="Response time (s)",
                filename=f"{base}_ev_series.png",
            )

        # --- Congestion series ---
        if getattr(self, "_rho_snapshots", None):
            self._save_series(
                self._rho_snapshots,
                title="Average congestion (rho) over time",
                ylabel="rho",
                filename=f"{base}_rho_series.png",
            )