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
# "count" counts records; "quantity" counts things in the world -- units of stock,
# pieces on order. They format differently and mean different things, and calling a
# quantity a count invites someone to read 12,000 units as 12,000 rows.
UNITS = ("currency", "count", "quantity", "days", "percent", "ratio")

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

    agg: str = "sum"                  # sum | count | count_distinct | avg | max | top | ratio
    filters: dict = field(default_factory=dict)

    # A window of time, measured back from where the data ends rather than from today.
    # {"field": "posting_date", "window": "last_full_month"}; windows are
    # last_full_month, last_full_months_<n> and last_days_<n>. On a dataset that stops
    # in August 2025, "last month" measured from today is an empty month, and a card
    # reading GHS 0 under "Money in, month" says the business took no money -- which is
    # what the Home card said until 18 Oct 2026. The window is resolved per business,
    # written into the drill filters so the records match the figure, and named in the
    # note as {period}.
    period: dict | None = None

    # For agg="top": the best (or worst) of a set of groups -- "Best month", "Top
    # supplier", "Worst shortfall". group_by names a dimension, or "month:<date field>"
    # for calendar months. group_agg is how each group is totalled (sum | count | max);
    # top_n how many of the leading groups are added together ("Top 2 suppliers");
    # order "desc" for the largest, "asc" for the smallest. as_share turns the result
    # into a percentage of every group together, so "57%" says of what. negate writes a
    # shortfall (a negative available quantity) as the positive number short. The
    # winning group is named in the note as {group}.
    group_by: str | None = None
    group_agg: str = "sum"
    top_n: int = 1
    order: str = "desc"
    as_share: bool = False
    negate: bool = False

    # For count_distinct: which column's distinct values to count. "How many
    # departments" is a count of distinct departments among people, not a count of
    # people -- and counting rows there would report headcount under a label that
    # says departments.
    distinct_on: str | None = None

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
        if self.agg not in AGGS:
            problems.append(f"{self.key}: agg {self.agg!r} is not one of {AGGS}")
        if self.agg in ("avg", "max") and self.measure == "*":
            problems.append(f"{self.key}: cannot take the {self.agg} of '*'")
        problems += self._validate_period() + self._validate_top()
        if self.agg == "count_distinct" and not self.distinct_on:
            problems.append(
                f"{self.key}: count_distinct needs distinct_on to say which column's "
                f"distinct values are being counted")
        if self.distinct_on and self.agg != "count_distinct":
            problems.append(
                f"{self.key}: distinct_on only means something for count_distinct")
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

    def _validate_period(self) -> list[str]:
        if self.period is None:
            return []
        from command_center.facts.schema import DATE_FIELDS
        p = self.period
        out = []
        if p.get("field") not in DATE_FIELDS.get(self.fact, ()):
            out.append(f"{self.key}: period field {p.get('field')!r} is not a date on "
                       f"{self.fact}")
        if not _WINDOW.match(str(p.get("window", ""))):
            out.append(f"{self.key}: period window {p.get('window')!r} is not "
                       f"last_full_month, last_full_months_<n> or last_days_<n>")
        if self.agg == "ratio":
            out.append(f"{self.key}: a ratio takes its window from its parts; give the "
                       f"numerator and denominator the period instead")
        return out

    def _validate_top(self) -> list[str]:
        if self.agg != "top":
            if self.group_by or self.as_share or self.negate or self.top_n != 1:
                return [f"{self.key}: group_by, top_n, as_share and negate only mean "
                        f"something for agg='top'"]
            return []
        from command_center.facts.schema import DATE_FIELDS, DIMENSIONS
        out = []
        g = self.group_by or ""
        if g.startswith("month:"):
            if g[6:] not in DATE_FIELDS.get(self.fact, ()):
                out.append(f"{self.key}: {g!r} groups by a field that is not a date on "
                           f"{self.fact}")
        elif g not in DIMENSIONS.get(self.fact, ()):
            out.append(f"{self.key}: group_by {g!r} is not a dimension of {self.fact}")
        if self.group_agg not in ("sum", "count", "max"):
            out.append(f"{self.key}: group_agg {self.group_agg!r} is not sum, count or max")
        if self.group_agg != "count" and self.measure == "*":
            out.append(f"{self.key}: a {self.group_agg} over groups needs a measure")
        if self.order not in ("desc", "asc"):
            out.append(f"{self.key}: order {self.order!r} is not desc or asc")
        if self.top_n < 1:
            out.append(f"{self.key}: top_n must be at least 1")
        if g.startswith("month:") and self.top_n != 1:
            out.append(f"{self.key}: the top few months together is not one month")
        if self.group_agg == "max" and self.top_n != 1:
            out.append(f"{self.key}: adding up the maxima of several groups means nothing")
        if self.as_share and (self.unit != "percent" or self.group_agg == "max"):
            out.append(f"{self.key}: as_share is a percentage of a total, so it needs "
                       f"unit='percent' and a sum or count")
        if "{group}" not in self.note:
            out.append(f"{self.key}: a top figure must name its group in the note "
                       f"({{group}}), or '57%' is a share of nobody in particular")
        return out


AGGS = ("sum", "count", "count_distinct", "avg", "max", "top", "ratio")

# Tokens a note may use that are not KPI keys: the KPI's own window and winning group.
RESERVED_TOKENS = ("period", "group")

import re as _re
_WINDOW = _re.compile(r"^(last_full_month|last_full_months_([2-9]|1[0-9]|2[0-4])|"
                      r"last_days_([1-9][0-9]{0,2}))$")


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
            if token in RESERVED_TOKENS:
                if token == "period" and not k.period:
                    problems.append(f"{k.key}: the note names {{period}} but the KPI "
                                    f"has no period")
                continue
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
        if token in RESERVED_TOKENS:
            continue
        referenced, wants_share = _resolve_token(token)
        needed.add(referenced)
        if wants_share and referenced in REGISTRY:
            needed.add(REGISTRY[referenced].share_of)
    return {n for n in needed if n and n != key}


def load_all() -> dict[str, Kpi]:
    """Import every definition module. Registration happens on import."""
    if not REGISTRY:
        from command_center.kpi import (  # noqa: F401
            buying, operations, sales, stock)
        problems = validate_registry()
        if problems:
            raise ValueError("; ".join(problems))
    return REGISTRY
