"""Every ingestor, in one place.

api/ingest.py imported INGESTORS from ingest.sales, which meant adding a fact to a
new module left it invisible to the runner with nothing to indicate why. The
registry is assembled here instead, and preflight fails if a fact the schema maps
has no ingestor.
"""

from __future__ import annotations

from command_center.ingest import buying, operations, sales, stock

INGESTORS: dict = {}
for module in (sales, buying, stock, operations):
    for fact, cls in module.INGESTORS.items():
        if fact in INGESTORS:
            raise ValueError(
                f"Two ingestors claim {fact!r}: {INGESTORS[fact].__name__} and "
                f"{cls.__name__}. One fact, one source grain, one loader.")
        INGESTORS[fact] = cls


def get(fact: str):
    cls = INGESTORS.get(fact)
    if not cls:
        raise KeyError(f"No ingestor for {fact!r}. Known: {', '.join(sorted(INGESTORS))}")
    return cls
