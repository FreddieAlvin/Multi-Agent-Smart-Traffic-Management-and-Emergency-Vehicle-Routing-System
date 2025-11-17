import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_lights import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent
from environment.city import CityEnvironment
from visualization import Visualizer

# New environment modules (importados caso precises deles noutros lados)
from environment.occupancy import Occupancy
from environment.events import EventManager
from utils.metrics import Metrics


async def main():
    # ---------------------------------------------------
    # INIT METRICS + CITY + SHARED STATE + VISUALIZER
    # ---------------------------------------------------
    # Objeto de métricas (ficheiro pode ser ajustado se quiseres outro nome)
    metrics = Metrics(filename="metrics.csv")

    # Passamos as métricas para o ambiente (city.py deve aceitar metrics=None por omissão)
    city = CityEnvironment(metrics=metrics)

    # Estado global para visualização no Visualizer
    shared = {
        "vehicles": {},
        "emergency": {},
        # podes adicionar "lights" aqui se o Visualizer usar isso
        # "lights": list(city.traffic_lights.values()),
        "metrics": metrics,
    }

    # Viewer (não bloqueia o main)
    vis = Visualizer(city, shared, refresh_hz=8)
    asyncio.create_task(vis.update_loop())

    # ---------------------------------------------------
    # START VEHICLES AND EMERGENCY VEHICLE
    # ---------------------------------------------------
    v1 = VehicleAgent(
        "vehicle1@localhost",
        "password",
        "Vehicle 1",
        city,
        shared,
    )
    v2 = VehicleAgent(
        "vehicle2@localhost",
        "password",
        "Vehicle 2",
        city,
        shared,
    )

    await v1.start(auto_register=True)
    await v2.start(auto_register=True)

    em = EmergencyVehicleAgent(
        "emergency@localhost",
        "password",
        "Ambulance",
        city,
        shared,
        fixed_dest=city.hospitals["hospital_central"],
        pause_at_goal=2.0,
    )

    await em.start(auto_register=True)

    # ---------------------------------------------------
    # INCIDENT REPORTER
    # ---------------------------------------------------
    reporter = IncidentReporterAgent("reporter@localhost", "password")
    await reporter.start(auto_register=True)

    # ---------------------------------------------------
    # START ALL GRID TRAFFIC LIGHTS (NON-BLOCKING)
    # ---------------------------------------------------
    async def start_grid_lights():
        light_agents = []
        tasks = []

        for lid, (x, y) in city.traffic_lights.items():
            jid = f"{lid}@localhost"
            tl = TrafficLightAgent(jid, "password")
            light_agents.append(tl)
            tasks.append(tl.start(auto_register=True))

        await asyncio.gather(*tasks)
        print(f"[MAIN] Started {len(light_agents)} traffic lights.")

    asyncio.create_task(start_grid_lights())

    print("🚦 Simulation + Viewer started")

    # ---------------------------------------------------
    # MAIN LOOP (KEEPS SIMULATION RUNNING)
    # ---------------------------------------------------
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Se a tarefa for cancelada por algum motivo
        pass
    finally:
        # Antes de terminar, guardar as métricas em disco
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


if __name__ == "__main__":
    # Para correr:
    #   spade run --host 127.0.0.1
    # Depois:
    #   python -u main.py
    asyncio.run(main())