# traffic_lights.py
import asyncio
import json
from spade import agent, behaviour
from spade.message import Message

# Fase 0: Norte/Sul
# Fase 1: Este/Oeste
ALLOWED_BY_PHASE = {
    0: {"N", "S"},
    1: {"E", "W"},
}

# valor base; será adaptado dinamicamente consoante a densidade
PHASE_DURATION = 5.0  # segundos


def direction(from_pos, to_pos):
    """Devolve 'N','S','E','W' consoante o movimento."""
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
    # movimento estranho (diagonal ou stay); por segurança, não deixar passar
    return None


class TrafficLightAgent(agent.Agent):
    def __init__(self, jid, password, city_env=None, shared=None):
        super().__init__(jid, password)
        self.city = city_env
        self.shared = shared or {}
        self.position = None          # (x, y) deste semáforo na grelha
        self.phase_duration = PHASE_DURATION
        self.phase = 0
        self._last_switch = 0.0

    class LightBehaviour(behaviour.CyclicBehaviour):
        async def on_start(self):
            # estado inicial do semáforo
            self.agent.phase = 0
            self.agent._last_switch = asyncio.get_event_loop().time()
            print(
                f"[Traffic Light {self.agent.jid}] 🚦 started in phase "
                f"{self.agent.phase}"
            )

        async def run(self):
            now = asyncio.get_event_loop().time()

            # 0) adaptar duração da fase com base na densidade local (se tivermos city)
            if getattr(self.agent, "city", None) is not None and self.agent.position is not None:
                try:
                    # densidade média numa vizinhança à volta da interseção
                    rho = self.agent.city.occupancy.local_density(
                        self.agent.position,
                        radius=2,
                    )
                    # mapear rho ∈ [0,1+] para duração ∈ [3, 8] segundos
                    self.agent.phase_duration = max(
                        3.0,
                        min(8.0, 3.0 + 5.0 * float(rho)),
                    )
                except Exception as e:
                    print(f"[Traffic Light {self.agent.jid}] ⚠️ density adapt error: {e}")
                    self.agent.phase_duration = PHASE_DURATION

            # 1) alternar de fase periodicamente
            if now - self.agent._last_switch >= self.agent.phase_duration:
                self.agent.phase = 1 - self.agent.phase
                self.agent._last_switch = now
                print(
                    f"[Traffic Light {self.agent.jid}] 🔄 Switched to phase {self.agent.phase} "
                    f"(allowed={ALLOWED_BY_PHASE[self.agent.phase]}, "
                    f"duration={self.agent.phase_duration:.1f}s)"
                )

            # 2) tratar pedidos de passagem
            msg = await self.receive(timeout=0.1)
            if not msg:
                return

            mtype = msg.metadata.get("type") if msg.metadata else None

            if mtype in ("passage_request", "priority_request"):
                # Esperamos que o body venha em JSON com { "from": [x,y], "to": [x,y] }
                try:
                    payload = json.loads(msg.body)
                    from_pos = tuple(payload["from"])
                    to_pos = tuple(payload["to"])
                except Exception:
                    # se o formato vier diferente, loga e nega (para não rebentar)
                    print(
                        f"[Traffic Light {self.agent.jid}] ⚠️ Invalid message body: "
                        f"{msg.body}"
                    )
                    await self._reply(msg, granted=False, reason="invalid_body")
                    return

                # Emergência: pode sempre passar
                if mtype == "priority_request":
                    print(
                        f"[Traffic Light {self.agent.jid}] 🚑 Priority request "
                        f"{from_pos}->{to_pos} -> GRANTED"
                    )
                    await self._reply(msg, granted=True, reason="emergency")
                    return

                # Veículo normal: verificar direção vs fase atual
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

                print(
                    f"[Traffic Light {self.agent.jid}] 🚗 Request {from_pos}->{to_pos} "
                    f"dir={d} phase={self.agent.phase} allowed={allowed_dirs} -> "
                    f"{'GRANTED' if granted else 'DENIED'}"
                )

                await self._reply(msg, granted=granted, reason="phase_check")

        async def _reply(self, msg, granted: bool, reason: str = ""):
            """Responder ao veículo / ambulância com semântica tipo Contract Net."""
            reply = Message(to=str(msg.sender))
            reply.set_metadata("type", "passage_reply")

            # Contract Net-style metadata
            reply.set_metadata("protocol", "contract-net")

            mtype = msg.metadata.get("type") if msg.metadata else None
            if mtype == "priority_request":
                # emergência: é sempre "accept-proposal"
                reply.set_metadata("performative", "accept-proposal")
            else:
                # veículo normal: aceita se granted, caso contrário rejeita
                reply.set_metadata(
                    "performative",
                    "accept-proposal" if granted else "reject-proposal",
                )

            reply.set_metadata("granted", "true" if granted else "false")
            if reason:
                reply.set_metadata("reason", reason)
            reply.body = "granted" if granted else "denied"
            await self.send(reply)

    async def setup(self):
        print(f"Traffic Light Agent {self.jid} ready")

        # descobrir a posição deste semáforo a partir do id (ex: 'light_4_8')
        if self.city is not None:
            lid = str(self.jid).split("@")[0]   # "light_4_8"
            self.position = self.city.traffic_lights.get(lid)

        # fase inicial
        self.phase_duration = PHASE_DURATION
        self.add_behaviour(self.LightBehaviour())
