# Simple and readable routing helpers for our MAS project.
# - nearest_traffic_light(pos)
# - A* / Weighted A* pathfinding (time-aware edge cost)
# - route_a_star(...) wrapper that plugs City + Events + Occupancy
# - route_weighted(...) for normal vehicles
# - route_exact(...) for emergency vehicles
# ------------------------------------------------------------

from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple
from heapq import heappush, heappop

# Optional import: if TRAFFIC_LIGHTS doesn't exist yet, fall back to empty dict.
try:
    # Expected shape in environment.city: TRAFFIC_LIGHTS = { "tl1@localhost": (x, y), ... }
    from environment.city import TRAFFIC_LIGHTS  # type: ignore
except Exception:
    TRAFFIC_LIGHTS = {}  # safe fallback for early development

# Basic coordinate type (grid nodes)
Node = Tuple[int, int]


# --------------------------------------------------------------------
# Nearest traffic light helper (kept simple and obvious)
# --------------------------------------------------------------------
def nearest_traffic_light(pos: Node) -> Optional[str]:
    """
    Return the JID of the nearest traffic light based on Manhattan distance.
    If no lights are registered, return None.
    """
    if not TRAFFIC_LIGHTS:
        return None
    x, y = pos
    jid, _ = min(
        TRAFFIC_LIGHTS.items(),
        key=lambda item: abs(item[1][0] - x) + abs(item[1][1] - y),
    )
    return jid


# --------------------------------------------------------------------
# A* / Weighted A* core (clean, minimal, well-commented)
# --------------------------------------------------------------------
def manhattan(a: Node, b: Node) -> float:
    """Admissible heuristic on grid graphs: L1 (|dx| + |dy|)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _reconstruct(came_from: Dict[Node, Node], current: Node) -> List[Node]:
    """Rebuild a path from 'came_from' map."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def astar(
    start: Node,
    goal: Node,
    neighbors_fn: Callable[[Node], List[Node]],
    edge_cost_fn: Callable[[Node, Node, int], float],  # time-aware edge cost
    heuristic_fn: Callable[[Node, Node], float] = manhattan,
    *,
    is_forbidden_fn: Optional[Callable[[Node, Node], bool]] = None,
    weight: float = 1.0,          # 1.0 = A*; >1.0 = Weighted A* (faster, near-optimal)
    start_tick: int = 0,          # current simulation tick (for ETA)
    eta_per_edge: int = 1,        # ticks to traverse one edge (constant for now)
) -> Optional[List[Node]]:
    """
    A* / Weighted A* search.
    Returns a node list [start ... goal] or None if no path exists.
    """
    open_heap: List[Tuple[float, Node]] = []
    heappush(open_heap, (0.0, start))

    came_from: Dict[Node, Node] = {}
    g: Dict[Node, float] = {start: 0.0}   # best known cost to reach node
    steps: Dict[Node, int] = {start: 0}   # number of edges taken to reach node

    while open_heap:
        _, cur = heappop(open_heap)
        if cur == goal:
            return _reconstruct(came_from, cur)

        cur_steps = steps[cur]

        for nb in neighbors_fn(cur):
            if is_forbidden_fn and is_forbidden_fn(cur, nb):
                continue

            # Estimated arrival tick on edge (cur -> nb)
            tick_eta = start_tick + (cur_steps + 1) * eta_per_edge
            cost = edge_cost_fn(cur, nb, tick_eta)  # can include signal penalties etc.

            tentative = g[cur] + cost
            if tentative < g.get(nb, float("inf")):
                came_from[nb] = cur
                g[nb] = tentative
                steps[nb] = cur_steps + 1

                # Weighted A*: increase heuristic influence (f = g + w*h)
                f = tentative + weight * heuristic_fn(nb, goal)
                heappush(open_heap, (f, nb))

    return None  # no path found


# --------------------------------------------------------------------
# Project-specific wrapper: City + Events + Occupancy
# --------------------------------------------------------------------
def route_a_star(
    city,
    events,
    occupancy,
    start: Node,
    goal: Node,
    *,
    weight: float = 1.0,          # normal cars: ~1.2; EMS: 1.0
    start_tick: int = 0,
    eta_per_edge: int = 1,
    ignore_capacity: bool = False # EMS can ignore capacity if allowed
) -> Optional[List[Node]]:
    """
    Compute a route using (Weighted) A* while respecting:
      - blocked edges (events.is_blocked(a, b))
      - capacity limits (occupancy.is_full(a, b)) unless ignore_capacity=True
      - time-dependent penalties (city.time_penalty(a, b, tick_eta)), if provided
    Required City API:
      - city.neighbors(node) -> List[Node]
      - city.edge_cost(a, b) -> float
      - (optional) city.time_penalty(a, b, tick) -> float
    """

    def is_forbidden(a: Node, b: Node) -> bool:
        # Physical closures / incidents
        if events and hasattr(events, "is_blocked") and events.is_blocked(a, b):
            return True
        # Capacity constraints for normal vehicles
        if not ignore_capacity and occupancy and hasattr(occupancy, "is_full") and occupancy.is_full(a, b):
            return True
        return False

    def edge_cost(a: Node, b: Node, tick_eta: int) -> float:
        base = city.edge_cost(a, b) if hasattr(city, "edge_cost") else 1.0
        extra = city.time_penalty(a, b, tick_eta) if hasattr(city, "time_penalty") else 0.0
        return base + extra

    return astar(
        start=start,
        goal=goal,
        neighbors_fn=city.neighbors,
        edge_cost_fn=edge_cost,
        heuristic_fn=manhattan,
        is_forbidden_fn=is_forbidden,
        weight=weight,
        start_tick=start_tick,
        eta_per_edge=eta_per_edge,
    )


# --------------------------------------------------------------------
# Small convenience helpers for agents
# --------------------------------------------------------------------
def route_weighted(
    city, events, occupancy, start: Node, goal: Node, *,
    start_tick: int = 0, eta_per_edge: int = 1, weight: float = 1.2
) -> Optional[List[Node]]:
    """Recommended for normal vehicles (fast, near-optimal)."""
    return route_a_star(
        city, events, occupancy, start, goal,
        weight=weight, start_tick=start_tick, eta_per_edge=eta_per_edge,
    )


def route_exact(
    city, events, occupancy, start: Node, goal: Node, *,
    start_tick: int = 0, eta_per_edge: int = 1, ignore_capacity: bool = False
) -> Optional[List[Node]]:
    """Recommended for emergency vehicles (exact A*)."""
    return route_a_star(
        city, events, occupancy, start, goal,
        weight=1.0, start_tick=start_tick, eta_per_edge=eta_per_edge,
        ignore_capacity=ignore_capacity,
    )
