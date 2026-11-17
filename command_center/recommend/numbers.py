"""The one check of the numbers an AI writes for a reader (17 Nov 2026).

Every AI text the platform shows -- the Daily Brief, Explain This, the Executive
Summary's short version and the daily AI review -- may state only figures it was given.
Three checkers did this before, and each was wrong in its own way:

* too weak: every run of digits anywhere in what the AI was given was allowed -- the
  dateline's day and year, "4 of 6", a rule's 60% threshold, the digits in a document's
  name -- and so were most roundings of them, with the sign thrown away and the unit
  ignored. "Overall Business Health is 17%" passed on the 17th of the month, and "Money in
  rose 8%" passed when it fell 8%;
* too strict: "GHS 341,565" was refused when it was given as "341,565.00".

So here a figure is a value with a unit -- an amount of money, a percentage, a count, a
date -- and the AI's text passes only when each of its figures matches one it was given:

* the same kind (a percentage is never a count or money; money and plain amounts of 100
  or more may stand for each other, as "GHS 341,565" and "341,565.00" do);
* the same value, to the precision the AI wrote it: "GHS 7.25M" and "GHS 7.3M" stand for
  7,254,533, "GHS 7M" does not (rounding is allowed to within 2% of the figure, never
  further), and a percentage to the whole point it is written in;
* in the same direction: "rose", "up", "fell", "down" and their like, said of a figure,
  must agree with the change it was given -- an "8% fall" given is not an "8% rise";
* dates are checked as dates (a date the AI writes must be one it was given), never as
  numbers; digits inside a document's or a key's name (SAL-ORD-2025-00942, F1, M:cash)
  and a numbered list's own numbers are not figures.

Given(...) collects what the AI was given (text, or values with their unit) and
problems(text, given) says what in the AI's text does not match, [] when nothing.
Thousands separators and trailing zeros are never a difference.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

CURRENCIES = {"GHS", "USD", "EUR", "GBP", "NGN", "KES", "ZAR", "XOF", "XAF", "CNY", "INR",
              "AED", "CAD", "AUD", "JPY", "CHF", "EGP", "TZS", "UGX", "RWF", "SLL", "GMD",
              "LRD", "ZMW", "BWP", "MAD"}
_SYMBOLS = ("GH₵", "₵", "$", "£", "€")
_MONTH = ("January|February|March|April|May|June|July|August|September|October|November|"
          "December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec")
_MONTHS = {m.lower()[:3]: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
_ORD = r"(?:st|nd|rd|th)?"
DATE = re.compile(
    r"(?P<iso>\b(?P<iy>\d{4})-(?P<im>\d{2})-(?P<id>\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?)"
    rf"|(?P<dmy>\b(?P<d1>\d{{1,2}}){_ORD}\s+(?P<m1>{_MONTH})\.?(?:,?\s+(?P<y1>\d{{4}}))?\b)"
    rf"|(?P<mdy>\b(?P<m2>{_MONTH})\.?\s+(?P<d2>\d{{1,2}}){_ORD},?\s+(?P<y2>\d{{4}})\b)"
    rf"|(?P<my>\b(?P<m3>{_MONTH})\.?\s+(?P<y3>\d{{4}})\b)"
    rf"|(?P<md>\b(?P<m4>{_MONTH})\.?\s+(?P<d4>\d{{1,2}}){_ORD}\b)"
    r"|(?P<time>\b\d{1,2}:\d{2}\b)"
    # a year on its own ("in 2026"), not an amount ("GHS 2026", "2026%", "2,026")
    r"|(?P<year>(?<![\w.,$£€₵])(?<![A-Z]{3} )\b(?:19|20)\d{2}\b(?![.,]\d|\s?(?:%|percent|k\b|K\b|m\b|M\b|million|bn)))")
# Not figures: a document's or record's name (letters and digits joined by - / _ .), a
# short code (F1, Q4, W46), a pack key (M:cash_in, L:rule), an ordinal, a list's numbers.
_NAMES = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:[-/_][A-Za-z0-9]+)*[-/_]\d[A-Za-z0-9]*(?:[-/_][A-Za-z0-9]+)*\b"
    r"|\b[A-Za-z]{1,2}\d+\b|\b[MLFAO]:[a-z0-9_]+\b|\b\d+(?:st|nd|rd|th)\b"
    r"|(?m:^\s*\d{1,2}[.)](?=\s))")
_CUR = "|".join(sorted(CURRENCIES)) + "|" + "|".join(re.escape(s) for s in _SYMBOLS)
NUMBER = re.compile(
    rf"(?P<cur>(?<![A-Za-z])(?:{_CUR})\s?)?"
    r"(?P<sign>[-−–](?=\d))?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<mag>\s?(?:thousand|million|billion|bn|mn)\b|(?:k|K|m|M|B)\b|\sM\b)?"
    r"(?P<pct>\s?(?:%|per\s?cent\b|percent\b|percentage points?\b))?")
_SCALE = {"thousand": 3, "k": 3, "million": 6, "mn": 6, "m": 6, "billion": 9, "bn": 9, "b": 9}
UP = ("rose", "rise", "rises", "risen", "rising", "up", "increased", "increase", "increases",
      "increasing", "grew", "grown", "grows", "growing", "growth", "climbed", "climb",
      "jumped", "jump", "gained", "gain", "higher", "more", "▲", "improved", "improvement")
DOWN = ("fell", "fall", "falls", "fallen", "falling", "down", "decreased", "decrease",
        "decreases", "decreasing", "dropped", "drop", "drops", "declined", "decline",
        "declines", "declining", "shrank", "shrunk", "slipped", "lower", "less", "fewer", "▼",
        "worsened")
_WORD = {w: 1 for w in UP} | {w: -1 for w in DOWN}
_BEFORE = re.compile(r"(?P<w>▲|▼|\b[a-z]+\b)\s*(?:(?P<to>to)|by|of|some|about|nearly|almost|"
                     r"around|roughly|just)?\s*$", re.I)
_AFTER = re.compile(r"^\s*(?:points?\s+)?(?P<w>[a-z]+|▲|▼)", re.I)


# A bound, not a figure: "2 below 60%", "over 90 days", "more than 30". Given as a bound,
# it may be written only as a bound -- a rule's threshold is not a finding.
_BOUND = re.compile(r"\b(?:below|above|under|over|beyond|than|least|most|within|exceeds?|"
                    r"exceeding|threshold(?:\s+of)?)\s*$", re.I)


class Figure:
    __slots__ = ("value", "unit", "step", "dir", "level", "line_dir", "raw", "bound")

    def __init__(self, value, unit, step=None, direction=None, level=False, raw="",
                 bound=False):
        self.value, self.unit, self.step = abs(Decimal(value)), unit, step
        self.dir, self.level, self.line_dir, self.raw = direction, level, None, raw
        self.bound = bound


def _dec(s) -> Decimal | None:
    try:
        return Decimal(str(s).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _direction(text, m) -> tuple:
    """(+1, -1 or None, whether it is a level -- "rose to X" -- rather than a change)."""
    before = _BEFORE.search(text[max(0, m.start() - 30):m.start()])
    if before and before.group("w").lower() in _WORD:
        if before.group("w").lower() == "up" and before.group("to"):
            return None, False              # "up to 30 days": a limit, not a rise
        return _WORD[before.group("w").lower()], bool(before.group("to"))
    after = _AFTER.search(text[m.end():m.end() + 20])
    if after and after.group("w").lower() in _WORD:
        return _WORD[after.group("w").lower()], False
    return None, False


def _dates(text) -> tuple:
    """([(kind, value)], text with the dates blanked)."""
    found = []

    def take(m):
        g = m.groupdict()
        try:
            if g["iso"]:
                found.append(("ymd", (int(g["iy"]), int(g["im"]), int(g["id"]))))
            elif g["dmy"]:
                mo = _MONTHS[g["m1"].lower()[:3]]
                found.append(("ymd", (int(g["y1"]), mo, int(g["d1"]))) if g["y1"]
                             else ("md", (mo, int(g["d1"]))))
            elif g["mdy"]:
                found.append(("ymd", (int(g["y2"]), _MONTHS[g["m2"].lower()[:3]], int(g["d2"]))))
            elif g["my"]:
                found.append(("ym", (int(g["y3"]), _MONTHS[g["m3"].lower()[:3]])))
            elif g["md"]:
                found.append(("md", (_MONTHS[g["m4"].lower()[:3]], int(g["d4"]))))
            elif g["year"]:
                found.append(("y", int(g["year"])))
            else:
                found.append(("time", m.group(0)))
        except (KeyError, TypeError, ValueError):
            pass
        return " " * len(m.group(0))
    return found, DATE.sub(take, text or "")


def _blank_names(text) -> str:
    return _NAMES.sub(lambda m: " " * len(m.group(0)), text)


def figures_in(text: str) -> tuple:
    """([Figure], [date]) in a text: every figure with its unit, precision and direction,
    and every date, apart."""
    dates, text = _dates(_blank_names(str(text or "")))
    out = []
    for m in NUMBER.finditer(text):
        num = m.group("num")
        value = _dec(num)
        if value is None:
            continue
        mag = (m.group("mag") or "").strip()
        scale = _SCALE.get(mag.lower(), 0)
        decimals = len(num.split(".")[1]) if "." in num else 0
        step = Decimal(1).scaleb(scale - decimals)
        unit = ("percent" if m.group("pct") else "currency" if m.group("cur") else "count")
        d, level = _direction(text, m)
        bound = bool(_BOUND.search(text[max(0, m.start() - 20):m.start()]))
        out.append(Figure(value.scaleb(scale), unit, step, d, level, m.group(0).strip(), bound))
    return out, dates


class Given:
    """What the AI was given: figures with their units (from text, or values) and dates."""

    def __init__(self):
        self.figures, self.dates = [], set()

    def text(self, *texts):
        """Each text is one line: a level in it takes the direction of the change beside
        it ("GHS 380,574 ... (up 8% on September)")."""
        for t in texts:
            for line in str(t or "").splitlines() or [""]:
                figs, dates = figures_in(line)
                moves = {f.dir for f in figs if f.dir is not None and not f.level}
                for f in figs:
                    f.line_dir = next(iter(moves)) if len(moves) == 1 else None
                self.figures += figs
                self.dates |= set(dates)
        return self

    def value(self, v, unit="count", direction=None):
        """A figure given as a number: unit is "currency", "percent" or "count"; a signed
        change may name its direction (+1 / -1) or leave it to the sign."""
        if v is None or isinstance(v, bool):
            return self
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            return self
        f = Figure(d, unit, None, direction if direction is not None else None)
        self.figures.append(f)
        return self

    def date(self, *texts):
        """Dates only (a dateline, a period's label): their digits are never figures."""
        for t in texts:
            self.dates |= set(_dates(_blank_names(str(t or "")))[0])
        return self


def _kind_ok(f: Figure, g: Figure) -> bool:
    if f.unit == g.unit:
        return True
    # Money with or without its currency: "GHS 341,565" and "341,565.00" are one amount.
    return ({f.unit, g.unit} == {"currency", "count"} and f.value >= 100)


def _value_ok(f: Figure, g: Figure) -> bool:
    half = (f.step or Decimal(1)) / 2
    if f.unit == "percent" or g.unit == "percent":
        tol = half
    else:
        tol = min(half, max(g.value * Decimal("0.02"), Decimal("0.5")))
    return abs(f.value - g.value) <= tol


def _date_ok(d, given: set) -> bool:
    kind, v = d
    if d in given:
        return True
    if kind == "ym":
        return any(k == "ymd" and (x[0], x[1]) == v for k, x in given)
    if kind == "md":
        return any(k == "ymd" and (x[1], x[2]) == v for k, x in given)
    if kind == "ymd":
        return ("md", (v[1], v[2])) in given and any(k in ("ym", "ymd") and x[0] == v[0]
                                                     for k, x in given)
    if kind == "y":
        return any(k in ("ym", "ymd") and x[0] == v for k, x in given)
    return False


def _show(f: Figure) -> str:
    n = format(f.value.normalize(), "f")
    n = n.rstrip("0").rstrip(".") if "." in n else n
    return n + ("%" if f.unit == "percent" else "")


def problems(text: str, given: Given) -> list:
    """What in `text` is not among the figures given: [] when everything matches."""
    figs, dates = figures_in(text)
    out = []
    for f in figs:
        same = [g for g in given.figures if _kind_ok(f, g) and _value_ok(f, g)
                and (f.bound or not g.bound)]
        if not same:
            out.append(_show(f))
            continue
        if f.dir is not None:
            had = [(g.line_dir if f.level else g.dir) for g in same]
            if f.dir not in had:
                word = "a rise" if f.dir > 0 else "a fall"
                out.append(f"{_show(f)} as {word}")
    out += [" ".join(map(str, v)) if isinstance(v, tuple) else str(v)
            for d in dates if not _date_ok(d, given.dates) for v in [d[1]]]
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq
