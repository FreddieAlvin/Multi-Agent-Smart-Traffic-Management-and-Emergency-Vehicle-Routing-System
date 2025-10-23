from spade import agent, behaviour
from spade.message import Message
import random
from environment.occupancy import GRID_SIZE

class IncidentReporterAgent(agent.Agent):
    class BroadcastBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            if random.random() < 0.4:
                pos = (random.randint(0, GRID_SIZE-1), random.randint(0, GRID_SIZE-1))
                msg = Message(to="vehicle1@localhost")
                msg.set_metadata("type", "incident_alert")
                msg.body = f"Accident reported near {pos}"
                await self.send(msg)
                print("[Reporter] 🚨 Broadcasted hazard alert")

    async def setup(self):
        print("Incident Reporter Agent started")
        self.add_behaviour(self.BroadcastBehaviour(period=8))
