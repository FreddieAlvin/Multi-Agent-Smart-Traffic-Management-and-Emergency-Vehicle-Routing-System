# agents/emergency_vehicle.py
import asyncio
import random
import networkx as nx
from spade import agent, behaviour
from spade.message import Message
import json  # para falar com os semáforos em JSON


def manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class EmergencyVehicleAgent(agent.Agent):
    """
    Emergency vehicle with smart A* routing:
      - A* with lighter congestion cost than regular vehicles
      - Priority requests to nearest traffic light
      - Pattern: hospital -> random far point -> hospital -> random -> ...
    """

    def __init__(self, jid, password, name, city_env, shared=None,
                 fixed_dest=None, pause_at_goal=2.0):
        """
        :param fixed_dest: (x,y) hospital node.
        :param pause_at_goal: seconds to pause at each goal.
        """
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"emergency": {}}

        # Se tivermos hospital definido, começamos no hospital
        # (cumpre o requisito: sair do hospital para destinos aleatórios)
        if fixed_dest is not None:
            self.position = fixed_dest
        else:
            nodes = list(city_env.graph.nodes)
            self.position = random.choice(nodes)

        # Routing state
        self.fixed_dest = fixed_dest          # hospital
        self.goal = None                      # chosen by phase
        self.path = []                        # current planned path
        self.steps_since_plan = 0             # unused now, but kept if you want stats
        self.pause_at_goal = float(pause_at_goal)

        # Phase: "to_hospital" or "to_random"
        if self.fixed_dest is not None and self.position != self.fixed_dest:
            self.phase = "to_hospital"
        else:
            # se nascemos no hospital ou não houver hospital, começamos por ir para random
            self.phase = "to_random"

        # visible immediately
        try:
            self.shared.setdefault("emergency", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE emergency init ERROR]", e)

    # ---------- dynamic cost (lighter congestion) ----------
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
    def _choose_far_goal(self, min_manhattan=10):
        here = self.position
        candidates = [
            n for n in self.city.graph.nodes
            if n != here and manhattan(n, here) >= min_manhattan
        ]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    # ---------- plan/step ----------
    def _plan_to(self, dest):
        """
        Planeia um caminho A* até dest.
        Aqui também registamos um replaneamento nas métricas, se existirem.
        """
        # Log de replaneamento (cada A* conta como replan)
        metrics = getattr(self.city, "metrics", None)
        if metrics is not None:
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
            print(f"[{self.label}] 🧭 planned path to {dest} (len={len(self.path)})")
        except Exception as e:
            print(f"[{self.label}] ❌ plan failed ({e}); using random next step")
            self.path = []
            self.goal = None

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
            best = min(
                lights,
                key=lambda l: nx.shortest_path_length(self.city.graph, self.position, l),
            )
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

            # --- Arrival handling ---
            at_goal = (
                self.agent.goal is not None
                and self.agent.position == self.agent.goal
            )
            singleton_here = (
                len(self.agent.path) == 1
                and self.agent.path[0] == self.agent.position
            )
            if at_goal or singleton_here:
                print(f"[{self.agent.label}] ✅ Reached goal {self.agent.goal}")

                # Se chegámos a um destino ALEATÓRIO (não hospital),
                # consideramos que a resposta à emergência terminou.
                metrics = getattr(self.agent.city, "metrics", None)
                if (
                    metrics is not None
                    and self.agent.fixed_dest is not None
                    and self.agent.position != self.agent.fixed_dest
                ):
                    metrics.end_emergency()

                await asyncio.sleep(self.agent.pause_at_goal)

                # Toggle phase: hospital <-> random, if a hospital is defined
                if self.agent.fixed_dest is not None:
                    if self.agent.position == self.agent.fixed_dest:
                        # we are at hospital -> next: random place
                        self.agent.phase = "to_random"
                    else:
                        # we are at random place -> next: hospital
                        self.agent.phase = "to_hospital"

                # clear planning state so next tick will choose the next leg
                self.agent.goal = None
                self.agent.path = []
                self.agent.steps_since_plan = 0
                return

            # --- Planning: only when we don't have a valid path/goal ---
            need_plan = (not self.agent.path) or (self.agent.goal is None)
            if need_plan:
                metrics = getattr(self.agent.city, "metrics", None)

                if self.agent.fixed_dest is not None:
                    # ensure phase is valid
                    if not hasattr(self.agent, "phase") or self.agent.phase not in {
                        "to_hospital", "to_random"
                    }:
                        if self.agent.position == self.agent.fixed_dest:
                            self.agent.phase = "to_random"
                        else:
                            self.agent.phase = "to_hospital"

                    if self.agent.phase == "to_hospital":
                        dest = self.agent.fixed_dest
                    else:  # to_random
                        dest = self.agent._choose_far_goal()
                        # Vamos assumir que a "resposta de emergência" começa
                        # quando sai do hospital para ir para um ponto aleatório.
                        if (
                            metrics is not None
                            and self.agent.position == self.agent.fixed_dest
                        ):
                            metrics.start_emergency()
                else:
                    # No fixed hospital: just patrol like a normal emergency vehicle
                    dest = self.agent._choose_far_goal()

                self.agent._plan_to(dest)

            # --- Move one step ---
            old_pos, new_pos = (
                self.agent._step_along_path()
                if self.agent.path
                else self.agent._move_randomly()
            )

            # Update viewer + occupancy
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                self.agent.shared.setdefault("emergency", {})[
                    self.agent.label
                ] = self.agent.position
            except Exception as e:
                print("[EMERGENCY UPDATE WARN]", e)

            print(
                f"[{self.agent.label}] 🚑 moved {old_pos} → {new_pos} "
                f"(goal={self.agent.goal}, phase={getattr(self.agent, 'phase', None)})"
            )

            # Priority request to nearest light (JSON body with from/to)
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

            if incoming:
                granted_flag = (
                    incoming.metadata.get("granted", "false")
                    if incoming.metadata
                    else "false"
                )
                print(
                    f"[{self.agent.label}] 📩 Traffic light reply: "
                    f"body={incoming.body}, granted={granted_flag}"
                )
            else:
                print(f"[{self.agent.label}] ⚠️ No reply from {light_jid}")

    async def setup(self):
        print(f"{self.label} (emergency) started at {self.position}")
        self.add_behaviour(self.EmergencyBehaviour(period=0.6))