"""
Visualization module for the Smart Traffic Simulation.

This component is responsible for live rendering of the simulation using
Matplotlib. It displays:
  • road network grid
  • vehicles
  • emergency vehicles
  • traffic lights
  • hospitals
  • incidents (blocked edges)

The visualizer runs asynchronously, refreshing at a configurable frequency,
pulling data from the shared state dictionary updated by all SPADE agents.
"""

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
    """
    Custom legend handler that displays an image instead of a text marker.

    Attributes:
        img (ndarray): Loaded image to display.
        zoom (float): Scale factor applied when embedding the image.
    """

    def __init__(self, img, zoom=0.03):
        self.img = img
        self.zoom = zoom
        super().__init__()

    def create_artists(
        self,
        legend,
        orig_handle,
        xdescent,
        ydescent,
        width,
        height,
        fontsize,
        trans,
    ):
        """
        Creates the artist elements used inside the legend.

        Returns:
            list: A list containing one AnnotationBbox with the scaled image.
        """
        im = OffsetImage(self.img, zoom=self.zoom)
        ab = AnnotationBbox(
            im, [width / 2, height / 2], frameon=False, xycoords=trans
        )
        return [ab]


class Visualizer:
    """
    Live visualization engine that renders the simulation environment.

    The Visualizer:
      • loads sprites from /environment/assets/
      • draws the static grid once
      • periodically refreshes positions of vehicles, ambulances, lights
      • renders incidents as edge markers
      • runs as an async loop in parallel with SPADE agents

    Attributes:
        city (CityEnvironment): The environment containing graph and assets.
        shared (dict): Shared dictionary updated by agents with their positions.
        refresh (int): Refresh rate (Hz).
        period (float): Time per frame (s).
        fig, ax: Matplotlib figure and axes used for rendering.
    """

    def __init__(self, city, shared_state, refresh_hz=5):
        """
        Initialize the visualization engine.

        Args:
            city (CityEnvironment): The grid and objects to draw.
            shared_state (dict): Real-time positions (vehicles, emergency, lights).
            refresh_hz (int): How many times per second to refresh.
        """
        self.city = city
        self.shared = shared_state
        self.refresh = max(1, refresh_hz)
        self.period = 1.0 / self.refresh
        self._last_log = 0.0

        # Load sprite assets
        base_path = os.path.join("environment", "assets")
        self.car_img = mpimg.imread(os.path.join(base_path, "car.png"))
        self.ev_img = mpimg.imread(os.path.join(base_path, "ambulance.png"))
        self.hospital_img = mpimg.imread(os.path.join(base_path, "hospital.png"))
        self.light_img = mpimg.imread(os.path.join(base_path, "traffic_light.png"))
        self.roadblock_img = mpimg.imread(os.path.join(base_path, "roadblock.png"))

        # Static plot: background + grid
        self.fig, self.ax = plt.subplots(figsize=(7, 7))
        self.ax.set_facecolor("#8dc68d")

        pos = {n: n for n in self.city.graph.nodes}
        nx.draw_networkx_edges(self.city.graph, pos, width=0.2, ax=self.ax)

        # Legend with images
        handles = ["Traffic Light", "Vehicles", "Emergency", "Hospital", "Incident"]
        labels = ["Traffic Light", "Vehicles", "Emergency", "Hospital", "Incident"]
        handler_map = {
            "Traffic Light": HandlerImage(self.light_img, zoom=0.01),
            "Vehicles": HandlerImage(self.car_img, zoom=0.03),
            "Emergency": HandlerImage(self.ev_img, zoom=0.03),
            "Hospital": HandlerImage(self.hospital_img, zoom=0.01),
            "Incident": HandlerImage(self.roadblock_img, zoom=0.03),
        }

        legend = self.ax.legend(
            handles=handles,
            labels=labels,
            handler_map=handler_map,
            loc="upper left",
            bbox_to_anchor=(1.02, 1.0),
            borderaxespad=0.0,
            frameon=True,
        )
        legend.get_frame().set_facecolor("#d3d3d3")
        legend.get_frame().set_edgecolor("none")

        self.ax.set_title("Smart Traffic — Live")
        self.ax.set_xlim(-1, self.city.width)
        self.ax.set_ylim(-1, self.city.height)
        self.ax.set_aspect("equal", adjustable="box")
        plt.tight_layout()

        # Runtime artists
        self._img_artists = []
        self._roadblock_artists = []

    async def update_loop(self):
        """
        Asynchronous refresh loop that updates the visual state continuously.

        This method:
            • calls `_update()` once per refresh period
            • redraws only dynamic elements
            • keeps the Matplotlib window alive without blocking SPADE
        """
        plt.show(block=False)
        while True:
            await asyncio.sleep(self.period)
            self._update()
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()

    def _update(self):
        """
        Redraw all dynamic elements (vehicles, ambulances, incidents, lights).

        This method fetches the latest shared state values updated by all agents,
        removes previous frame artifacts, and redraws icons at updated positions.
        """
        # Read state -----------------------
        vpos = list(self.shared.get("vehicles", {}).values())
        v_arr = np.array(vpos, float).reshape(-1, 2) if vpos else np.empty((0, 2))

        epos = list(self.shared.get("emergency", {}).values())
        e_arr = np.array(epos, float).reshape(-1, 2) if epos else np.empty((0, 2))

        hpos = list(self.city.hospitals.values())
        lpos = list(self.shared.get("lights", []))

        rnodes = self.city.event_manager.blocked_nodes()
        redges = self.city.event_manager.blocked_edges()

        # Clear previous frame ------------
        for art in self._img_artists:
            art.remove()
        for art in self._roadblock_artists:
            art.remove()
        self._img_artists.clear()
        self._roadblock_artists.clear()

        # Hospitals
        for x, y in hpos:
            icon = OffsetImage(self.hospital_img, zoom=0.02)
            ab = AnnotationBbox(icon, (x, y), frameon=False, zorder=10)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Traffic lights
        for x, y in lpos:
            icon = OffsetImage(self.light_img, zoom=0.01)
            ab = AnnotationBbox(icon, (x, y), frameon=False, zorder=10)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Vehicles
        for x, y in v_arr:
            icon = OffsetImage(self.car_img, zoom=0.03)
            ab = AnnotationBbox(icon, (x, y), frameon=False, zorder=12)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Emergency vehicles
        for x, y in e_arr:
            icon = OffsetImage(self.ev_img, zoom=0.03)
            ab = AnnotationBbox(icon, (x, y), frameon=False, zorder=13)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Incidents (edges + icon)
        for (u, v) in redges:
            # red line marking blocked edge
            art = self.ax.plot(
                [u[0], v[0]],
                [u[1], v[1]],
                color="red",
                linewidth=2,
                zorder=11,
                alpha=0.6,
            )[0]
            self._roadblock_artists.append(art)

            # icon at midpoint
            mx = (u[0] + v[0]) / 2
            my = (u[1] + v[1]) / 2
            icon = OffsetImage(self.roadblock_img, zoom=0.025)
            ab = AnnotationBbox(icon, (mx, my), frameon=False, zorder=12)
            self.ax.add_artist(ab)
            self._img_artists.append(ab)

        # Log heartbeat
        now = time.time()
        if now - self._last_log > 0.5:
            print(
                f"[VIS] vehicles={len(v_arr)} "
                f"emergency={len(e_arr)} "
                f"hospitals={len(hpos)} "
                f"traffic_lights={len(lpos)} "
                f"blocked_edges={len(redges)}"
            )
            self._last_log = now
