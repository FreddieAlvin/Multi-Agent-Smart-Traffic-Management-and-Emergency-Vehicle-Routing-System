"""Routing helpers for the multi-agent traffic management project.

This module provides:
- A generic implementation of A* / Weighted A* with time-aware edge costs.
- Helper functions to compute routes that integrate city, events and occupancy.
- A utility to find the nearest traffic light based on Manhattan distance.
"""

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


def nearest_traffic_light(pos: Node) -> Optional[str]:
    """Return the JID of the nearest traffic light based on Manhattan distance.

    The function searches over the global TRAFFIC_LIGHTS dictionary, which is
    expected to map traffic light JIDs to their grid positions. If no traffic
    lights are registered, it returns None.

    Args:
        pos (Node): Current position of the agent in grid coordinates (x, y).

    Returns:
        Optional[str]: JID of the nearest traffic light, or None if there are
            no traffic lights available.
    """
    if not TRAFFIC_LIGHTS:
        return None
    x, y = pos
    jid, _ = min(
        TRAFFIC_LIGHTS.items(),
        key=lambda item: abs(item[1][0] - x) + abs(item[1][1] - y),
    )
    return jid


def manhattan(a: Node, b: Node) -> float:
    """Compute the Manhattan distance between two grid nodes.

    This heuristic is admissible on grid graphs where movement is restricted
    to horizontal and vertical directions.

    Args:
        a (Node): First node (x, y).
        b (Node): Second node (x, y).

    Returns:
        float: Manhattan distance |dx| + |dy| between the two nodes.
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _reconstruct(came_from: Dict[Node, Node], current: Node) -> List[Node]:
    """Rebuild a path from the predecessor map returned by A*.

    Starting from the goal node, this function walks backwards through the
    `came_from` dictionary until it reaches the start node, then reverses
    the sequence to obtain the full path from start to goal.

    Args:
        came_from (Dict[Node, Node]): Mapping from each visited node to its
            predecessor on the best known path.
        current (Node): Final node of the path (typically the goal).

    Returns:
        List[Node]: Ordered list of nodes from start to goal.
    """
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
    edge_cost_fn: Callable[[Node, Node, int], float],
    heuristic_fn: Callable[[Node, Node], float] = manhattan,
    *,
    is_forbidden_fn: Optional[Callable[[Node, Node], bool]] = None,
    weight: float = 1.0,
    start_tick: int = 0,
    eta_per_edge: int = 1,
) -> Optional[List[Node]]:
    """Run A* / Weighted A* search on an abstract graph.

    This function implements a generic A* (or Weighted A*) algorithm that:
    - Uses a user-provided neighbor function.
    - Supports time-aware edge costs via `edge_cost_fn`.
    - Optionally skips forbidden edges (e.g., blocked or over capacity).
    - Allows heuristic weighting (Weighted A*: f = g + w * h).

    Args:
        start (Node): Start node.
        goal (Node): Goal node.
        neighbors_fn (Callable[[Node], List[Node]]): Function that returns
            the list of neighbors for a given node.
        edge_cost_fn (Callable[[Node, Node, int], float]): Function that
            computes the cost of traversing an edge (u, v) at a given
            estimated arrival tick.
        heuristic_fn (Callable[[Node, Node], float], optional): Heuristic
            function h(n, goal). Defaults to `manhattan`.
        is_forbidden_fn (Callable[[Node, Node], bool], optional): Predicate
            that returns True if an edge (u, v) should not be traversed
            (for example due to incidents or capacity constraints).
            Defaults to None (no edges forbidden).
        weight (float, optional): Heuristic weight. A value of 1.0 yields
            standard A*. Values greater than 1.0 correspond to Weighted A*,
            which is faster but can produce suboptimal paths. Defaults to 1.0.
        start_tick (int, optional): Simulation tick at which the search
            starts. Used to compute time-dependent costs. Defaults to 0.
        eta_per_edge (int, optional): Estimated number of ticks required to
            traverse a single edge. Defaults to 1.

    Returns:
        Optional[List[Node]]: Path as a list of nodes from start to goal,
        or None if no path exists.
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
            cost = edge_cost_fn(cur, nb, tick_eta)

            tentative = g[cur] + cost
            if tentative < g.get(nb, float("inf")):
                came_from[nb] = cur
                g[nb] = tentative
                steps[nb] = cur_steps + 1

                # Weighted A*: increase heuristic influence (f = g + w*h)
                f = tentative + weight * heuristic_fn(nb, goal)
                heappush(open_heap, (f, nb))

    return None  # no path found


def route_a_star(
    city,
    events,
    occupancy,
    start: Node,
    goal: Node,
    *,
    weight: float = 1.0,
    start_tick: int = 0,
    eta_per_edge: int = 1,
    ignore_capacity: bool = False,
) -> Optional[List[Node]]:
    """Compute a route using (Weighted) A* with city, events and occupancy.

    This is a project-specific wrapper around `astar` that:
    - Uses the city's neighbor function and base edge costs.
    - Checks incident-based roadblocks via the events manager.
    - Enforces capacity constraints via the occupancy module.
    - Optionally accounts for time-dependent penalties on edges.

    Required City API:
        - city.neighbors(node) -> List[Node]
        - city.edge_cost(a, b) -> float
        - (optional) city.time_penalty(a, b, tick) -> float

    Args:
        city: City object providing graph neighbors and base edge costs.
        events: Event manager used to detect blocked edges (incidents).
        occupancy: Occupancy manager used to detect full edges.
        start (Node): Start node for the route.
        goal (Node): Goal node for the route.
        weight (float, optional): Heuristic weight for A*/Weighted A*.
            Typical values: 1.0 for exact A*, ~1.2 for faster approximate
            routing. Defaults to 1.0.
        start_tick (int, optional): Simulation tick at which the route
            is being computed. Defaults to 0.
        eta_per_edge (int, optional): Estimated ticks per edge, used to
            compute arrival ticks in the cost function. Defaults to 1.
        ignore_capacity (bool, optional): If True, capacity constraints from
            `occupancy.is_full` are ignored (useful for emergency vehicles).
            Defaults to False.

    Returns:
        Optional[List[Node]]: List of nodes representing the route from
        start to goal, or None if no feasible route exists.
    """

    def is_forbidden(a: Node, b: Node) -> bool:
        # Physical closures / incidents
        if events and hasattr(events, "is_blocked") and events.is_blocked(a, b):
            return True
        # Capacity constraints for normal vehicles
        if (
            not ignore_capacity
            and occupancy
            and hasattr(occupancy, "is_full")
            and occupancy.is_full(a, b)
        ):
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


def route_weighted(
    city,
    events,
    occupancy,
    start: Node,
    goal: Node,
    *,
    start_tick: int = 0,
    eta_per_edge: int = 1,
    weight: float = 1.2,
) -> Optional[List[Node]]:
    """Compute a near-optimal route using Weighted A* (recommended for vehicles).

    This is a convenience wrapper around `route_a_star` configured for
    standard vehicles. It uses a heuristic weight greater than 1.0 to
    trade a small amount of optimality for faster search.

    Args:
        city: City object providing graph neighbors and base edge costs.
        events: Event manager used to detect blocked edges (incidents).
        occupancy: Occupancy manager used to detect full edges.
        start (Node): Start node for the route.
        goal (Node): Goal node for the route.
        start_tick (int, optional): Simulation tick at which the route
            is being computed. Defaults to 0.
        eta_per_edge (int, optional): Estimated ticks per edge. Defaults to 1.
        weight (float, optional): Heuristic weight for Weighted A*. Defaults
            to 1.2.

    Returns:
        Optional[List[Node]]: Near-optimal path from start to goal, or None
        if no feasible route exists.
    """
    return route_a_star(
        city,
        events,
        occupancy,
        start,
        goal,
        weight=weight,
        start_tick=start_tick,
        eta_per_edge=eta_per_edge,
    )


def route_exact(
    city,
    events,
    occupancy,
    start: Node,
    goal: Node,
    *,
    start_tick: int = 0,
    eta_per_edge: int = 1,
    ignore_capacity: bool = False,
) -> Optional[List[Node]]:
    """Compute an exact A* route (recommended for emergency vehicles).

    This wrapper calls `route_a_star` with weight=1.0, corresponding to
    standard A*, and optionally ignores capacity constraints. It is
    suitable for agents where obtaining the best possible route is
    more important than search speed.

    Args:
        city: City object providing graph neighbors and base edge costs.
        events: Event manager used to detect blocked edges (incidents).
        occupancy: Occupancy manager used to detect full edges.
        start (Node): Start node for the route.
        goal (Node): Goal node for the route.
        start_tick (int, optional): Simulation tick at which the route
            is being computed. Defaults to 0.
        eta_per_edge (int, optional): Estimated ticks per edge. Defaults to 1.
        ignore_capacity (bool, optional): If True, edges considered "full"
            by the occupancy manager may still be used. This is typically
            useful for emergency vehicles. Defaults to False.

    Returns:
        Optional[List[Node]]: Path from start to goal, or None if no feasible
        route exists.
    """
    return route_a_star(
        city,
        events,
        occupancy,
        start,
        goal,
        weight=1.0,
        start_tick=start_tick,
        eta_per_edge=eta_per_edge,
        ignore_capacity=ignore_capacity,
    )