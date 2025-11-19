# agents/emergency_vehicle.py
import asyncio
import random
import networkx as nx
from spade import agent, behaviour
from spade.message import Message
import json


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class EmergencyVehicleAgent(agent.Agent):
    """
    Emergency vehicle with smart A* routing:
      - Avoids blocked edges reported in EventManager
      - A* with lighter congestion cost than regular vehicles
      - Priority requests to nearest traffic light
      - Pattern: hospital -> random far point -> hospital -> random -> ...
    """

    def __init__(self, jid, password, name, city_env, shared=None,
                 fixed_dest=None, pause_at_goal=2.0):
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"emergency": {}}

        # Initial position
        if fixed_dest is not None:
            self.position = fixed_dest
        else:
            self.position = random.choice(list(city_env.graph.nodes))

        self.fixed_dest = fixed_dest
        self.goal = None
        self.path = []
        self.steps_since_plan = 0
        self.pause_at_goal = float(pause_at_goal)

        # Phase: to_hospital or to_random
        if self.fixed_dest and self.position != self.fixed_dest:
            self.phase = "to_hospital"
        else:
            self.phase = "to_random"

        try:
            self.shared.setdefault("emergency", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE emergency init ERROR]", e)

    # ---------- dynamic edge weight ----------
    def _dynamic_weight(self, u, v, d):
        base = d.get("weight", 1.0)
        try:
            occ = self.city.occupancy.edge_density(u, v)
        except Exception:
            occ = 0.0
        try:
            pen = self.city.event_manager.penalty((u, v))
        except Exception:
            pen = 0.0
        return base + 0.3 * occ + pen  # congestion lighter for emergency, penalties still count

    # ---------- closest hospital ----------
    def _closest_hospital(self):
        hospitals = getattr(self.city, "hospitals", {}).values()
        if not hospitals:
            return None
        try:
            return min(hospitals, key=lambda h: manhattan(self.position, h))
        except Exception:
            return list(hospitals)[0]

    # ---------- far random goal ----------
    def _choose_far_goal(self, min_manhattan=10):
        here = self.position
        candidates = [n for n in self.city.graph.nodes if n != here and manhattan(n, here) >= min_manhattan]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    # ---------- plan A* ----------
    def _plan_to(self, dest):
        metrics = getattr(self.city, "metrics", None)
        if metrics:
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
            print(f"[{self.label}] 🧭 Planned path to {dest} (len={len(self.path)})")
        except Exception as e:
            print(f"[{self.label}] ❌ Plan failed ({e}); using random move")
            self.path = []
            self.goal = None

    # ---------- step along path ----------
    def _step_along_path(self):
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                i = self.path.index(self.position)
                self.path = self.path[i:]
            else:
                return self._move_randomly()

        if len(self.path) >= 2:
            next_edge = (self.path[0], self.path[1])
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
        nbrs = list(self.city.graph.neighbors(self.position))
        old = self.position
        if nbrs:
            self.position = random.choice(nbrs)
        return old, self.position

    # ---------- nearest traffic light ----------
    def _nearest_light_jid(self):
        lights = list(self.city.traffic_lights.values())
        if not lights:
            return "light1@localhost"
        try:
            best = min(lights, key=lambda l: nx.shortest_path_length(self.city.graph, self.position, l))
            return f"light_{best[0]}_{best[1]}@localhost"
        except Exception:
            return "light1@localhost"

    # ---------- behaviour ----------
    class EmergencyBehaviour(behaviour.PeriodicBehaviour):
        async def on_start(self):
            self.first_run = True

        async def run(self):
            if self.first_run:
                await asyncio.sleep(1.0)
                self.first_run = False

            # --- Merge incident updates ---
            try:
                incoming = await self.receive(timeout=0.2)
                if incoming and incoming.body:
                    payload = json.loads(incoming.body)
                    self.agent.city.event_manager.merge_from_message(payload)
                    print(f"[{self.agent.label}] 📩 Merged incident update: {payload}")
            except Exception as e:
                print("[EMERGENCY] Failed to merge incident:", e)

            # --- Arrival check ---
            at_goal = self.agent.goal and self.agent.position == self.agent.goal
            singleton_here = len(self.agent.path) == 1 and self.agent.path[0] == self.agent.position
            if at_goal or singleton_here:
                metrics = getattr(self.agent.city, "metrics", None)
                if metrics and self.agent.fixed_dest and self.agent.position != self.agent.fixed_dest:
                    metrics.end_emergency()

                await asyncio.sleep(self.agent.pause_at_goal)

                if self.agent.fixed_dest:
                    self.agent.phase = "to_random" if self.agent.position == self.agent.fixed_dest else "to_hospital"
                else:
                    hospitals = getattr(self.agent.city, "hospitals", None)
                    self.agent.phase = "to_random" if hospitals and self.agent.position in hospitals.values() else "to_hospital"

                self.agent.goal = None
                self.agent.path = []
                self.agent.steps_since_plan = 0
                return

            # --- Planning ---
            if not self.agent.path or self.agent.goal is None:
                metrics = getattr(self.agent.city, "metrics", None)
                if self.agent.fixed_dest:
                    dest = self.agent.fixed_dest if self.agent.phase == "to_hospital" else self.agent._choose_far_goal()
                    if metrics and self.agent.position == self.agent.fixed_dest and self.agent.phase == "to_random":
                        metrics.start_emergency()
                else:
                    dest = self.agent._closest_hospital() if self.agent.phase == "to_hospital" else self.agent._choose_far_goal()
                    if metrics and getattr(self.agent.city, "hospitals", None) and self.agent.position in self.agent.city.hospitals.values() and self.agent.phase == "to_random":
                        metrics.start_emergency()
                if dest:
                    self.agent._plan_to(dest)

            # --- Move one step ---
            old_pos, new_pos = self.agent._step_along_path()

            # --- Collision avoidance ---
            all_vehicles = self.agent.shared.get("vehicles", {})
            all_emergency = self.agent.shared.get("emergency", {})

            hospital = getattr(self.agent, "fixed_dest", None)
            at_hospital = hospital and new_pos == hospital

            occupied_by_vehicle = any(pos == new_pos for pos in all_vehicles.values())
            occupied_by_other_ambulance = any(pos == new_pos and name != self.agent.label for name, pos in all_emergency.items())

            must_block = occupied_by_vehicle or (occupied_by_other_ambulance and not at_hospital)
            if must_block:
                print(f"[{self.agent.label}] ⛔ Target {new_pos} occupied, staying at {old_pos}")
                self.agent.position = old_pos
                new_pos = old_pos
                self.agent.path = []
                self.agent.goal = None
                self.agent.steps_since_plan = 0

            # --- Update visualization / occupancy ---
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                self.agent.shared.setdefault("emergency", {})[self.agent.label] = self.agent.position
            except Exception as e:
                print("[EMERGENCY UPDATE WARN]", e)

            # --- Priority request to nearest light ---
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

            granted_flag = incoming.metadata.get("granted", "false") if incoming and incoming.metadata else "false"
            print(f"[{self.agent.label}] 📩 Traffic light reply: body={incoming.body if incoming else None}, granted={granted_flag}")

    async def setup(self):
        print(f"{self.label} (emergency) started at {self.position}")
        self.add_behaviour(self.EmergencyBehaviour(period=1.5))
