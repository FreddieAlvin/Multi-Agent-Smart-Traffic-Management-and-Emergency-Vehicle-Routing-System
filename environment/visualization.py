# environment/visualizer.py
import time
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx
import asyncio
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import matplotlib.image as mpimg
import os
from matplotlib.legend_handler import HandlerBase


class HandlerImage(HandlerBase):
    """Custom legend handler to display an image."""
    def __init__(self, img, zoom=0.03):
        self.img = img
        self.zoom = zoom
        super().__init__()

    def create_artists(self, legend, orig_handle,
                       xdescent, ydescent, width, height, fontsize, trans):
        im = OffsetImage(self.img, zoom=self.zoom)
        ab = AnnotationBbox(im, [width / 2, height / 2], frameon=False, xycoords=trans)
        return [ab]


class Visualizer:
    def __init__(self, city, shared_state, refresh_hz=5):
        self.city = city
        self.shared = shared_state
        self.refresh = max(1, refresh_hz)
        self.period = 1.0 / self.refresh
        self._last_log = 0.0

        # Load images from environment/assets
        base_path = os.path.join("environment", "assets")
        self.car_img = mpimg.imread(os.path.join(base_path, "car.png"))
        self.ev_img = mpimg.imread(os.path.join(base_path, "ambulance.png"))
        self.hospital_img = mpimg.imread(os.path.join(base_path, "hospital.png"))
        self.light_img = mpimg.imread(os.path.join(base_path, "traffic_light.png"))
        self.roadblock_img = mpimg.imread(os.path.join(base_path, "roadblock.png"))

        # Figure and axes
        self.fig, self.ax = plt.subplots(figsize=(7, 7))
        self.ax.set_facecolor("#8dc68d")  # light green background

        pos = {n: n for n in self.city.graph.nodes}
        nx.draw_networkx_edges(self.city.graph, pos, width=0.2, ax=self.ax)

        # Legend using images
        handles = ["Traffic Light", "Vehicles", "Emergency", "Hospital", "Incident"]
        labels = ["Traffic Light", "Vehicles", "Emergency", "Hospital", "Incident"]

        handler_map = {
            "Traffic Light": HandlerImage(self.light_img, zoom=0.01),
            "Vehicles": HandlerImage(self.car_img, zoom=0.03),
            "Emergency": HandlerImage(self.ev_img, zoom=0.03),
            "Hospital": HandlerImage(self.hospital_img, zoom=0.01),
            "Incident": HandlerImage(self.roadblock_img, zoom=0.03),
        }

        leg = self.ax.legend(
            handles=handles,
            labels=labels,
            handler_map=handler_map,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0.0,
            frameon=True,
        )

        # optional: tint legend background to match the figure a bit
        leg.get_frame().set_facecolor("#d3d3d3")
        leg.get_frame().set_edgecolor("none")


        self.ax.set_title("Smart Traffic — Live")
        self.ax.set_xlim(-1, self.city.width)
        self.ax.set_ylim(-1, self.city.height)
        self.ax.set_aspect("equal", adjustable="box")
        plt.tight_layout()

        # Containers for drawn elements
        self._img_artists = []
        self._roadblock_artists = []

    async def update_loop(self):
        plt.show(block=False)
        while True:
            await asyncio.sleep(self.period)
            self._update()
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

    def _update(self):
        # --- VEHICLES ---
        vpos = list(self.shared.get("vehicles", {}).values())
        v_arr = np.array(vpos, float).reshape(-1, 2) if vpos else np.empty((0, 2))

        # --- EMERGENCY VEHICLES ---
        epos = list(self.shared.get("emergency", {}).values())
        e_arr = np.array(epos, float).reshape(-1, 2) if epos else np.empty((0, 2))

        # --- HOSPITALS ---
        hpos = list(self.city.hospitals.values()) if hasattr(self.city, "hospitals") else []

        # --- TRAFFIC LIGHTS ---
        lpos = list(self.shared.get("lights", []))

        # --- ROADBLOCKS / INCIDENTS ---
        rnodes = list(self.city.event_manager.blocked_nodes()) if hasattr(self.city, "event_manager") else []
        redges = list(self.city.event_manager.blocked_edges()) if hasattr(self.city, "event_manager") else []

        # Clear previous artists
        for art in self._img_artists:
            art.remove()
        for art in self._roadblock_artists:
            art.remove()

        self._img_artists.clear()
        self._roadblock_artists.clear()

        # Draw hospitals
        for x, y in hpos:
            im = OffsetImage(self.hospital_img, zoom=0.02)
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=10)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Draw traffic lights
        for x, y in lpos:
            im = OffsetImage(self.light_img, zoom=0.01)
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=10)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Draw vehicles
        for x, y in v_arr:
            im = OffsetImage(self.car_img, zoom=0.03)
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=12)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Draw emergency vehicles
        for x, y in e_arr:
            im = OffsetImage(self.ev_img, zoom=0.03)
            ab = AnnotationBbox(im, (x, y), frameon=False, zorder=13)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # 🔴 Draw blocked edges + icon in the middle (instead of on nodes)
        for (u, v) in redges:
            # red line along the edge
            x_vals = [u[0], v[0]]
            y_vals = [u[1], v[1]]
            art = self.ax.plot(x_vals, y_vals, color="red", linewidth=2,
                               zorder=11, alpha=0.6)[0]
            self._roadblock_artists.append(art)

            # icon at the midpoint of the edge
            mx = (u[0] + v[0]) / 2.0
            my = (u[1] + v[1]) / 2.0
            im = OffsetImage(self.roadblock_img, zoom=0.025)
            ab = AnnotationBbox(im, (mx, my), frameon=False, zorder=12)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # (no more "Draw blocked nodes" loop here)
