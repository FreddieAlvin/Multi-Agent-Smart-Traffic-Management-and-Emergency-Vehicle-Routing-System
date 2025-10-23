from spade import agent, behaviour
from spade.message import Message
from environment.occupancy import occupied_cells, random_position

class EmergencyVehicleAgent(agent.Agent):
    def __init__(self, jid, password, name):
        super().__init__(jid, password)
        self.name = name
        self.position = random_position()

    class EmergencyBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            msg = Message(to="light1@localhost")  # or nearest light
            msg.set_metadata("type", "priority_request")
            msg.body = f"Emergency vehicle {self.agent.name} at {self.agent.position} needs priority"
            await self.send(msg)
            print(f"[{self.agent.name}] 🚑 Sent priority request")
            incoming = await self.receive(timeout=3)
            if incoming:
                print(f"[{self.agent.name}] 📩 Received: {incoming.body}")

    async def setup(self):
        occupied_cells.add(self.position)
        print(f"{self.name} (emergency) started at {self.position}")
        self.add_behaviour(self.EmergencyBehaviour(period=10))
