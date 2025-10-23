import asyncio
from agents.vehicle import VehicleAgent
from agents.traffic_light import TrafficLightAgent
from agents.emergency_vehicle import EmergencyVehicleAgent
from agents.incident_reporter import IncidentReporterAgent

async def main():
    # Start traffic lights
    tl1 = TrafficLightAgent("light1@localhost", "password")
    await tl1.start(auto_register=True)
    tl2 = TrafficLightAgent("light2@localhost", "password")
    await tl2.start(auto_register=True)

    # Start vehicles
    v1 = VehicleAgent("vehicle1@localhost", "password", "Vehicle 1")
    v2 = VehicleAgent("vehicle2@localhost", "password", "Vehicle 2")
    await v1.start(auto_register=True)
    await v2.start(auto_register=True)

    # Start emergency vehicle
    em = EmergencyVehicleAgent("emergency@localhost", "password", "Ambulance")
    await em.start(auto_register=True)

    # Start incident reporter
    reporter = IncidentReporterAgent("reporter@localhost", "password")
    await reporter.start(auto_register=True)

    print("🚦 Simulation started")
    while True:
        await asyncio.sleep(1)

asyncio.run(main())
