"""Recommendations: what a business's figures say is worth doing, ranked by money at stake.

    rules.py    the library: each rule reads the platform's figures and facts (or a light
                live read of the business's ERPNext) and returns zero or more
                recommendations, every number in them from that data
    engine.py   evaluating the rules for one business, ranking them, and keeping each
                one's state (Done, Not Relevant, Snoozed, Resolved) in
                Command Center Recommendation
    surface.py  the department screens' finding boxes, fed from the matching area
    daily.py    the daily email digest and the optional Daily Brief by Claude
"""
