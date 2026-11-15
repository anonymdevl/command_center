"""A business's own normal range for a figure, and whether today's value is out of it.

Pure arithmetic over a series of (date, value) points: no frappe, no database, so it is
tested on crafted series and preflight can import it.

    baseline(points, grain)   the normal range of the LAST point, from the points before it
    change_band(points, ...)  how far the figure usually moves, for an adaptive threshold

Method, in order of preference:

  seasonal   monthly figures with at least 13 months: the expected value is the same
             month a year earlier times the business's recent trend (the median of the
             last three months' ratios to the same months a year before); the spread is
             the median absolute deviation of what the same method would have expected
             for each earlier month. Needs six such earlier months to measure the spread.
  rolling    otherwise: the median and median absolute deviation of the last 12 months
             (monthly) or 90 days (daily). Needs MIN_POINTS of them.
  learning   fewer points than that: no range is invented; the result says how many more
             weeks or months of data it needs.

The robust z-score is (value - expected) / (1.4826 x MAD): about a standard deviation's
worth for well-behaved figures, and not dragged about by one extreme month. A point is
an anomaly from |z| >= Z_ANOMALY. A change-point ("level shift") is the median of the
latest few points sitting more than Z_SHIFT spreads from the median of the points before
them, every one of them on the same side.
"""

from __future__ import annotations

import datetime as _dt
from statistics import median

MAD_SCALE = 1.4826
Z_ANOMALY = 3.0
Z_SHIFT = 3.0
BAND_Z = 2.0
MIN_POINTS = {"month": 6, "day": 28}
WINDOW = {"month": 12, "day": 90}
SHIFT_RECENT = {"month": 3, "day": 7}
SEASONAL_MONTHS = 13
SEASONAL_RESIDUALS = 6
SPARK_POINTS = {"month": 24, "day": 60}


def _d(v) -> _dt.date:
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _mad(xs, centre) -> float:
    return median([abs(x - centre) for x in xs]) if xs else 0.0


def _floor_scale(scale, centre, values) -> float:
    """A spread of zero (a figure that never moved) would make any change infinite: the
    spread is at least 5% of the level, or of the largest value seen, or 1."""
    ref = max([abs(centre)] + [abs(v) for v in values] + [0.0])
    return max(scale, 0.05 * ref, 1e-9 if ref == 0 else 0.0) or 1.0


def _month_key(d: _dt.date) -> tuple:
    return (d.year, d.month)


def _needs(grain: str, have: int) -> str:
    need = MIN_POINTS[grain] - have
    if grain == "month":
        return f"Learning: needs {need} more month{'s' if need != 1 else ''} of data."
    weeks = max(1, -(-need // 7))
    return f"Learning: needs {weeks} more week{'s' if weeks != 1 else ''} of data."


def _shift(history, last_values, scale, centre, grain):
    """A level shift: the latest points all on one side of the earlier median, by more
    than Z_SHIFT spreads."""
    n = SHIFT_RECENT[grain]
    if len(last_values) < n or len(history) < MIN_POINTS[grain]:
        return None
    recent = last_values[-n:]
    m = median(recent)
    if abs(m - centre) <= Z_SHIFT * scale:
        return None
    up = m > centre
    if not all((v > centre) == up for v in recent):
        return None
    return {"direction": "up" if up else "down", "points": n, "level": round(m, 4),
            "before": round(centre, 4)}


def baseline(points, grain: str = "month", direction: str = "either") -> dict:
    """The normal range for the LAST point of `points` ([(date, value)], any order),
    worked out from the points before it.

    direction: "up_bad", "down_bad" or "either" -- which way an anomaly is a problem.
    """
    pts = sorted(((_d(d), float(v)) for d, v in points if v is not None), key=lambda p: p[0])
    out = {"grain": grain, "status": "learning", "method": None, "points": len(pts),
           "spark": [[str(d), round(v, 4)] for d, v in pts[-SPARK_POINTS[grain]:]]}
    if not pts:
        out["says"] = _needs(grain, 0)
        return out
    last_d, last_v = pts[-1]
    history = pts[:-1]
    out.update(latest=round(last_v, 4), latest_on=str(last_d))
    centre = scale = None

    if grain == "month" and len(pts) >= SEASONAL_MONTHS:
        by = {_month_key(d): v for d, v in pts}

        def ly(d):
            return by.get((d.year - 1, d.month))

        def trend_before(i):
            """The median ratio of the three months before pts[i] to a year earlier."""
            ratios = []
            for d, v in pts[max(0, i - 3):i]:
                b = ly(d)
                if b and b > 0 and v >= 0:
                    ratios.append(v / b)
            return median(ratios) if ratios else 1.0
        resid = []
        for i, (d, v) in enumerate(history):
            b = ly(d)
            if b is None:
                continue
            resid.append(v - b * trend_before(i))
        base = ly(last_d)
        if base is not None and len(resid) >= SEASONAL_RESIDUALS:
            trend = trend_before(len(pts) - 1)
            centre = base * trend
            scale = MAD_SCALE * _mad(resid, median(resid)) if resid else 0.0
            out.update(method="seasonal", same_month_last_year=round(base, 4),
                       trend=round(trend, 4))
    if centre is None:
        window = history[-WINDOW[grain]:] if grain == "month" else [
            p for p in history if (last_d - p[0]).days <= WINDOW["day"]]
        if len(window) < MIN_POINTS[grain]:
            out["says"] = _needs(grain, len(window))
            return out
        vals = [v for _, v in window]
        centre = median(vals)
        scale = MAD_SCALE * _mad(vals, centre)
        out["method"] = "rolling"
        out["window"] = len(window)
    scale = _floor_scale(scale, centre, [v for _, v in history[-WINDOW[grain]:]])
    z = (last_v - centre) / scale
    bad = {"up_bad": z > 0, "down_bad": z < 0}.get(direction, True)
    out.update(status="ready", centre=round(centre, 4), scale=round(scale, 4),
               low=round(centre - BAND_Z * scale, 4), high=round(centre + BAND_Z * scale, 4),
               z=round(z, 2), ratio=round(last_v / centre, 2) if centre else None,
               anomaly=bool(abs(z) >= Z_ANOMALY and bad))
    out["shift"] = _shift(history, [v for _, v in pts], scale, centre, grain)
    if out["shift"] and direction in ("up_bad", "down_bad"):
        out["shift"]["bad"] = (out["shift"]["direction"] == "up") == (direction == "up_bad")
    return out


def changes(points, kind: str = "pct", grain: str = "month") -> list:
    """The figure's own movements: each point against the same month a year before when
    the series has a year of them (as the rules compare), else against the point before.
    kind "pct" gives percentage changes, "points" differences. [(date, change)]."""
    pts = sorted(((_d(d), float(v)) for d, v in points if v is not None), key=lambda p: p[0])
    by = {_month_key(d): v for d, v in pts}
    yearly = grain == "month" and sum(1 for d, _ in pts if (d.year - 1, d.month) in by) >= 6
    out = []
    for i, (d, v) in enumerate(pts):
        if yearly:
            b = by.get((d.year - 1, d.month))
        else:
            b = pts[i - 1][1] if i else None
        if b is None:
            continue
        if kind == "pct":
            if b <= 0:
                continue
            out.append((d, 100.0 * (v - b) / b))
        else:
            out.append((d, v - b))
    return out


def change_band(points, kind: str = "pct", grain: str = "month") -> dict:
    """How far this figure usually moves: the median absolute change plus BAND_Z spreads.
    A move beyond it is unusual for this business. Learning until MIN_POINTS changes."""
    ch = changes(points, kind, grain)
    mags = [abs(c) for _, c in ch]
    if len(mags) < MIN_POINTS[grain]:
        return {"status": "learning", "changes": len(mags), "says": _needs(grain, len(mags))}
    centre = median(mags)
    scale = MAD_SCALE * _mad(mags, centre)
    return {"status": "ready", "changes": len(mags), "typical": round(centre, 2),
            "scale": round(scale, 2), "unusual_from": round(centre + BAND_Z * scale, 2),
            "basis": "the same month a year earlier" if _yearly(points, grain) else "the month before"}


def _yearly(points, grain) -> bool:
    pts = [_d(d) for d, v in points if v is not None]
    keys = {_month_key(d) for d in pts}
    return grain == "month" and sum(1 for d in pts if (d.year - 1, d.month) in keys) >= 6


def level_band(points, grain: str = "month") -> dict:
    """The usual upper edge of a level (a share, a percentage): the median of the
    business's own history plus BAND_Z spreads."""
    vals = [float(v) for _, v in sorted(points, key=lambda p: _d(p[0])) if v is not None]
    window = vals[-WINDOW[grain]:]
    if len(window) < MIN_POINTS[grain]:
        return {"status": "learning", "says": _needs(grain, len(window))}
    centre = median(window)
    scale = _floor_scale(MAD_SCALE * _mad(window, centre), centre, window)
    return {"status": "ready", "typical": round(centre, 2), "scale": round(scale, 2),
            "unusual_from": round(centre + BAND_Z * scale, 2), "basis": "its own last "
            f"{len(window)} {'months' if grain == 'month' else 'days'}"}


def trend(points) -> float | None:
    """Theil-Sen slope per point: the median of every pair's slope. None under 4 points."""
    vals = [float(v) for _, v in sorted(points, key=lambda p: _d(p[0])) if v is not None]
    if len(vals) < 4:
        return None
    slopes = [(vals[j] - vals[i]) / (j - i) for i in range(len(vals)) for j in range(i + 1, len(vals))]
    return median(slopes)
