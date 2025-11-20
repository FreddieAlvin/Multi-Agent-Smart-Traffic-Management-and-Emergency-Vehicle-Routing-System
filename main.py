"""
Main entry point for the Smart Traffic Management simulation.

This module initializes the city environment, spawns all autonomous agents
(vehicles, ambulances, traffic lights, and the incident reporter), launches
the live visualizer, and starts the simulation event loop.

The simulation runs asynchronously using SPADE agents and monitors:
    - normal vehicle movement
    - emergency vehicle response
    - traffic light coordination using Contract-Net
    - dynamic roadblock generation and event propagation
    - congestion monitoring
    - metric collection and plot generation

The program terminates only when manually stopped.
"""

import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_lights import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent
from environment.city import CityEnvironment
from environment.visualization import Visualizer
from utils.metrics import Metrics


async def main():
    """
    Launches and manages the full simulation lifecycle.

    Responsibilities:
        - Initialize Metrics, CityEnvironment, and shared state
        - Create and start SPADE agents (vehicles, emergency vehicles,
          traffic lights, incident reporter)
        - Launch the visualizer update loop
        - Start a background process that injects random roadblocks
        - Continuously log global congestion (rho)
        - Save metrics and plots when the simulation ends

    This function blocks indefinitely in the main loop until the program
    is terminated externally.

    Raises:
        asyncio.CancelledError: If the main loop is cancelled by shutdown.
    """
    # ---------------------------------------------------
    # INIT METRICS + CITY + SHARED STATE + VISUALIZER
    # ---------------------------------------------------
    metrics = Metrics(filename="metrics.csv")
    city = CityEnvironment()
    city.metrics = metrics  # link city to metrics collector

    shared = {
        "vehicles": {},
        "emergency": {},
        "lights": list(city.traffic_lights.values()),
        "metrics": metrics,
    }

    # Launch the visualizer asynchronously
    vis = Visualizer(city, shared, refresh_hz=4)
    asyncio.create_task(vis.update_loop())

    # ---------------------------------------------------
    # BUILD ALL AGENT INSTANCES (no starts yet)
    # ---------------------------------------------------

    # Vehicles (10 normal agents)
    vehicles = []
    for i in range(1, 11):
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

    # Emergency vehicles (5 ambulances)
    ambulances = []
    for i in range(1, 6):
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

    # Incident reporter (injects accident events & gossips them)
    reporter = IncidentReporterAgent(
        "reporter@localhost",
        "password",
        city,
        city.event_manager,
    )

    # ---------------------------------------------------
    # START *EVERYTHING* CONCURRENTLY
    # ---------------------------------------------------
    start_coros = (
        [v.start(auto_register=True) for v in vehicles] +
        [em.start(auto_register=True) for em in ambulances] +
        [tl.start(auto_register=True) for tl in light_agents] +
        [reporter.start(auto_register=True)]
    )

    await asyncio.gather(*start_coros)

    print(f"[MAIN] Started {len(light_agents)} traffic lights.")
    print(f"[MAIN] Started {len(vehicles)} vehicles.")
    print(f"[MAIN] Started {len(ambulances)} emergency vehicles.")
    print("🚦 Simulation + Viewer started with Incident Reporter.")

    # ---------------------------------------------------
    # START RANDOM ROADBLOCK LOOP
    # ---------------------------------------------------
    async def delayed_roadblocks():
        """
        Continuously spawns temporary roadblocks at random locations.

        This runs as a background coroutine and injects incidents every few
        seconds, allowing agents to react and replan in real time.
        """
        await city.random_roadblocks_loop(
            interval=3.0,
            ttl=8.0,
            max_blocks=3
        )

    asyncio.create_task(delayed_roadblocks())

    # ---------------------------------------------------
    # MAIN LOOP
    # ---------------------------------------------------
    try:
        while True:
            await asyncio.sleep(1)

            # --- log congestion (rho) ---
            try:
                all_pos = (
                    list(shared.get("vehicles", {}).values()) +
                    list(shared.get("emergency", {}).values())
                )
                unique_occ = len({tuple(p) for p in all_pos})
                total_nodes = city.graph.number_of_nodes()

                rho = unique_occ / total_nodes if total_nodes > 0 else 0.0
                metrics.log_congestion(rho)

            except Exception as e:
                print("[MAIN] Congestion logging error:", e)

    except asyncio.CancelledError:
        # Graceful shutdown
        pass

    finally:
        # ---------------------------------------------------
        # SAVE METRICS + PLOTS
        # ---------------------------------------------------
        try:
            print("[MAIN] Metrics summary:", metrics.summary())
        except Exception as e:
            print("[MAIN] Error computing metrics summary:", e)

        try:
            metrics.save()
            print("[MAIN] Metrics saved.")
        except Exception as e:
            print("[MAIN] Error saving metrics:", e)

        try:
            metrics.save_plots()
            print("[MAIN] Metric plots saved.")
        except Exception as e:
            print("[MAIN] Error saving plots:", e)


if __name__ == "__main__":
    asyncio.run(main())
