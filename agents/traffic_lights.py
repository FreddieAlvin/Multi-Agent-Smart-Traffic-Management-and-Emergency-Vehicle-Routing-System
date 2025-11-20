"""
traffic_lights.py

Implements the TrafficLightAgent, a SPADE agent that simulates an adaptive
traffic light in a grid-based smart-city environment.

Each traffic light:
  - Alternates between two phases:
        Phase 0: North/South movement allowed
        Phase 1: East/West movement allowed
  - Adapts its phase duration based on local road congestion
  - Responds to two types of requests:
        - priority_request (emergency vehicles)
        - passage_request (regular vehicles)
  - Integrates with the EventManager to block edges affected by incidents
  - Follows a Contract Net–style reply semantics (accept/reject proposals)

This file defines:
    direction() → Infer direction of movement from grid coordinates.
    TrafficLightAgent → SPADE agent controlling a single traffic light.
"""

import asyncio
import json
from spade import agent, behaviour
from spade.message import Message

# Phase definitions
ALLOWED_BY_PHASE = {
    0: {"N", "S"},   # Phase 0
    1: {"E", "W"},   # Phase 1
}

PHASE_DURATION = 5.0   # Default base duration in seconds


def direction(from_pos, to_pos):
    """
    Infer movement direction between two grid coordinates.

    Args:
        from_pos (tuple[int, int]): Current position (x, y).
        to_pos (tuple[int, int]): Next position (x, y).

    Returns:
        str | None:
            "N", "S", "E", or "W" depending on movement.
            None if movement is diagonal or zero.
    """
    (x1, y1) = from_pos
    (x2, y2) = to_pos
    dx = x2 - x1
    dy = y2 - y1

    if dx == 1 and dy == 0:
        return "E"
    if dx == -1 and dy == 0:
        return "W"
    if dx == 0 and dy == 1:
        return "N"
    if dx == 0 and dy == -1:
        return "S"

    return None



class TrafficLightAgent(agent.Agent):
    """
    Traffic light controller agent.

    This agent autonomously alternates between NS and EW phases, adjusts the
    duration of each phase according to observed traffic density, and processes
    vehicle passage requests.

    Attributes:
        city (CityEnvironment): The global environment object.
        shared (dict): Shared state dictionary for visualization.
        position (tuple[int, int] | None): Grid coordinate of the light.
        phase (int): Current phase (0=NS, 1=EW).
        phase_duration (float): Adaptive duration of the current phase.
        _last_switch (float): Time of last phase toggle.
    """

    def __init__(self, jid, password, city_env=None, shared=None):
        super().__init__(jid, password)
        self.city = city_env
        self.shared = shared or {}
        self.position = None
        self.phase_duration = PHASE_DURATION
        self.phase = 0
        self._last_switch = 0.0

    class LightBehaviour(behaviour.CyclicBehaviour):
        """
        Cyclic behaviour controlling the traffic-light loop.

        Responsibilities:
            1. Adapt phase duration using local traffic density.
            2. Toggle phase when time expires.
            3. Process passage requests (regular or emergency).
            4. Use Contract Net semantics for responses.
        """

        async def on_start(self):
            """Initializes light phase and timestamp."""
            self.agent.phase = 0
            self.agent._last_switch = asyncio.get_event_loop().time()
            print(
                f"[Traffic Light {self.agent.jid}] 🚦 started in phase "
                f"{self.agent.phase}"
            )

        async def run(self):
            """Main control loop executed repeatedly."""
            now = asyncio.get_event_loop().time()

            # -------------------------------------------------------
            # 1) Adapt duration using local traffic density
            # -------------------------------------------------------
            if getattr(self.agent, "city", None) and self.agent.position:
                try:
                    rho = self.agent.city.occupancy.local_density(
                        self.agent.position,
                        radius=2,
                    )
                    self.agent.phase_duration = max(
                        3.0, min(8.0, 3.0 + 5.0 * float(rho))
                    )
                except Exception as e:
                    print(f"[Traffic Light {self.agent.jid}] ⚠️ density adapt error: {e}")
                    self.agent.phase_duration = PHASE_DURATION

            # -------------------------------------------------------
            # 2) Toggle phase if duration expired
            # -------------------------------------------------------
            if now - self.agent._last_switch >= self.agent.phase_duration:
                self.agent.phase = 1 - self.agent.phase
                self.agent._last_switch = now
                print(
                    f"[Traffic Light {self.agent.jid}] 🔄 Switched to phase {self.agent.phase} "
                    f"(allowed={ALLOWED_BY_PHASE[self.agent.phase]}, "
                    f"duration={self.agent.phase_duration:.1f}s)"
                )

            # -------------------------------------------------------
            # 3) Handle incoming passage requests
            # -------------------------------------------------------
            msg = await self.receive(timeout=0.1)
            if not msg:
                return

            mtype = msg.metadata.get("type") if msg.metadata else None

            # Parse body safely
            try:
                payload = json.loads(msg.body)
                from_pos = tuple(payload["from"])
                to_pos = tuple(payload["to"])
            except Exception:
                print(
                    f"[Traffic Light {self.agent.jid}] ⚠️ Invalid message body: "
                    f"{msg.body}"
                )
                await self._reply(msg, granted=False, reason="invalid_body")
                return

            # Emergency: always granted
            if mtype == "priority_request":
                print(
                    f"[Traffic Light {self.agent.jid}] 🚑 Priority request "
                    f"{from_pos}->{to_pos} -> GRANTED"
                )
                await self._reply(msg, granted=True, reason="emergency")
                return

            # Non-emergency vehicle
            d = direction(from_pos, to_pos)
            if d is None:
                print(
                    f"[Traffic Light {self.agent.jid}] ❌ Unknown direction "
                    f"{from_pos}->{to_pos}"
                )
                await self._reply(msg, granted=False, reason="unknown_direction")
                return

            allowed_dirs = ALLOWED_BY_PHASE[self.agent.phase]
            granted = d in allowed_dirs
            reason = "phase_check"

            # Incident check (blocked edge)
            if getattr(self.agent.city, "event_manager", None):
                edge = (from_pos, to_pos)
                if self.agent.city.event_manager.is_blocked(edge):
                    granted = False
                    reason = "blocked_by_incident"
                    print(
                        f"[Traffic Light {self.agent.jid}] 🚧 Edge {edge} blocked by incident -> DENIED"
                    )

            print(
                f"[Traffic Light {self.agent.jid}] 🚗 Request {from_pos}->{to_pos} "
                f"dir={d} phase={self.agent.phase} allowed={allowed_dirs} -> "
                f"{'GRANTED' if granted else 'DENIED'} (reason={reason})"
            )

            await self._reply(msg, granted=granted, reason=reason)

        async def _reply(self, msg, granted: bool, reason: str = ""):
            """
            Send a Contract Net–style reply to a vehicle or ambulance.

            Args:
                msg (Message): Incoming request message.
                granted (bool): Whether passage is allowed.
                reason (str): Explanation for logging.
            """
            reply = Message(to=str(msg.sender))
            reply.set_metadata("type", "passage_reply")
            reply.set_metadata("protocol", "contract-net")

            mtype = msg.metadata.get("type") if msg.metadata else None
            if mtype == "priority_request":
                reply.set_metadata("performative", "accept-proposal")
            else:
                reply.set_metadata(
                    "performative",
                    "accept-proposal" if granted else "reject-proposal",
                )

            reply.set_metadata("granted", "true" if granted else "false")
            if reason:
                reply.set_metadata("reason", reason)

            reply.body = "granted" if granted else "denied"
            await self.send(reply)
            await asyncio.sleep(1.5)

    async def setup(self):
        """
        Initializes the traffic-light agent.

        Extracts its grid position from its JID (e.g., 'light_4_8@localhost'),
        sets initial timing parameters, and registers the behaviour loop.
        """
        print(f"Traffic Light Agent {self.jid} ready")

        if self.city:
            lid = str(self.jid).split("@")[0]
            self.position = self.city.traffic_lights.get(lid)

        self.phase_duration = PHASE_DURATION
        self.add_behaviour(self.LightBehaviour())
