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

    # Criamos a city normalmente
    city = CityEnvironment()
    # E depois penduramos o objeto de métricas à mão
    city.metrics = metrics

    # Estado global para visualização no Visualizer
    shared = {
        "vehicles": {},
        "emergency": {},
        "lights": list(city.traffic_lights.values()),
        "metrics": metrics,
    }

    # Viewer (não bloqueia o main)
    vis = Visualizer(city, shared, refresh_hz=8)
    asyncio.create_task(vis.update_loop())

    # ---------------------------------------------------
    # START MULTIPLE VEHICLES AND EMERGENCY VEHICLES
    # ---------------------------------------------------
    # --- Normal Vehicles ---
    vehicles = []
    for i in range(1, 11):   # vehicle1 .. vehicle5
        v = VehicleAgent(
            f"vehicle{i}@localhost",
            "password",
            f"Vehicle {i}",
            city,
            shared,
        )
        vehicles.append(v)

    # start them
    for v in vehicles:
        await v.start(auto_register=True)

    # --- Emergency Vehicles (2 ambulances) ---
    ambulances = []
    for i in range(1, 11):  # emergency1, emergency2
        em = EmergencyVehicleAgent(
            f"emergency{i}@localhost",
            "password",
            f"Ambulance {i}",
            city,
            shared,
            fixed_dest=city.hospitals["hospital_central"],
            pause_at_goal=2.0,
        )
        ambulances.append(em)

    # start ambulances
    for em in ambulances:
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