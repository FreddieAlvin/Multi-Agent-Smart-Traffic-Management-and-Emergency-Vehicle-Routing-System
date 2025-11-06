import random
import networkx as nx
from spade import agent, behaviour
from spade.message import Message

class VehicleAgent(agent.Agent):
    def __init__(self, jid, password, name, city_env):
        """
        :param jid: JID for the vehicle agent
        :param password: XMPP password
        :param name: Vehicle name (for identification)
        :param city_env: Instance of CityEnvironment
        """
        super().__init__(jid, password)
        self.name = name
        self.city = city_env
        self.position = random.choice(list(city_env.graph.nodes))

    # ---------------------------------------------------------------------
    # Movement and logic
    # ---------------------------------------------------------------------
    def move_randomly(self):
        """Move randomly to a neighboring node in the graph."""
        neighbors = list(self.city.graph.neighbors(self.position))
        if not neighbors:
            return self.position
        old_pos = self.position
        self.position = random.choice(neighbors)
        return old_pos, self.position

    def find_nearest_traffic_light(self):
        """Return nearest traffic light based on path length."""
        lights = list(self.city.traffic_lights.values())
        return min(lights, key=lambda l: nx.shortest_path_length(self.city.graph, self.position, l))

    def nearby_vehicle_count(self, all_positions):
        """Count nearby vehicles within one hop."""
        neighbors = list(self.city.graph.neighbors(self.position))
        return sum(1 for pos in all_positions if pos in neighbors)

    # ---------------------------------------------------------------------
    # Behaviour definition
    # ---------------------------------------------------------------------
    class VehicleBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            # Move vehicle
            old_pos, new_pos = self.agent.move_randomly()
            print(f"[{self.agent.name}] 🚗 moved from {old_pos} → {new_pos}")

            # Simple congestion detection
            # (You can replace this with a shared state manager later)
            all_positions = [self.agent.position]  # placeholder for nearby vehicles
            nearby_count = self.agent.nearby_vehicle_count(all_positions)

            if nearby_count >= 2:
                msg = Message(to="reporter@localhost")
                msg.set_metadata("type", "congestion_update")
                msg.body = f"Congestion detected near {new_pos} ({nearby_count} vehicles)"
                await self.send(msg)
                print(f"[{self.agent.name}] 🚦 Reported congestion at {new_pos}")

            # Request passage from nearest light
            nearest_light = self.agent.find_nearest_traffic_light()
            light_jid = f"light_{nearest_light[0]}_{nearest_light[1]}@localhost"
            msg = Message(to=light_jid)
            msg.set_metadata("type", "passage_request")
            msg.body = f"{self.agent.name} at {new_pos} requests passage"
            await self.send(msg)
            print(f"[{self.agent.name}] 🚧 Requested passage from {light_jid}")

            # Wait for reply
            incoming = await self.receive(timeout=3)
            if incoming:
                print(f"[{self.agent.name}] 📩 Received: {incoming.body}")

    # ---------------------------------------------------------------------
    # Setup
    # ---------------------------------------------------------------------
    async def setup(self):
        print(f"[{self.name}] Vehicle agent initialized at {self.position}")
        b = self.VehicleBehaviour(period=5)
        self.add_behaviour(b)