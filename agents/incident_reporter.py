# agents/incident_reporter.py
import asyncio
import random
import time
import json
from spade import agent, behaviour
from spade.message import Message

class IncidentReporterAgent(agent.Agent):
    """
    Broadcasts temporary accidents / roadblocks AND updates the EventManager.
    Designed for decentralized coordination. Vehicles and traffic lights
    can receive incident gossip and adapt their routes.
    """

    def __init__(self, jid, password, city, event_manager):
        super().__init__(jid, password)
        self.city = city
        self.event_manager = event_manager

    class BroadcastBehaviour(behaviour.PeriodicBehaviour):
        async def run(self):
            city = self.agent.city
            em = self.agent.event_manager

            # 40% chance to spawn a new roadblock each cycle
            if random.random() < 0.4:

                # -------------------------------
                # 1. Pick a random road (edge)
                # -------------------------------
                edge = random.choice(list(city.graph.edges()))
                u, v = edge
                pos = city.node_positions.get(u, u)  # approximate location for logging

                # -------------------------------
                # 2. Create temporary roadblock
                # -------------------------------
                duration = 8.0  # seconds
                em.spawn_temporary_block((u, v), ttl=duration)

                # -------------------------------
                # 3. Prepare gossip message
                # -------------------------------
                payload = {
                    "edge": [list(u), list(v)],
                    "severity": 10.0,
                    "expires_at": time.time() + duration
                }

                message_body = json.dumps({
                    "type": "incident_gossip",
                    "hop_ttl": 4,  # max hops for gossip propagation
                    "payload": payload
                })

                # -------------------------------
                # 4. Broadcast to known agents (vehicles + traffic lights)
                # -------------------------------
                recipients = list(city.vehicle_jids) + list(city.traffic_light_jids)
                for r in recipients:
                    msg = Message(to=r)
                    msg.set_metadata("type", "incident_gossip")
                    msg.body = message_body
                    await self.send(msg)

                print(f"[Reporter] 🚨 Roadblock on {edge} broadcast to {len(recipients)} agents, duration {duration}s")

    async def setup(self):
        print("[Reporter] Incident Reporter Agent started")
        self.add_behaviour(self.BroadcastBehaviour(period=8))
