# agents/incident_reporter.py
from spade import agent, behaviour
from spade.message import Message
import random

GRID_W = GRID_H = 20  # match CityEnvironment defaults

class IncidentReporterAgent(agent.Agent):
    class BroadcastBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            if random.random() < 0.4:
                pos = (random.randint(0, GRID_W-1), random.randint(0, GRID_H-1))
                msg = Message(to="vehicle1@localhost")
                msg.set_metadata("type", "incident_alert")
                msg.body = f"Accident reported near {pos}"
                await self.send(msg)
                print("[Reporter] 🚨 Broadcasted hazard alert")

    async def setup(self):
        print("Incident Reporter Agent started")
        self.add_behaviour(self.BroadcastBehaviour(period=8))
