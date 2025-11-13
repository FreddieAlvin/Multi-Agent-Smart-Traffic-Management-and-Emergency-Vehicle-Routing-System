# agents/emergency_vehicle.py
import asyncio
import random
import networkx as nx
from spade import agent, behaviour
from spade.message import Message

def manhattan(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])


class EmergencyVehicleAgent(agent.Agent):
    """
    Emergency vehicle with smart A* routing:
      - A* over the city graph using dynamic edge costs
      - Priority requests to nearest traffic light
      - On arrival: brief pause, then either stop (fixed hospital) or choose a new far goal (patrol)
    """

    def __init__(self, jid, password, name, city_env, shared=None,
                 fixed_dest=None, pause_at_goal=1.0):
        """
        :param fixed_dest: (x,y) hospital node; if None -> continuous patrol
        """
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"emergency": {}}

        nodes = list(city_env.graph.nodes)
        self.position = random.choice(nodes)

        # Routing state
        self.fixed_dest = fixed_dest                # e.g., (10, 10) for a hospital
        self.goal = fixed_dest                      # start by aiming at hospital if provided
        self.path = []                               # current planned path
        self.steps_since_plan = 0
        self.replan_every = 6                        # a bit more eager than regular vehicles
        self.pause_at_goal = float(pause_at_goal)

        # make it visible immediately
        try:
            self.shared.setdefault("emergency", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE emergency init ERROR]", e)

    # ---------- dynamic cost (lighter congestion than cars) ----------
    def _dynamic_weight(self, u, v, d):
        base = d.get("weight", 1.0)
        try:
            occ = self.city.occupancy.edge_density(u, v)
        except Exception:
            occ = 0.0
        try:
            pen = self.city.event_manager.edge_penalty(u, v)
        except Exception:
            pen = 0.0
        # ambulance gets priority → congestion matters less; hazards still matter
        return base + 0.3 * occ + pen

    # ---------- goal helpers ----------
    def _choose_nearest_hospital(self):
        hospitals = getattr(self.city, "hospitals", None)
        if not hospitals:
            return None
        best = None
        best_d = None
        for h in hospitals:
            try:
                d = nx.shortest_path_length(self.city.graph, self.position, h)
                if best_d is None or d < best_d:
                    best_d, best = d, h
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
        return best

    def _choose_far_goal(self, min_manhattan=10):
        here = self.position
        candidates = [n for n in self.city.graph.nodes if n != here and manhattan(n, here) >= min_manhattan]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    # ---------- plan/step ----------
    def _plan_to(self, dest):
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
            print(f"[{self.label}] 🧭 planned path to {dest} (len={len(self.path)})")
        except Exception as e:
            print(f"[{self.label}] ❌ plan failed ({e}); using random next step")
            self.path = []

    def _step_along_path(self):
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                i = self.path.index(self.position)
                self.path = self.path[i:]
            else:
                return self._move_randomly()

        if len(self.path) >= 2:
            old = self.position
            self.position = self.path[1]
            self.path = self.path[1:]
            self.steps_since_plan += 1
            return old, self.position
        else:
            # at goal: keep singleton so arrival logic detects it
            self.path = [self.position]
            return self.position, self.position

    def _move_randomly(self):
        nbrs = list(self.city.graph.neighbors(self.position))
        old = self.position
        if nbrs:
            self.position = random.choice(nbrs)
        return old, self.position

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

            # Arrived?
            at_goal = (self.agent.goal is not None and self.agent.position == self.agent.goal)
            singleton_here = (len(self.agent.path) == 1 and self.agent.path[0] == self.agent.position)
            if at_goal or singleton_here:
                print(f"[{self.agent.label}] ✅ Reached goal {self.agent.goal}")
                await asyncio.sleep(self.agent.pause_at_goal)
                if self.agent.fixed_dest is not None:
                    # fixed destination (hospital): stay there
                    return
                # patrol mode: pick a new far goal and continue
                self.agent.goal = None
                self.agent.path = []
                self.agent.steps_since_plan = 0
                # fall through (next tick will plan)

            # Need a plan?
            need_plan = (
                (not self.agent.path)
                or (self.agent.goal is None)
                or (self.agent.steps_since_plan >= self.agent.replan_every)
            )
            if need_plan:
                if self.agent.fixed_dest is not None:
                    # always head to the fixed hospital
                    self.agent._plan_to(self.agent.fixed_dest)
                else:
                    # prefer nearest hospital if defined; else far patrol goal
                    dest = self.agent._choose_nearest_hospital() or self.agent._choose_far_goal()
                    self.agent._plan_to(dest)

            # Step
            old_pos, new_pos = (self.agent._step_along_path() if self.agent.path else self.agent._move_randomly())

            # Update viewer + occupancy
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                self.agent.shared.setdefault("emergency", {})[self.agent.label] = self.agent.position
            except Exception as e:
                print("[EMERGENCY UPDATE WARN]", e)

            print(f"[{self.agent.label}] 🚑 moved {old_pos} → {new_pos} (goal={self.agent.goal})")

            # Priority request to nearest light (retry once if booting)
            light_jid = self.agent._nearest_light_jid()
            req = Message(to=light_jid)
            req.set_metadata("type", "priority_request")
            req.body = f"Emergency vehicle {self.agent.label} at {new_pos} needs priority"
            await self.send(req)
            incoming = await self.receive(timeout=0.6)
            if not incoming:
                await asyncio.sleep(0.3)
                await self.send(req)
                incoming = await self.receive(timeout=0.6)

            if incoming:
                print(f"[{self.agent.label}] 📩 Received: {incoming.body}")
            else:
                print(f"[{self.agent.label}] ⚠️ No reply from {light_jid}")

    async def setup(self):
        print(f"{self.label} (emergency) started at {self.position}")
        # faster reaction than regular vehicles
        self.add_behaviour(self.EmergencyBehaviour(period=0.6))
