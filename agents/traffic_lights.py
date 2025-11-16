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

PHASE_DURATION = 5.0  # segundos que cada fase fica ativa (ajusta à vontade)


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
    class LightBehaviour(behaviour.CyclicBehaviour):
        async def on_start(self):
            # estado inicial do semáforo
            self.agent.phase = 0
            self.agent._last_switch = asyncio.get_event_loop().time()
            print(f"[Traffic Light {self.agent.jid}] 🚦 started in phase {self.agent.phase}")

        async def run(self):
            now = asyncio.get_event_loop().time()

            # 1) alternar de fase periodicamente
            if now - self.agent._last_switch >= self.agent.phase_duration:
                self.agent.phase = 1 - self.agent.phase
                self.agent._last_switch = now
                print(
                    f"[Traffic Light {self.agent.jid}] 🔄 Switched to phase {self.agent.phase} "
                    f"(allowed={ALLOWED_BY_PHASE[self.agent.phase]})"
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
                    print(f"[Traffic Light {self.agent.jid}] ⚠️ Invalid message body: {msg.body}")
                    await self._reply(msg, granted=False, reason="invalid_body")
                    return

                # Emergência: pode sempre passar
                if mtype == "priority_request":
                    print(f"[Traffic Light {self.agent.jid}] 🚑 Priority request {from_pos}->{to_pos} -> GRANTED")
                    await self._reply(msg, granted=True, reason="emergency")
                    return

                # Veículo normal: verificar direção vs fase atual
                d = direction(from_pos, to_pos)
                if d is None:
                    print(f"[Traffic Light {self.agent.jid}] ❌ Unknown direction {from_pos}->{to_pos}")
                    await self._reply(msg, granted=False, reason="unknown_direction")
                    return

                allowed_dirs = ALLOWED_BY_PHASE[self.agent.phase]
                granted = d in allowed_dirs

                print(
                    f"[Traffic Light {self.agent.jid}] 🚗 Request {from_pos}->{to_pos} dir={d} "
                    f"phase={self.agent.phase} allowed={allowed_dirs} -> "
                    f"{'GRANTED' if granted else 'DENIED'}"
                )

                await self._reply(msg, granted=granted, reason="phase_check")

        async def _reply(self, msg, granted: bool, reason: str = ""):
            reply = Message(to=str(msg.sender))
            reply.set_metadata("type", "passage_reply")
            reply.set_metadata("granted", "true" if granted else "false")
            if reason:
                reply.set_metadata("reason", reason)
            reply.body = "granted" if granted else "denied"
            await self.send(reply)

    async def setup(self):
        print(f"Traffic Light Agent {self.jid} ready")
        # podes parametrizar a duração se quiseres
        self.phase_duration = PHASE_DURATION
        self.add_behaviour(self.LightBehaviour())