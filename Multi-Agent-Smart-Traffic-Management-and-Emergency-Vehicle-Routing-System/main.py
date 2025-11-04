import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_light import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent

# novos módulos do ambiente
from environment.occupancy import Occupancy
from environment.events import EventManager
from utils.metrics import Metrics


async def main():
    # --- Inicializar ambiente partilhado ---
    occupancy = Occupancy(default_capacity=5)
    events = EventManager()
    metrics = Metrics("metrics.csv")

    # --- Criar agentes ---
    tl1 = TrafficLightAgent("light1@localhost", "password", occupancy, events)
    tl2 = TrafficLightAgent("light2@localhost", "password", occupancy, events)

    v1 = VehicleAgent("vehicle1@localhost", "password", "Vehicle 1", occupancy, events, metrics)
    v2 = VehicleAgent("vehicle2@localhost", "password", "Vehicle 2", occupancy, events, metrics)

    em = EmergencyVehicleAgent("emergency@localhost", "password", "Ambulance", occupancy, events, metrics)
    reporter = IncidentReporterAgent("reporter@localhost", "password", events)

    # --- Iniciar agentes ---
    agents = [tl1, tl2, v1, v2, em, reporter]
    for agent in agents:
        await agent.start(auto_register=True)

    print("🚦 Simulation started")

    # --- Loop da simulação (exemplo: 60 segundos) ---
    try:
        for t in range(60):
            # (opcional) recolher congestão média a cada segundo
            avg_rho = 0.0
            if occupancy.road_usage:
                total_rho = sum(occupancy.rho(u, v) for (u, v) in occupancy.road_usage.keys())
                avg_rho = total_rho / len(occupancy.road_usage)
            metrics.log_congestion(avg_rho)

            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Simulation stopped manually")

    # --- Parar agentes e guardar métricas ---
    for agent in agents:
        await agent.stop()
    metrics.save()
    print("✅ Simulation finished, metrics saved.")


if __name__ == "__main__":
    asyncio.run(main())
