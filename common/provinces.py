"""Iran's thirty-one provinces, from the one list the panel already uses.

The customer forms fill their «استان» select from `iran-provinces.json` — the
same file the choropleth map on the customers page draws — so the names a
person picks are exactly the names the map can place. The server reads that
file too rather than keeping a second copy that could drift from it (2.19.0,
when users gained a province of their own and it had to be validated here).
"""

import json
from functools import lru_cache
from pathlib import Path

_MAP_FILE = Path(__file__).resolve().parent / "static" / "common" / "iran-provinces.json"


@lru_cache(maxsize=1)
def province_names():
    """The Persian names, in the order the map file lists them."""
    data = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
    return tuple(entry["name"] for entry in data["provinces"].values())


def is_province(value):
    return value in province_names()
