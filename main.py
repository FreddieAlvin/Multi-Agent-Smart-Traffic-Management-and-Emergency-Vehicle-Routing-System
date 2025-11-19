# main.py
import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_lights import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent
from environment.city import CityEnvironment
from environment.visualization import Visualizer
from utils.metrics import Metrics


async def main():
    # ---------------------------------------------------
    # INIT METRICS + CITY + SHARED STATE + VISUALIZER
    # ---------------------------------------------------
    metrics = Metrics(filename="metrics.csv")
    city = CityEnvironment()
    city.metrics = metrics

    shared = {
        "vehicles": {},
        "emergency": {},
        "lights": list(city.traffic_lights.values()),
        "metrics": metrics,
    }

    vis = Visualizer(city, shared, refresh_hz=4)
    asyncio.create_task(vis.update_loop())

    # ---------------------------------------------------
    # BUILD ALL AGENT INSTANCES (no starts yet)
    # ---------------------------------------------------

    # Vehicles
    vehicles = []
    for i in range(1, 11):   # vehicle1 .. vehicle10
        jid = f"vehicle{i}@localhost"
        v = VehicleAgent(
            jid,
            "password",
            f"Vehicle {i}",
            city,
            shared,
        )
        vehicles.append(v)
        city.vehicle_jids.append(jid)

    # Emergency vehicles
    ambulances = []
    for i in range(1, 6):  # emergency1 .. emergency5
        jid = f"emergency{i}@localhost"
        em = EmergencyVehicleAgent(
            jid,
            "password",
            f"Ambulance {i}",
            city,
            shared,
            fixed_dest=None,
            pause_at_goal=3.0,
        )
        ambulances.append(em)

    # Traffic lights
    light_agents = []
    for lid, (x, y) in city.traffic_lights.items():
        jid = f"{lid}@localhost"
        tl = TrafficLightAgent(jid, "password", city_env=city, shared=shared)
        light_agents.append(tl)

    # Incident reporter
    reporter = IncidentReporterAgent(
        "reporter@localhost",
        "password",
        city,
        city.event_manager,
    )

    # ---------------------------------------------------
    # START *EVERYTHING* CONCURRENTLY
    # ---------------------------------------------------
    start_coros = []
    start_coros += [v.start(auto_register=True) for v in vehicles]
    start_coros += [em.start(auto_register=True) for em in ambulances]
    start_coros += [tl.start(auto_register=True) for tl in light_agents]
    start_coros.append(reporter.start(auto_register=True))

    await asyncio.gather(*start_coros)

    print(f"[MAIN] Started {len(light_agents)} traffic lights.")
    print(f"[MAIN] Started {len(vehicles)} vehicles.")
    print(f"[MAIN] Started {len(ambulances)} emergency vehicles.")
    print("🚦 Simulation + Viewer started with Incident Reporter.")

    # ---------------------------------------------------
    # START RANDOM ROADBLOCK LOOP (AFTER AGENTS ARE LIVE)
    # ---------------------------------------------------
    async def delayed_roadblocks():
        # small delay so you see "clean" traffic first; tweak if you want
        await city.random_roadblocks_loop(interval=3.0, ttl=8.0, max_blocks=3)

    asyncio.create_task(delayed_roadblocks())

    # ---------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        # Save metrics
        try:
            summary = metrics.summary()
            print("[MAIN] Metrics summary:", summary)
        except Exception as e:
            print(f"[MAIN] Error computing metrics summary: {e}")

        try:
            metrics.save()
            print("[MAIN] Metrics saved to", metrics.filename)
        except Exception as e:
            print(f"[MAIN] Error saving metrics: {e}")

        try:
            metrics.save_plots()
            print("[MAIN] Metric plots saved as PNG files.")
        except Exception as e:
            print(f"[MAIN] Error saving metric plots: {e}")


if __name__ == "__main__":
    asyncio.run(main())
