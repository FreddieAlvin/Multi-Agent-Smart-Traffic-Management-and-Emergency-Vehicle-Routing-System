import time
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
import asyncio

class Visualizer:
    def __init__(self, city, shared_state, refresh_hz=5):
        self.city = city
        self.shared = shared_state
        self.refresh = max(1, refresh_hz)
        self.period = 1.0 / self.refresh
        self._last_log = 0.0

        self.fig, self.ax = plt.subplots(figsize=(7, 7))
        pos = {n: n for n in self.city.graph.nodes}
        # draw edges and nodes separately, no zorder kw
        nx.draw_networkx_edges(self.city.graph, pos, width=0.2, ax=self.ax)
        nx.draw_networkx_nodes(self.city.graph, pos, node_size=10, ax=self.ax)

        # lights (static) — squares, a partir do city.traffic_lights
        if self.city.traffic_lights:
            lx, ly = zip(*self.city.traffic_lights.values())
            self.light_scatter = self.ax.scatter(
                lx, ly, marker="s", s=70, label="Lights", zorder=3
            )
        else:
            # caso extremo em que não haja semáforos
            self.light_scatter = self.ax.scatter(
                [], [], marker="s", s=70, label="Lights", zorder=3
            )

        # dynamic layers
        self.veh_scatter = self.ax.scatter([], [], s=80, label="Vehicles", zorder=4)
        self.ev_scatter  = self.ax.scatter([], [], marker="*", s=200, label="Emergency", zorder=5)

        self.ax.set_title("Smart Traffic — Live")
        self.ax.set_xlim(-1, self.city.width)
        self.ax.set_ylim(-1, self.city.height)
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.legend(loc="upper right")
        plt.tight_layout()

    async def update_loop(self):
        plt.show(block=False)
        while True:
            await asyncio.sleep(self.period)
            self._update()
            # force re-draw
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

    def _update(self):
        # vehicles
        vpos = list(self.shared.get("vehicles", {}).values())
        v_arr = np.array(vpos, float).reshape(-1, 2) if vpos else np.empty((0, 2))
        self.veh_scatter.set_offsets(v_arr)

        # emergency
        epos = list(self.shared.get("emergency", {}).values())
        e_arr = np.array(epos, float).reshape(-1, 2) if epos else np.empty((0, 2))
        self.ev_scatter.set_offsets(e_arr)

        # heartbeat every ~0.5s so you can see counts in the console
        now = time.time()
        if now - self._last_log > 0.5:
            print(f"[VIS] drawing vehicles={len(v_arr)} emergency={len(e_arr)}")
            self._last_log = now