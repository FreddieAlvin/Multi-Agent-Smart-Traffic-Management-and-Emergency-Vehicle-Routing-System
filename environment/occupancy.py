from collections import defaultdict

class Occupancy:
    """
    Keeps track of which vehicles are on each edge (u, v)
    and computes both occupancy (count) and density (0..1) based on capacity.
    """

    def __init__(self, default_capacity: int = 5):
        # Example: road_usage[(u, v)] = {"veh1", "veh7", ...}
        self.road_usage = defaultdict(set)
        # Capacity per edge; by default, we use default_capacity
        self.capacity = defaultdict(lambda: default_capacity)

    # --- Capacity configuration (optional per edge) ---
    def set_capacity(self, u, v, cap: int) -> None:
        """Sets a specific capacity for the edge (u, v)."""
        self.capacity[(u, v)] = max(int(cap), 1)

    # --- Vehicle entering / leaving an edge ---
    def enter(self, u, v, vehicle_id: str) -> None:
        """Registers that a vehicle has entered the edge (u, v)."""
        self.road_usage[(u, v)].add(vehicle_id)

    def leave(self, u, v, vehicle_id: str) -> None:
        """Registers that a vehicle has left the edge (u, v)."""
        self.road_usage[(u, v)].discard(vehicle_id)

    # --- Quick queries ---
    def count(self, u, v) -> int:
        """Returns the number of vehicles currently on the edge (u, v)."""
        return len(self.road_usage[(u, v)])

    def rho(self, u, v) -> float:
        """
        Normalized density: count / capacity, limited to 1.0.
        Useful for dynamic routing cost and adaptive traffic light control.
        """
        cap = max(self.capacity[(u, v)], 1)
        return min(self.count(u, v) / cap, 1.0)

    def is_full(self, u, v, threshold: float = 1.0) -> bool:
        """
        Indicates whether the edge is 'full' (rho >= threshold).
        By default, considers full when rho == 1.0.
        """
        return self.rho(u, v) >= threshold