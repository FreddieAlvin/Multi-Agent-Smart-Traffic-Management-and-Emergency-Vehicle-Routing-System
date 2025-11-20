"""
ISIA - Introdução a Sistemas Inteligentes Autónomos
Multi-Agent Smart Traffic Management and Emergency Vehicle Routing System

Ficheiro:
    agents/vehicle.py

Descrição:
    Define o agente de veículo "normal" (não prioritário), responsável por:
      - planear rotas com A* num grafo de cidade;
      - evitar arestas e nós bloqueados (incidentes);
      - respeitar semáforos via protocolo tipo Contract Net;
      - atualizar a ocupação (congestionamento) e métricas de viagem;
      - cooperar com o visualizador através de um estado partilhado.

    Este agente representa o tráfego de veículos comuns na cidade
    que convivem com veículos de emergência e incidentes dinâmicos.
"""

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
    """
    Compute the Manhattan distance between two grid points.

    Args:
        a (tuple[int, int]): First point (x, y).
        b (tuple[int, int]): Second point (x, y).

    Returns:
        int: |x1 - x2| + |y1 - y2|
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class VehicleAgent(agent.Agent):
    """
    Agente de veículo "normal" na cidade.

    Responsabilidades:
      - Escolher destinos aleatórios e relativamente distantes.
      - Planear rotas com A* usando pesos dinâmicos:
          * custo base da aresta,
          * ocupação (congestionamento),
          * penalizações de incidentes/bloqueios.
      - Solicitar passagem a semáforos (Contract Net-like).
      - Evitar colisões (não entrar em nós ocupados).
      - Atualizar métricas de viagem (tempo de viagem e replans).
      - Publicar a posição atual no estado partilhado para o visualizador.
    """

    def __init__(self, jid, password, name, city_env, shared=None):
        """
        Inicializa o agente de veículo.

        Args:
            jid (str): JID XMPP do agente.
            password (str): Password do agente.
            name (str): Label amigável (ex.: "Vehicle 1").
            city_env (CityEnvironment): Ambiente da cidade, com grafo e serviços.
            shared (dict | None): Dicionário de estado partilhado com o visualizador.
        """
        super().__init__(jid, password)
        self.label = name
        self.city = city_env
        self.shared = shared or {"vehicles": {}}

        # Posição inicial aleatória no grafo da cidade
        nodes = list(city_env.graph.nodes)
        self.position = random.choice(nodes)

        # Estado de roteamento
        self.goal = None
        self.path = []              # lista de nós (inclui atual + goal)
        self.steps_since_plan = 0
        self.replan_every = 10      # replanning periódico de segurança

        # Inicializar ocupação no estado partilhado
        try:
            self.shared.setdefault("vehicles", {})[self.label] = self.position
        except Exception as e:
            print("[VIS-WRITE vehicle init ERROR]", e)

    # ---------------- Helpers ----------------
    def _dynamic_weight(self, u, v, d):
        """
        Calcula o peso dinâmico de uma aresta para o A*.

        Combina:
          - peso base da aresta,
          - densidade de ocupação (congestionamento),
          - penalizações de incidentes/bloqueios (aresta + nó destino).

        Args:
            u (tuple[int, int]): Nó origem da aresta.
            v (tuple[int, int]): Nó destino da aresta.
            d (dict): Atributos da aresta no grafo.

        Returns:
            float: Peso efetivo da aresta para o A*.
        """
        base = d.get("weight", 1.0)

        # Occupancy (congestionamento)
        try:
            occ = self.city.occupancy.edge_density(u, v)
        except Exception:
            occ = 0.0

        # Incidentes / roadblocks (aresta)
        pen = 0.0
        try:
            pen = self.city.event_manager.edge_penalty(u, v)
        except Exception:
            pass

        # Extra: evitar entrar num nó bloqueado
        try:
            if self.city.event_manager.is_node_blocked(v):
                pen += 9999.0   # essencialmente "não ir para aqui"
        except Exception:
            pass

        return base + 0.6 * occ + pen

    def _choose_far_goal(self):
        """
        Escolhe um destino aleatório relativamente distante (>= 8 em Manhattan).

        Returns:
            tuple[int, int]: Nó destino escolhido.
        """
        here = self.position
        candidates = [n for n in self.city.graph.nodes if n != here and manhattan(n, here) >= 8]
        if not candidates:
            candidates = [n for n in self.city.graph.nodes if n != here]
        return random.choice(candidates) if candidates else here

    def _plan_to(self, dest):
        """
        Planeia uma rota A* até um dado destino.

        Regista o replan nas métricas e atualiza:
          - self.path,
          - self.goal,
          - self.steps_since_plan.

        Args:
            dest (tuple[int, int]): Nó destino pretendido.
        """
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
        """
        Executa um passo ao longo do caminho planeado, se existir.

        Respeita:
          - coerência entre posição atual e path,
          - bloqueios em arestas e nós,
          - em caso de bloqueio, esvazia o plano.

        Returns:
            tuple[tuple[int, int], tuple[int, int]]:
                (posição_antiga, nova_posição)
        """
        if not self.path or self.path[0] != self.position:
            if self.path and self.position in self.path:
                idx = self.path.index(self.position)
                self.path = self.path[idx:]
            else:
                return self._move_randomly()

        if len(self.path) >= 2:
            curr = self.path[0]
            nxt = self.path[1]

            # 1) aresta bloqueada?
            try:
                if self.city.event_manager.is_blocked((curr, nxt)):
                    print(f"[{self.label}] ⛔ Edge {(curr, nxt)} blocked, waiting and replanning")
                    self.path = []
                    self.goal = None
                    return self.position, self.position
            except Exception:
                pass

            # 2) nó bloqueado?
            try:
                if self.city.event_manager.is_node_blocked(nxt):
                    print(f"[{self.label}] ⛔ Node {nxt} blocked, waiting and replanning")
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
        else:
            # Sem próximo passo: path reduzido à posição atual
            self.path = [self.position]
            return self.position, self.position

    def _move_randomly(self):
        """
        Movimento aleatório para um vizinho caso não exista plano válido.

        Returns:
            tuple[tuple[int, int], tuple[int, int]]:
                (posição_antiga, nova_posição)
        """
        neighbors = list(self.city.graph.neighbors(self.position))
        old = self.position
        if neighbors:
            self.position = random.choice(neighbors)
        return old, self.position

    def _nearest_light_jid(self):
        """
        Determina o JID do semáforo mais próximo no grafo.

        Returns:
            str: JID do agente semáforo mais próximo,
                 ou "light1@localhost" como fallback.
        """
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
        """
        Devolve o próximo passo no caminho sem o executar.

        Se o path estiver desalinhado com a posição atual, tenta corrigir.
        Caso não exista passo seguinte, devolve a posição atual.

        Returns:
            tuple[tuple[int, int], tuple[int, int]]:
                (posição_atual, próximo_nó_no_path_ou_atual)
        """
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
        """
        Obtém o JID do semáforo associado a um nó da grelha, se existir.

        Args:
            node (tuple[int, int]): Coordenada da grelha.

        Returns:
            str | None: JID do semáforo correspondente ou None.
        """
        for lid, pos in self.city.traffic_lights.items():
            if pos == node:
                return f"{lid}@localhost"
        return None

    # ---------------- Behaviour ----------------
    class VehicleBehaviour(behaviour.PeriodicBehaviour):
        """
        Comportamento periódico principal do veículo.

        Ciclo:
          - espera inicial (para não colidir com arranque de outros agentes);
          - verifica chegada ao destino e trata fim de viagem;
          - reage a incidentes próximos (replaneamento);
          - se necessário, planeia um novo destino;
          - coordena passagem com semáforos (Contract Net-like);
          - evita entrar em nós ocupados;
          - atualiza ocupação e estado partilhado para o visualizador.
        """

        async def on_start(self):
            """
            Inicialização do comportamento.

            Define um pequeno atraso na primeira execução
            para evitar picos de trabalho todos ao mesmo tempo.
            """
            self.first_run = True

        async def _wait_for_green(self, from_pos, to_pos):
            """
            Solicita passagem ao semáforo associado ao nó de destino.

            Envia pedidos repetidamente até receber resposta "granted"
            ou expirar o timeout entre tentativas.

            Args:
                from_pos (tuple[int, int]): Posição atual do veículo.
                to_pos (tuple[int, int]): Nó de destino pretendido.
            """
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
            """
            Corpo principal do comportamento periódico.

            Implementa o ciclo de vida de um veículo:
              - deteção de chegada ao destino e pausa;
              - decisão de replanear;
              - reação a incidentes recebidos por mensagem;
              - coordenação com semáforos;
              - atualização de métricas, ocupação e visualização.
            """
            # Atraso inicial apenas na primeira iteração
            if self.first_run:
                await asyncio.sleep(1.5)
                self.first_run = False

            metrics = getattr(self.agent.city, "metrics", None)

            # ---------------- Chegada ao destino ----------------
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

            # ---------------- Decidir se é preciso planear ----------------
            need_plan = (
                not self.agent.path
                or (self.agent.goal is None)
                or (self.agent.steps_since_plan >= self.agent.replan_every)
            )

            # ---------------- Reação a incidentes próximos ----------------
            incident_near = False
            try:
                incident_msg = None
                if USE_FILTERED_INCIDENTS and Template is not None:
                    incident_msg = await self.receive(timeout=0.01, filter=Template(metadata={"type": "incident"}))
                else:
                    # fallback: inspeciona mensagens de texto simples
                    candidate = await self.receive(timeout=0.01)
                    if candidate and isinstance(candidate.body, str) and "Accident reported near" in candidate.body:
                        incident_msg = candidate

                if incident_msg and isinstance(incident_msg.body, str):
                    # Extrair coordenadas do texto: "(x, y)"
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
                    # Novo destino "longe"
                    self.agent.goal = self.agent._choose_far_goal()
                    if metrics is not None:
                        metrics.start_trip(self.agent.label)
                self.agent._plan_to(self.agent.goal)

            # ---------------- Movimento (com coordenação com semáforo) ----------------
            if self.agent.path:
                old_pos, candidate_new = self.agent._peek_next_step()
                if old_pos != candidate_new:
                    # Pedir permissão ao semáforo do nó destino
                    await self._wait_for_green(old_pos, candidate_new)

                    # Evitar colisões com outros veículos / emergências
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
                        # Movimento efetivo
                        self.agent.position = candidate_new
                        if self.agent.position in self.agent.path:
                            idx = self.agent.path.index(self.agent.position)
                            self.agent.path = self.agent.path[idx:]
                        else:
                            self.agent.path = [self.agent.position]
                        self.agent.steps_since_plan += 1
                        new_pos = self.agent.position
                else:
                    # Path degenerado: recorre a movimento aleatório
                    old_pos, new_pos = self.agent._move_randomly()
            else:
                # Sem path: movimento aleatório simples
                old_pos, new_pos = self.agent._move_randomly()

            # ---------------- Atualização de ocupação ----------------
            try:
                if old_pos != new_pos:
                    self.agent.city.occupancy.leave(old_pos, new_pos, self.agent.label)
                    self.agent.city.occupancy.enter(old_pos, new_pos, self.agent.label)
                if hasattr(self.agent.city, "update_edge_weights"):
                    self.agent.city.update_edge_weights()
            except Exception as e:
                print("[OCCUPANCY/WEIGHTS ERROR]", e)

            # ---------------- Atualização do visualizador ----------------
            try:
                self.agent.shared.setdefault("vehicles", {})[self.agent.label] = self.agent.position
            except Exception as e:
                print("[VIS-WRITE vehicle tick ERROR]", e)

            print(f"[{self.agent.label}] 🚗 moved {old_pos} → {new_pos} (goal={self.agent.goal})")

    async def setup(self):
        """
        Configuração inicial do agente de veículo.

        Adiciona o comportamento periódico principal e
        reporta a posição inicial na consola.
        """
        print(f"[{self.label}] Vehicle agent initialized at {self.position}")
        self.add_behaviour(self.VehicleBehaviour(period=1.5))
