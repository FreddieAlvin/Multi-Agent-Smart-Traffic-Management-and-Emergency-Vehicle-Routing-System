from spade import agent, behaviour
from spade.message import Message
from environment.occupancy import occupied_cells, random_free_position, nearby_vehicle_count
from utils.routing import nearest_traffic_light

class VehicleAgent(agent.Agent):
    def __init__(self, jid, password, name):
        super().__init__(jid, password)
        self.name = name
        from environment.occupancy import random_position
        self.position = random_position()

    def move_randomly(self):
        old_pos = self.position
        new_pos = random_free_position(old_pos)
        if new_pos != old_pos:
            occupied_cells.add(new_pos)
            occupied_cells.discard(old_pos)
            self.position = new_pos
        else:
            occupied_cells.add(old_pos)
        return self.position

    class VehicleBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            old_pos = self.agent.position
            new_pos = self.agent.move_randomly()
            print(f"[{self.agent.name}] moved from {old_pos} to {new_pos}")

            # Check congestion
            neighbors = nearby_vehicle_count(new_pos)
            if neighbors >= 2:
                msg = Message(to="reporter@localhost")
                msg.set_metadata("type", "congestion_update")
                msg.body = f"Congestion at {new_pos} ({neighbors} nearby)"
                await self.send(msg)
                print(f"[{self.agent.name}] 🚗 Reported congestion")

            # Request passage at nearest traffic light
            light_jid = nearest_traffic_light(new_pos)
            msg = Message(to=light_jid)
            msg.set_metadata("type", "passage_request")
            msg.body = f"{self.agent.name} at {new_pos} requests passage"
            await self.send(msg)
            print(f"[{self.agent.name}] 🚦 Requested passage from {light_jid}")

            # Receive messages
            incoming = await self.receive(timeout=3)
            if incoming:
                print(f"[{self.agent.name}] 📩 Received: {incoming.body}")

    async def setup(self):
        occupied_cells.add(self.position)
        print(f"{self.name} started at {self.position}")
        self.add_behaviour(self.VehicleBehaviour(period=5))
