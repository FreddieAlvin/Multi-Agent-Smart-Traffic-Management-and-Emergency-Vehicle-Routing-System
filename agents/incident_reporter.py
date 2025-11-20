# agents/incident_reporter.py
import asyncio
import random
import time
import json
from spade import agent, behaviour
from spade.message import Message


class IncidentReporterAgent(agent.Agent):
    """
    Agent responsible for generating and broadcasting temporary incidents
    (roadblocks) to all system agents. It periodically selects a random
    edge in the road network, marks it as blocked, and gossips this update
    to vehicles and traffic lights.

    Responsibilities:
        • Randomly inject temporary roadblock events into the environment.
        • Update the shared EventManager so that pathfinding avoids the edge.
        • Broadcast incident gossip in JSON format to all known agents.
        • Enable decentralized awareness of accidents across the system.

    Parameters:
        jid (str): Jabber/XMPP identifier for the SPADE agent.
        password (str): SPADE agent password.
        city (CityEnvironment): Shared environment containing the road graph
            and agent registries.
        event_manager (EventManager): Component storing incident states and
            providing lookup utilities.
    """

    def __init__(self, jid, password, city, event_manager):
        super().__init__(jid, password)
        self.city = city
        self.event_manager = event_manager

    class BroadcastBehaviour(behaviour.PeriodicBehaviour):
        """
        Periodic behaviour that creates and broadcasts temporary incidents.
        Every cycle, with a configurable probability, a random road segment
        is selected and marked as blocked for a short duration.

        Responsibilities:
            • Select a random edge from the city's road graph.
            • Create a temporary incident using EventManager.
            • Construct an incident gossip payload in JSON format.
            • Broadcast the update to all vehicles and traffic lights.

        Message Format:
            {
                "type": "incident_gossip",
                "hop_ttl": <remaining hops>,
                "payload": {
                    "edge": [[x1, y1], [x2, y2]],
                    "severity": <severity value>,
                    "expires_at": <unix timestamp>
                }
            }
        """

        async def run(self):
            city = self.agent.city
            em = self.agent.event_manager

            # 40% chance to generate a new temporary incident
            if random.random() < 0.4:
                edge = random.choice(list(city.graph.edges()))
                u, v = edge

                duration = 8.0
                em.spawn_temporary_block((u, v), ttl=duration)

                payload = {
                    "edge": [list(u), list(v)],
                    "severity": 10.0,
                    "expires_at": time.time() + duration
                }

                message_body = json.dumps({
                    "type": "incident_gossip",
                    "hop_ttl": 4,
                    "payload": payload
                })

                recipients = list(city.vehicle_jids) + list(city.traffic_light_jids)
                for r in recipients:
                    msg = Message(to=r)
                    msg.set_metadata("type", "incident_gossip")
                    msg.body = message_body
                    await self.send(msg)

                print(f"[Reporter] 🚨 Roadblock on {edge} broadcast to {len(recipients)} agents, duration {duration}s")

    async def setup(self):
        """
        Initializes the Incident Reporter and starts its periodic broadcast
        behaviour. This behaviour runs every 8 seconds and may generate new
        incidents depending on random chance.

        Responsibilities:
            • Register BroadcastBehaviour with SPADE runtime.
            • Print startup diagnostics to console.
        """
        print("[Reporter] Incident Reporter Agent started")
        self.add_behaviour(self.BroadcastBehaviour(period=8))
