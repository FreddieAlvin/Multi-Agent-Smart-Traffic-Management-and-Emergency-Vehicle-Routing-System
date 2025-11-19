import asyncio
import random
import json  # for communication with traffic lights
import re

import networkx as nx
from spade import agent, behaviour
from spade.message import Message

# If your IncidentReporter sets msg.set_metadata("type", "incident"), set this True.
# If not, leave False and we'll fall back to a text-only peek that won't crash movement.
USE_FILTERED_INCIDENTS = False
try:
    from spade.template import Template
except Exception:
    Template = None
    USE_FILTERED_INCIDENTS = False


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class VehicleAgent(agent.Agent):
    def __init__(self, jid, password, name, city_env, shared=None):
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"vehicles": {}}

        nodes = list(city_env.graph.nodes)
        self.position = random.choice(nodes)

        # Routing state
        self.goal = None
        self.path = []              # list of nodes (including current + goal)
        self.steps_since_plan = 0
        self.replan_every = 10      # periodic replan safety net

        # Initialize shared occupancy
        try:
            self.shared.setdefault("vehicles", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE vehicle init ERROR]", e)

    # ---------------- Helpers ----------------
    def _dynamic_weight(self, u, v, d):
        base = d.get("weight", 1.0)

        # occupancy
        try:
            occ = self.city.occupancy.edge_density(u, v)
        except Exception:
            occ = 0.0

        # incidents / roadblocks
        try:
            pen = self.city.event_manager.edge_penalty(u, v)
        except Exception:
            pen = 0.0

        return base + 0.6 * occ + pen

    def _choose_far_goal(self):
        here = self.position
        candidates = [n for n in self.city.graph.nodes if n != here and manhattan(n, here) >= 8]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    def _plan_to(self, dest):
        metrics = getattr(self.city, "metrics", None)
        if metrics is not None:
            metrics.log_replan(self.label)
        try:
            self.path = nx.astar_path(
                self.city.graph,
                self.position,
                dest,
                heuristic=manhattan,
                weight=lambda u, v, d: self._dynamic_weight(u, v, d)
            )
            self.goal = dest
            self.steps_since_plan = 0
            print(f"[{self.label}] 🧭 planned path to {dest} (len={len(self.path)})")
        except Exception as e:
            print(f"[{self.label}] ❌ plan failed ({e}); fallback random")
            self.path = []
            self.goal = None

    def _step_along_path(self):
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                idx = self.path.index(self.position)
                self.path = self.path[idx:]
            else:
                return self._move_randomly()

        if len(self.path) >= 2:
            next_edge = (self.path[0], self.path[1])
            # check for blocked edges / incidents
            if self.city.event_manager.is_blocked(next_edge):
                print(f"[{self.label}] ⛔ Edge {next_edge} blocked, waiting and replanning")
                self.path = []
                self.goal = None
                return self.position, self.position

            old = self.position
            self.position = self.path[1]
            self.path = self.path[1:]
            self.steps_since_plan += 1
            return old, self.position
        else:
            self.path = [self.position]
            return self.position, self.position

    def _move_randomly(self):
        neighbors = list(self.city.graph.neighbors(self.position))
        old = self.position
        if neighbors:
            self.position = random.choice(neighbors)
        return old, self.position

    def _nearest_light_jid(self):
        lights = list(self.city.traffic_lights.values())
        if not lights:
            return "light1@localhost"
        try:
            best = min(
                lights,
                key=lambda l: nx.shortest_path_length(self.city.graph, self.position, l)
            )
            return f"light_{best[0]}_{best[1]}@localhost"
        except Exception:
            return "light1@localhost"

    def _peek_next_step(self):
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                idx = self.path.index(self.position)
                self.path = self.path[idx:]
            else:
                return self.position, self.position

        if len(self.path) >= 2:
            return self.position, self.path[1]
        else:
            return self.position, self.position

    def _light_jid_for(self, node):
        for lid, pos in self.city.traffic_lights.items():
            if pos == node:
                return f"{lid}@localhost"
        return None

    # ---------------- Behaviour ----------------
    class VehicleBehaviour(behaviour.PeriodicBehaviour):
        async def on_start(self):
            self.first_run = True

        async def _wait_for_green(self, from_pos, to_pos):
            light_jid = self.agent._light_jid_for(to_pos)
            if not light_jid:
                return

            while True:
                req = Message(to=light_jid)
                req.set_metadata("type", "passage_request")
                req.set_metadata("protocol", "contract-net")
                req.set_metadata("performative", "cfp")
                req.body = json.dumps({"from": list(from_pos), "to": list(to_pos)})
                await self.send(req)
                incoming = await self.receive(timeout=0.8)

                if not incoming:
                    print(f"[{self.agent.label}] ⚠️ No reply from {light_jid}, retrying...")
                    await asyncio.sleep(0.4)
                    continue

                granted_flag = incoming.metadata.get("granted", "false") if incoming.metadata else "false"
                granted = (granted_flag == "true")
                performative = incoming.metadata.get("performative", "?") if incoming.metadata else "?"

                print(f"[{self.agent.label}] 📩 Traffic light reply: body={incoming.body}, granted={granted_flag}, perf={performative}")
                if granted:
                    return
                await asyncio.sleep(0.5)

        async def run(self):
            if self.first_run:
                await asyncio.sleep(1.5)
                self.first_run = False

            metrics = getattr(self.agent.city, "metrics", None)

            # Arrival handling
            at_goal = self.agent.goal is not None and self.agent.position == self.agent.goal
            singleton_here = len(self.agent.path) == 1 and self.agent.path[0] == self.agent.position
            if at_goal or singleton_here:
                print(f"[{self.agent.label}] ✅ Reached {self.agent.goal}, pausing 3s...")
                if metrics is not None and self.agent.goal is not None:
                    metrics.end_trip(self.agent.label)
                await asyncio.sleep(3)
                self.agent.goal = None
                self.agent.path = []
                self.agent.steps_since_plan = 0
                return

            # Plan if needed
            need_plan = (not self.agent.path) or (self.agent.goal is None) or (self.agent.steps_since_plan >= self.agent.replan_every)

            # Incident-aware replan
            incident_near = False
            try:
                incident_msg = None
                if USE_FILTERED_INCIDENTS and Template is not None:
                    incident_msg = await self.receive(timeout=0.01, filter=Template(metadata={"type": "incident"}))
                else:
                    candidate = await self.receive(timeout=0.01)
                    if candidate and isinstance(candidate.body, str) and "Accident reported near" in candidate.body:
                        incident_msg = candidate

                if incident_msg and isinstance(incident_msg.body, str):
                    m = re.search(r"\((\d+),\s*(\d+)\)", incident_msg.body)
                    if m:
                        p = (int(m.group(1)), int(m.group(2)))
                        if manhattan(p, self.agent.position) <= 4:
                            incident_near = True
                            print(f"[{self.agent.label}] 🔁 Rerouting due to incident at {p}")
            except Exception as e:
                print("[INCIDENT CHECK WARN]", e)

            if need_plan or (incident_near and self.agent.goal is not None and self.agent.position != self.agent.goal):
                if self.agent.goal is None:
                    self.agent.goal = self.agent._choose_far_goal()
                    if metrics is not None:
                        metrics.start_trip(self.agent.label)
                self.agent._plan_to(self.agent.goal)

            # Move along path
            if self.agent.path:
                old_pos, candidate_new = self.agent._peek_next_step()
                if old_pos != candidate_new:
                    await self._wait_for_green(old_pos, candidate_new)

                    all_vehicles = self.agent.shared.get("vehicles", {})
                    all_emergency = self.agent.shared.get("emergency", {})
                    others = {**all_vehicles, **all_emergency}
                    occupied = any(pos == candidate_new and name != self.agent.label for name, pos in others.items())

                    if occupied:
                        print(f"[{self.agent.label}] ⛔ target {candidate_new} occupied, staying at {old_pos}")
                        new_pos = old_pos
                        self.agent.path = []
                        self.agent.goal = None
                        self.agent.steps_since_plan = 0
                    else:
                        self.agent.position = candidate_new
                        if self.agent.position in self.agent.path:
                            idx = self.agent.path.index(self.agent.position)
                            self.agent.path = self.agent.path[idx:]
                        else:
                            self.agent.path = [self.agent.position]
                        self.agent.steps_since_plan += 1
                        new_pos = self.agent.position
                else:
                    old_pos, new_pos = self.agent._move_randomly()
            else:
                old_pos, new_pos = self.agent._move_randomly()

            # Occupancy update
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                if hasattr(self.agent.city, "update_edge_weights"):
                    self.agent.city.update_edge_weights()
            except Exception as e:
                print("[OCCUPANCY/WEIGHTS ERROR]", e)

            # Viewer update
            try:
                self.agent.shared.setdefault("vehicles", {})[self.agent.label] = self.agent.position
            except Exception as e:
                print("[VIS-WRITE vehicle tick ERROR]", e)

            print(f"[{self.agent.label}] 🚗 moved {old_pos} → {new_pos} (goal={self.agent.goal})")

    async def setup(self):
        print(f"[{self.label}] Vehicle agent initialized at {self.position}")
        self.add_behaviour(self.VehicleBehaviour(period=1.5))
