from spade import agent, behaviour
from spade.message import Message

class TrafficLightAgent(agent.Agent):
    class LightBehaviour(behaviour.CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=5)
            if msg:
                mtype = msg.metadata.get("type") if msg.metadata else None
                if mtype == "passage_request":
                    print(f"[Traffic Light] 🚦 Received: {msg.body}")
                    reply = Message(to=str(msg.sender))
                    reply.body = "Passage granted."
                    await self.send(reply)
                elif mtype == "priority_request":
                    print(f"[Traffic Light] 🚑 Emergency priority: {msg.body}")
                    reply = Message(to=str(msg.sender))
                    reply.body = "Priority passage granted."
                    await self.send(reply)

    async def setup(self):
        print("Traffic Light Agent ready")
        self.add_behaviour(self.LightBehaviour())
