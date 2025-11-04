from environment.city import TRAFFIC_LIGHTS

def nearest_traffic_light(pos):
    """Return the JID of the nearest traffic light based on Manhattan distance."""
    x, y = pos
    nearest = min(TRAFFIC_LIGHTS.items(),
                  key=lambda t: abs(t[1][0]-x) + abs(t[1][1]-y))
    return nearest[0]
