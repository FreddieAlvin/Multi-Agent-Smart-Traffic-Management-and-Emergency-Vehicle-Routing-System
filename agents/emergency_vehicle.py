"""
Emergency vehicle agent module.

This module defines the EmergencyVehicleAgent, a SPADE autonomous agent that
implements intelligent emergency response behavior in the simulation.

Key features:
    - A* routing with reduced congestion penalties (faster navigation)
    - Avoidance of blocked edges reported by EventManager
    - Automatic switching between "to_hospital" and "to_random" phases
    - Traffic-light priority negotiation
    - Integration with the Metrics system to track emergency response time
    - Incident gossip handling (merging distributed incident information)

This agent continuously cycles:
    hospital → random incident → hospital → random incident → ...
"""

import asyncio
import random
import json

import networkx as nx
from spade import agent, behaviour
from spade.message import Message


def manhattan(a, b):
    """Return the Manhattan distance between two (x, y) points."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class EmergencyVehicleAgent(agent.Agent):
    """
    Autonomous emergency vehicle with priority-aware routing.

    This agent simulates an ambulance or emergency responder. It travels between
    hospitals and random points in the city using A* pathfinding, dynamically
    adapting to congestion and incidents.

    Features:
        - Avoids blocked edges reported by EventManager.
        - Negotiates priority with traffic lights.
        - Uses congestion-aware edge weights.
        - Sends/receives incident gossip updates.
        - Triggers metric collection for emergency response time.

    Attributes:
        label (str): Human-readable name.
        city (CityEnvironment): Shared simulation environment.
        shared (dict): Shared position dictionary for visualization.
        position (tuple): Current (x, y) grid coordinate.
        fixed_dest (tuple | None): Optional dedicated hospital node.
        goal (tuple | None): Current navigation target.
        path (list[tuple]): Planned A* route.
        steps_since_plan (int): Counter for replan detection.
        pause_at_goal (float): Delay after reaching an endpoint.
        phase (str): Either "to_hospital" or "to_random".
    """

    def __init__(self, jid, password, name, city_env, shared=None,
                 fixed_dest=None, pause_at_goal=2.0):
        """
        Initialize the emergency vehicle agent.

        Args:
            jid (str): Agent JID.
            password (str): Authentication password.
            name (str): Human-readable label (e.g. "Ambulance 1").
            city_env (CityEnvironment): Reference to the city environment.
            shared (dict | None): Shared visualization state.
            fixed_dest (tuple | None): Station / hospital node. If None,
                any hospital is used as a base.
            pause_at_goal (float): Pause duration at each target.
        """
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"emergency": {}}

        # Initial spawn position
        if fixed_dest is not None:
            self.position = fixed_dest
        else:
            self.position = random.choice(list(city_env.graph.nodes))

        self.fixed_dest = fixed_dest
        self.goal = None
        self.path = []
        self.steps_since_plan = 0
        self.pause_at_goal = float(pause_at_goal)

        # Determine initial phase
        hospitals = getattr(self.city, "hospitals", {})
        hospital_positions = set(hospitals.values()) if hospitals else set()

        if self.fixed_dest:
            self.phase = (
                "to_hospital"
                if self.position != self.fixed_dest
                else "to_random"
            )
        else:
            self.phase = (
                "to_random"
                if hospital_positions and self.position in hospital_positions
                else "to_hospital"
            )

        # Register initial position for the visualizer
        try:
            self.shared.setdefault("emergency", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE emergency init ERROR]", e)

    # ----------------------------------------------------------------------
    # Routing helpers
    # ----------------------------------------------------------------------
    def _dynamic_weight(self, u, v, d):
        """
        Compute the dynamic weight of a road segment for A* routing.

        Emergency vehicles have lighter congestion penalties than normal cars
        but still respect incident penalties.

        Args:
            u (tuple): Starting node.
            v (tuple): Ending node.
            d (dict): Edge attribute dictionary.

        Returns:
            float: Effective weight.
        """
        base = d.get("weight", 1.0)

        try:
            occ = self.city.occupancy.edge_density(u, v)
        except Exception:
            occ = 0.0

        try:
            pen = self.city.event_manager.edge_penalty(u, v)
        except Exception:
            pen = 0.0

        return base + 0.3 * occ + pen

    def _closest_hospital(self):
        """
        Return the closest hospital node to the current position.

        Returns:
            tuple | None: (x, y) of the closest hospital, or None.
        """
        hospitals = getattr(self.city, "hospitals", {}).values()
        if not hospitals:
            return None
        try:
            return min(hospitals, key=lambda h: manhattan(self.position, h))
        except Exception:
            return list(hospitals)[0]

    def _choose_far_goal(self, min_manhattan=10):
        """
        Select a far-away random grid node as the next target.

        Args:
            min_manhattan (int): Required Manhattan distance.

        Returns:
            tuple: Selected node coordinate.
        """
        here = self.position
        candidates = [
            n for n in self.city.graph.nodes
            if n != here and manhattan(n, here) >= min_manhattan
        ]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    def _plan_to(self, dest):
        """
        Plan a path to the given destination using A*.

        Args:
            dest (tuple): Target node coordinate.
        """
        metrics = getattr(self.city, "metrics", None)
        if metrics:
            metrics.log_replan(self.label)

        try:
            self.path = nx.astar_path(
                self.city.graph,
                self.position,
                dest,
                heuristic=manhattan,
                weight=lambda u, v, d: self._dynamic_weight(u, v, d),
            )
            self.goal = dest
            self.steps_since_plan = 0
            print(f"[{self.label}] 🧭 Planned path to {dest} (len={len(self.path)})")
        except Exception as e:
            print(f"[{self.label}] ❌ Plan failed ({e}); using random move")
            self.path = []
            self.goal = None

    def _step_along_path(self):
        """
        Move one step along the planned A* path.

        Returns:
            tuple: (old_pos, new_pos)
        """
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                i = self.path.index(self.position)
                self.path = self.path[i:]
            else:
                return self._move_randomly()

        if len(self.path) >= 2:
            curr = self.path[0]
            nxt = self.path[1]

            # Blocked edge check
            try:
                if self.city.event_manager.is_blocked((curr, nxt)):
                    print(f"[{self.label}] ⛔ Edge {(curr, nxt)} blocked, waiting and replanning")
                    self.path = []
                    self.goal = None
                    return self.position, self.position
            except Exception:
                pass

            old = self.position
            self.position = nxt
            self.path = self.path[1:]
            self.steps_since_plan += 1
            return old, self.position

        # At destination or path exhausted
        return self.position, self.position

    def _move_randomly(self):
        """
        Take a random step when no path exists.

        Returns:
            tuple: (old_pos, new_pos)
        """
        nbrs = list(self.city.graph.neighbors(self.position))
        old = self.position
        if nbrs:
            self.position = random.choice(nbrs)
        return old, self.position

    def _nearest_light_jid(self):
        """
        Determine the JID of the nearest traffic light.

        Returns:
            str: Traffic light JID.
        """
        lights = list(self.city.traffic_lights.values())
        if not lights:
            return "light1@localhost"
        try:
            best = min(
                lights,
                key=lambda l: nx.shortest_path_length(self.city.graph, self.position, l),
            )
            return f"light_{best[0]}_{best[1]}@localhost"
        except Exception:
            return "light1@localhost"

    # ----------------------------------------------------------------------
    # Behaviour
    # ----------------------------------------------------------------------
    class EmergencyBehaviour(behaviour.PeriodicBehaviour):
        """
        Periodic behaviour controlling movement, replanning, incident gossip
        ingestion, priority negotiation, emergency timing, and collision
        avoidance for the emergency vehicle.
        """

        async def on_start(self):
            """Executed once when the behaviour begins."""
            self.first_run = True

        async def run(self):
            """
            Main loop executed periodically:
                - read incident gossip
                - perform arrival checks and phase switching
                - plan new routes when needed
                - step along A* path
                - manage collisions
                - request priority from nearest traffic light
                - log emergency start/end for metrics
            """
            if self.first_run:
                await asyncio.sleep(1.0)
                self.first_run = False

            metrics = getattr(self.agent.city, "metrics", None)
            hospitals = getattr(self.agent.city, "hospitals", {})
            hospital_positions = set(hospitals.values()) if hospitals else set()

            # --------------------------------------------------------------
            # Merge incoming incident gossip (JSON messages)
            # --------------------------------------------------------------
            incoming = await self.receive(timeout=0.2)

            if incoming and incoming.body:
                try:
                    data = json.loads(incoming.body)
                except Exception:
                    data = None

                if isinstance(data, dict) and data.get("type") == "incident_gossip":
                    payload = data.get("payload")
                    if payload:
                        try:
                            self.agent.city.event_manager.merge_from_message(payload)
                            print(f"[{self.agent.label}] 📩 Merged incident update: {payload}")
                        except Exception as e:
                            print("[EMERGENCY] Failed to merge incident:", e)

            # --------------------------------------------------------------
            # Arrival check (hospital or random target)
            # --------------------------------------------------------------
            at_goal = self.agent.goal and self.agent.position == self.agent.goal
            singleton_here = (
                len(self.agent.path) == 1
                and self.agent.path[0] == self.agent.position
            )

            if at_goal or singleton_here:
                # Record EV response completion
                if metrics:
                    if self.agent.fixed_dest:
                        if (
                            self.agent.position == self.agent.fixed_dest
                            and self.agent.phase == "to_hospital"
                        ):
                            metrics.end_emergency()
                    else:
                        if (
                            hospital_positions
                            and self.agent.position in hospital_positions
                            and self.agent.phase == "to_hospital"
                        ):
                            metrics.end_emergency()

                await asyncio.sleep(self.agent.pause_at_goal)

                # Phase switch
                if self.agent.fixed_dest:
                    self.agent.phase = (
                        "to_random"
                        if self.agent.position == self.agent.fixed_dest
                        else "to_hospital"
                    )
                else:
                    self.agent.phase = (
                        "to_random"
                        if hospital_positions and self.agent.position in hospital_positions
                        else "to_hospital"
                    )

                self.agent.goal = None
                self.agent.path = []
                self.agent.steps_since_plan = 0
                return

            # --------------------------------------------------------------
            # Route planning ⇢ choose destination and maybe start emergency
            # --------------------------------------------------------------
            if not self.agent.path or self.agent.goal is None:
                dest = None

                if self.agent.fixed_dest:
                    # Hospital <-> random
                    dest = (
                        self.agent.fixed_dest
                        if self.agent.phase == "to_hospital"
                        else self.agent._choose_far_goal()
                    )

                    if (
                        metrics
                        and self.agent.position == self.agent.fixed_dest
                        and self.agent.phase == "to_random"
                    ):
                        metrics.start_emergency()

                else:
                    # Any hospital works
                    dest = (
                        self.agent._closest_hospital()
                        if self.agent.phase == "to_hospital"
                        else self.agent._choose_far_goal()
                    )

                    if (
                        metrics
                        and hospital_positions
                        and self.agent.position in hospital_positions
                        and self.agent.phase == "to_random"
                    ):
                        metrics.start_emergency()

                if dest:
                    self.agent._plan_to(dest)

            # --------------------------------------------------------------
            # Move one planned step
            # --------------------------------------------------------------
            old_pos, new_pos = self.agent._step_along_path()

            # --------------------------------------------------------------
            # Collision avoidance:
            #   - avoid cars
            #   - avoid other ambulances unless arriving at hospital
            # --------------------------------------------------------------
            all_vehicles = self.agent.shared.get("vehicles", {})
            all_emergency = self.agent.shared.get("emergency", {})

            at_hospital_node = (
                (self.agent.fixed_dest and new_pos == self.agent.fixed_dest)
                or (
                    not self.agent.fixed_dest
                    and hospital_positions
                    and new_pos in hospital_positions
                )
            )

            occupied_by_vehicle = any(pos == new_pos for pos in all_vehicles.values())
            occupied_by_other_ambulance = any(
                pos == new_pos and name != self.agent.label
                for name, pos in all_emergency.items()
            )

            must_block = (
                occupied_by_vehicle
                or (occupied_by_other_ambulance and not at_hospital_node)
            )

            if must_block:
                print(f"[{self.agent.label}] ⛔ Target {new_pos} occupied, staying at {old_pos}")
                self.agent.position = old_pos
                new_pos = old_pos
                self.agent.path = []
                self.agent.goal = None
                self.agent.steps_since_plan = 0

            # --------------------------------------------------------------
            # Occupancy + visualization update
            # --------------------------------------------------------------
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                self.agent.shared.setdefault("emergency", {})[self.agent.label] = self.agent.position
            except Exception as e:
                print("[EMERGENCY UPDATE WARN]", e)

            # --------------------------------------------------------------
            # Priority request to traffic light
            # --------------------------------------------------------------
            light_jid = self.agent._nearest_light_jid()

            req = Message(to=light_jid)
            req.set_metadata("type", "priority_request")
            req.body = json.dumps({"from": list(old_pos), "to": list(new_pos)})

            await self.send(req)

            incoming = await self.receive(timeout=0.6)
            if not incoming:
                await asyncio.sleep(0.3)
                await self.send(req)
                incoming = await self.receive(timeout=0.6)

            granted_flag = (
                incoming.metadata.get("granted", "false")
                if incoming and incoming.metadata
                else "false"
            )
            print(
                f"[{self.agent.label}] 📩 Traffic light reply: "
                f"body={incoming.body if incoming else None}, granted={granted_flag}"
            )

    async def setup(self):
        """Attach and start the EmergencyBehaviour on agent startup."""
        print(f"{self.label} (emergency) started at {self.position}")
        self.add_behaviour(self.EmergencyBehaviour(period=1.5))
