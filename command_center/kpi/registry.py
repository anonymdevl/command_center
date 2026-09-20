"""What a KPI is, before anyone computes one.

A KPI here is data, not code: a row in a registry that names the fact it reads,
the measure it aggregates, the filters that scope it, and — two fields that exist
because of mistakes already made on this engagement —

    as_of_basis   every figure derived from a point in time carries that point.
                  Reading an ageing figure as "today" on a restored dataset turned
                  a thirteen-month-old snapshot into a false finding about how the
                  client collects.

    subset_of     a figure computed over a ranked or limited set says what it is a
                  subset of. GHS 4,592,482 was reported as the whole receivable
                  for most of a day; it was the ten largest customers, and the
                  whole was 9,177,568.91.

Neither is a convention anyone has to remember. A definition without them does
not validate, and preflight fails the build.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Units decide formatting at the edge, not in the engine. A KPI says what kind of
# quantity it is; the interface decides how to write it.
UNITS = ("currency", "count", "days", "percent", "ratio")

# Which direction is bad. Used for tone, never to editorialise the number.
DIRECTIONS = ("higher_is_worse", "higher_is_better", "neutral")


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    fact: str
    measure: str                      # a column, or "*" to count rows
    unit: str
    direction: str = "neutral"

    agg: str = "sum"                  # sum | count | ratio
    filters: dict = field(default_factory=dict)

    # A ratio is not aggregated from a table; it is two other KPIs divided. Margin
    # percent is the case that forced this: the correct denominator is the net of
    # lines that carry a valuation, not the net of every line. Dividing by the
    # wrong whole gives a plausible number that is quietly wrong, which is the
    # class of error this engine exists to prevent.
    numerator: str | None = None
    denominator: str | None = None

    # KPIs that must add up to this one. Declared, then checked against the data:
    # ar_total says it is ar_over_90 + ar_inside_90, so a new ageing bucket that
    # belongs to neither is caught instead of silently vanishing from both.
    components: tuple = ()

    # The sentence under the figure. May reference other keys in the same set,
    # which is how "74% of the balance" stays consistent with the balance.
    note: str = ""

    # Where "which records?" goes. Without it a card cannot honour the chevron.
    drill_filters: dict | None = None

    # Stated, never inferred.
    as_of_basis: str = "data_horizon"  # data_horizon | today | none
    subset_of: str | None = None       # prose: what the whole is

    # The key this figure is a share of. A note may write "{self_share} of the
    # balance"; the denominator is this KPI, named here. The engine used to assume
    # ar_total for every share, which would have quietly produced a wrong
    # percentage the first time a non-receivable KPI wanted one.
    share_of: str | None = None

    def validate(self) -> list[str]:
        problems = []
        if self.unit not in UNITS:
            problems.append(f"{self.key}: unit {self.unit!r} is not one of {UNITS}")
        if self.direction not in DIRECTIONS:
            problems.append(f"{self.key}: direction {self.direction!r} is unknown")
        if self.agg not in ("sum", "count", "ratio"):
            problems.append(f"{self.key}: agg {self.agg!r} is not sum, count or ratio")
        if self.agg == "sum" and self.measure == "*":
            problems.append(f"{self.key}: cannot sum '*'")
        if self.agg == "ratio":
            if not (self.numerator and self.denominator):
                problems.append(
                    f"{self.key}: a ratio needs both numerator and denominator")
            if self.unit not in ("percent", "ratio"):
                problems.append(
                    f"{self.key}: a ratio must be a percent or a ratio, not "
                    f"{self.unit!r}")
            if self.numerator == self.denominator:
                problems.append(f"{self.key}: numerator and denominator are the same")
        elif self.numerator or self.denominator:
            problems.append(
                f"{self.key}: numerator/denominator only mean something for a ratio")
        if self.as_of_basis not in ("data_horizon", "today", "none"):
            problems.append(f"{self.key}: as_of_basis {self.as_of_basis!r} is unknown")
        if "_share}" in self.note and not self.share_of:
            problems.append(
                f"{self.key}: the note asks for a share but share_of names no "
                f"denominator. A share whose whole is guessed is a wrong number.")
        if self.share_of == self.key:
            problems.append(f"{self.key}: share_of points at itself")
        if self.drill_filters is None and self.agg != "ratio":
            problems.append(
                f"{self.key}: no drill_filters. Every figure opens to its records; "
                f"a KPI that cannot be opened breaks the card contract.")
        return problems


REGISTRY: dict[str, Kpi] = {}


def register(*kpis: Kpi) -> None:
    for k in kpis:
        problems = k.validate()
        if problems:
            raise ValueError("; ".join(problems))
        if k.key in REGISTRY:
            raise ValueError(
                f"KPI {k.key!r} is already registered. Two definitions of one "
                f"figure drift apart, which is how cards and colours went wrong "
                f"before.")
        REGISTRY[k.key] = k


def get(key: str) -> Kpi:
    if key not in REGISTRY:
        raise KeyError(f"No KPI {key!r}. Known: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[key]


def validate_registry() -> list[str]:
    """Checks that need the whole registry, not one definition.

    register() cannot do these: a KPI may legitimately reference a key that is
    defined further down the same file.
    """
    problems = []
    for k in REGISTRY.values():
        for role, ref in (("numerator", k.numerator), ("denominator", k.denominator)):
            if ref and ref not in REGISTRY:
                problems.append(f"{k.key}: {role} {ref!r} is not a registered KPI")
            elif ref and REGISTRY[ref].agg == "ratio":
                problems.append(
                    f"{k.key}: {role} {ref!r} is itself a ratio. A ratio of ratios "
                    f"is almost always a mistake; state the measure you mean.")
        for part in k.components:
            if part not in REGISTRY:
                problems.append(f"{k.key}: component {part!r} is not a registered KPI")
            elif REGISTRY[part].fact != k.fact:
                problems.append(
                    f"{k.key}: component {part!r} reads a different fact, so adding "
                    f"them up compares unlike things")
            elif REGISTRY[part].unit != k.unit:
                problems.append(f"{k.key}: component {part!r} has a different unit")
        if k.share_of and k.share_of not in REGISTRY:
            problems.append(
                f"{k.key}: share_of {k.share_of!r} is not a registered KPI")
        for token in _tokens(k.note):
            referenced, wants_share = _resolve_token(token)
            if referenced not in REGISTRY:
                problems.append(
                    f"{k.key}: note references {{{token}}}, and {referenced!r} is "
                    f"not a registered KPI")
            elif wants_share and not REGISTRY[referenced].share_of:
                problems.append(
                    f"{k.key}: note asks for {referenced!r} as a share, but that "
                    f"KPI names no denominator in share_of")
    return problems


def _resolve_token(token: str) -> tuple[str, bool]:
    """`{ar_over_90_share}` means ar_over_90, expressed as a share.

    A key that genuinely ends in _share would be ambiguous, so a key wins over the
    suffix reading.
    """
    if token in REGISTRY:
        return token, False
    if token.endswith("_share"):
        return token[: -len("_share")], True
    return token, False


def _tokens(note: str) -> list[str]:
    import re
    return re.findall(r"\{([a-z0-9_]+)\}", note or "")


def value_dependencies(key: str) -> set[str]:
    """KPIs whose *value* must exist before this one can be computed.

    Only a ratio has these. A note reference is not one: notes are rendered after
    every value in the set is known, which is what lets ar_total say how many
    invoices there are while ar_count says what they are worth. Treating those as
    ordering constraints made them a cycle, the dependency sort gave up, and
    ar_over_90_pct was evaluated before its own denominator -- printing an em dash
    where 73.8% belonged.
    """
    kpi = get(key)
    needed = {kpi.numerator, kpi.denominator} if kpi.agg == "ratio" else set()
    return {n for n in needed if n and n != key}


def dependencies(key: str) -> set[str]:
    """Every other KPI needed to compute or caption this one.

    evaluate_set() expands by this, so asking for a share alone still gets you a
    correct percentage rather than an em dash.
    """
    kpi = get(key)
    needed = {kpi.numerator, kpi.denominator}
    if kpi.share_of:
        needed.add(kpi.share_of)
    for token in _tokens(kpi.note):
        referenced, wants_share = _resolve_token(token)
        needed.add(referenced)
        if wants_share and referenced in REGISTRY:
            needed.add(REGISTRY[referenced].share_of)
    return {n for n in needed if n and n != key}


def load_all() -> dict[str, Kpi]:
    """Import every definition module. Registration happens on import."""
    if not REGISTRY:
        from command_center.kpi import sales  # noqa: F401
        problems = validate_registry()
        if problems:
            raise ValueError("; ".join(problems))
    return REGISTRY
