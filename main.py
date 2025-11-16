import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_lights import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent
from environment.city import CityEnvironment
from visualization import Visualizer


async def main():
    city = CityEnvironment()

    # shared state para visualização
    shared = {
        "vehicles": {},
        "emergency": {},
        # já não precisamos de "lights" aqui; os semáforos vêm de city.traffic_lights
    }

    # start the viewer
    vis = Visualizer(city, shared, refresh_hz=8)
    asyncio.create_task(vis.update_loop())

    # --- START VEHICLES + AMBULANCE FIRST (so dots appear immediately) ---
    v1 = VehicleAgent("vehicle1@localhost", "password", "Vehicle 1", city, shared)
    v2 = VehicleAgent("vehicle2@localhost", "password", "Vehicle 2", city, shared)
    await v1.start(auto_register=True)
    await v2.start(auto_register=True)

    em = EmergencyVehicleAgent(
        "emergency@localhost",
        "password",
        "Ambulance",
        city,
        shared,
        fixed_dest=city.hospitals["hospital_central"],  # hospital node (x, y)
        pause_at_goal=2.0,
    )
    await em.start(auto_register=True)

    reporter = IncidentReporterAgent("reporter@localhost", "password")
    await reporter.start(auto_register=True)

    # --- START ALL GRID LIGHTS IN THE BACKGROUND (don’t block UI) ---
    async def start_grid_lights():
        light_agents, tasks = [], []
        for lid, (x, y) in city.traffic_lights.items():
            # lid é algo como "light_4_8" → JID "light_4_8@localhost"
            jid = f"{lid}@localhost"
            tl = TrafficLightAgent(jid, "password")
            light_agents.append(tl)
            tasks.append(tl.start(auto_register=True))
        await asyncio.gather(*tasks)
        print(f"[MAIN] started {len(light_agents)} traffic lights")

    asyncio.create_task(start_grid_lights())  # <- arranca sem bloquear o main

    print("🚦 Simulation + Viewer started")

    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    # NOTE: Run the SPADE server in another terminal:
    #   spade run --host 127.0.0.1
    # Then launch this file:
    #   python -u main.py
    asyncio.run(main())