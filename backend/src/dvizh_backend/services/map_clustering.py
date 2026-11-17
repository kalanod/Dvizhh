"""Deterministic adaptive quadtree refinement with a hard marker budget."""

import math

MAX_MARKERS = 30
MAX_LATITUDE = 85.0511287798066


def cell_for(longitude: float, latitude: float, level: int) -> tuple[int, int]:
    scale = 2**level
    radians = math.radians(max(-MAX_LATITUDE, min(MAX_LATITUDE, latitude)))
    x = min(scale - 1, math.floor((longitude + 180) / 360 * scale))
    y = min(
        scale - 1,
        max(
            0,
            math.floor(
                (1 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2 * scale
            ),
        ),
    )
    return x, y


def refinement_level(group, maximum: int) -> int | None:
    if group["count"] <= 1 or group["west"] == group["east"] and group["south"] == group["north"]:
        return None
    # Skip empty single-child levels instead of issuing a DB query per zoom step.
    for level in range(group["level"] + 1, maximum + 1):
        if cell_for(group["west"], group["south"], level) != cell_for(
            group["east"], group["north"], level
        ):
            return level
    return None


async def cluster_map(repository, zoom: float):
    maximum = max(0, min(24, int(zoom) + 2))
    level = maximum
    while True:
        groups = await repository.groups(level)
        if len(groups) <= MAX_MARKERS:
            break
        level -= 1
    blocked = set()
    while len(groups) < MAX_MARKERS:
        candidates = sorted(
            groups, key=lambda item: (-item["count"], item["level"], item["x"], item["y"])
        )
        refined = False
        for item in candidates:
            cell = (item["level"], int(item["x"]), int(item["y"]))
            next_level = refinement_level(item, maximum)
            if cell in blocked or next_level is None:
                continue
            children = await repository.groups(next_level, cell)
            if not children or len(groups) - 1 + len(children) > MAX_MARKERS:
                blocked.add(cell)
                continue
            groups.remove(item)
            groups.extend(children)
            refined = True
            break
        if not refined:
            break
    return sorted(groups, key=lambda item: (item["level"], item["x"], item["y"]))
