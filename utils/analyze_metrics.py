# utils/analyze_metrics.py

import csv
from statistics import mean
import matplotlib.pyplot as plt


def load_metrics(filename="metrics.csv"):
    records = []
    with open(filename, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["value"] = float(row["value"]) if row["value"] != "" else None
            records.append(row)
    return records


def summarize(records):
    trips = [r["value"] for r in records if r["type"] == "trip"]
    ev_responses = [r["value"] for r in records if r["type"] == "ev_response"]
    avg_rho_rows = [r["value"] for r in records if r["type"] == "avg_rho"]
    total_replans_rows = [r["value"] for r in records if r["type"] == "total_replans"]

    avg_trip_time = mean(trips) if trips else None
    ev_response_time = ev_responses[-1] if ev_responses else None
    avg_rho = avg_rho_rows[0] if avg_rho_rows else None
    total_replans = int(total_replans_rows[0]) if total_replans_rows else 0

    return {
        "avg_trip_time": avg_trip_time,
        "ev_response_time": ev_response_time,
        "avg_rho": avg_rho,
        "total_replans": total_replans,
        "all_trips": trips,
    }


def main():
    records = load_metrics("metrics.csv")
    summ = summarize(records)

    print("=== Simulation Metrics Summary ===")
    print(f"Average trip time (s):          {summ['avg_trip_time']}")
    print(f"Emergency response time (s):    {summ['ev_response_time']}")
    print(f"Number of replans:              {summ['total_replans']}")
    print(f"Average road occupancy ρ:       {summ['avg_rho']}")

    # ---------- Figure 1: global summary (bar chart) ----------
    labels = ["Avg trip time (s)", "EV response time (s)", "Total replans", "Avg occupancy (ρ)"]
    values = [
        summ["avg_trip_time"] or 0.0,
        summ["ev_response_time"] or 0.0,
        float(summ["total_replans"] or 0.0),
        summ["avg_rho"] or 0.0,
    ]

    plt.figure(figsize=(8, 4))
    plt.bar(labels, values)
    plt.xticks(rotation=20, ha="right")
    plt.ylabel("Value")
    plt.title("Simulation Metrics Summary")
    plt.tight_layout()
    plt.savefig("metrics_summary.png", dpi=200)

    # ---------- Figure 2: average trip time per vehicle ----------
    trips_by_vehicle = {}
    for r in records:
        if r["type"] == "trip":
            vid = r["id"]
            trips_by_vehicle.setdefault(vid, []).append(r["value"])

    if trips_by_vehicle:
        vehicles = sorted(trips_by_vehicle.keys())
        avg_times = [mean(trips_by_vehicle[v]) for v in vehicles]

        plt.figure(figsize=(8, 4))
        plt.bar(vehicles, avg_times)
        plt.xlabel("Vehicle")
        plt.ylabel("Average trip time (s)")
        plt.title("Average Trip Time per Vehicle")
        plt.xticks(rotation=15, ha="right")
        plt.tight_layout()
        plt.savefig("avg_trip_per_vehicle.png", dpi=200)

    # ---------- Figure 3: distribution of trip times (histogram) ----------
    if summ["all_trips"]:
        plt.figure(figsize=(8, 4))
        plt.hist(summ["all_trips"], bins="auto")
        plt.xlabel("Trip time (s)")
        plt.ylabel("Number of trips")
        plt.title("Distribution of Trip Times")
        plt.tight_layout()
        plt.savefig("trip_time_distribution.png", dpi=200)

    # ---------- Figure 4: evolution of ρ over time ----------
    rho_series = [r["value"] for r in records if r["type"] == "rho_snap"]
    if rho_series:
        plt.figure(figsize=(8, 4))
        plt.plot(range(len(rho_series)), rho_series, marker="o")
        plt.xlabel("Snapshot")
        plt.ylabel("ρ (average occupancy)")
        plt.title("Evolution of Road Occupancy (ρ)")
        plt.tight_layout()
        plt.savefig("rho_evolution.png", dpi=200)


if __name__ == "__main__":
    main()