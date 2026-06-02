from __future__ import annotations


def speed_kmh_from_delta(delta_s: float, distance_m: float = 2.0) -> float:
    if delta_s <= 0:
        return 0.0
    return (distance_m / delta_s) * 3.6
