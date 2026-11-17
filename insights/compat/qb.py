"""frappe.qb -- which is PyPika, the open-source query builder Frappe wraps.

The figure engine and the fact screens build their SQL with it. Here it is PyPika
itself, with Frappe's two conveniences put back: DocType("X") is the table "tabX", and
a query has .run(as_dict=...) that executes it on the platform's database. The SQL is
built in the dialect of that database (MySQLQuery on MariaDB, SQLLiteQuery locally).
"""

from __future__ import annotations

from pypika import Field, Order, Table  # noqa: F401
from pypika import functions as fn
from pypika.queries import QueryBuilder

from insights.compat.state import _dict
from insights.compat.utils import to_plain


def _dialect():
    from django.db import connection
    if connection.vendor == "mysql":
        from pypika import MySQLQuery
        return MySQLQuery
    from pypika.dialects import SQLLiteQuery
    return SQLLiteQuery


def _run(self, as_dict=False, pluck=None, debug=False, **kw):
    from django.db import connection
    sql = self.get_sql()
    with connection.cursor() as cur:
        cur.execute(sql)
        if cur.description is None:
            from insights.compat.db import db, is_write
            if is_write(sql):
                db._wrote()
            return []
        cols = [c[0] for c in cur.description]
        rows = cur.fetchall()
    if pluck:
        i = cols.index(pluck) if pluck in cols else 0
        return [to_plain(r[i]) for r in rows]
    if as_dict:
        return [_dict({c: to_plain(v) for c, v in zip(cols, r)}) for r in rows]
    return [tuple(to_plain(v) for v in r) for r in rows]


QueryBuilder.run = _run


def DocType(name: str) -> Table:  # noqa: N802 (Frappe's name)
    return Table(f"tab{name}")


def _table(t):
    return DocType(t) if isinstance(t, str) else t


def from_(t):
    return _dialect().from_(_table(t))


def into(t):
    return _dialect().into(_table(t))


def update(t):
    return _dialect().update(_table(t))


functions = fn
terms = None
Field = Field


class _Functions:
    """frappe.query_builder.functions"""

    Count = fn.Count
    Sum = fn.Sum
    Max = fn.Max
    Min = fn.Min
    Avg = fn.Avg
    Coalesce = fn.Coalesce
    IfNull = fn.Coalesce
    Abs = fn.Abs
