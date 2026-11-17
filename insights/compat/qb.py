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


def _model_of(table_name: str):
    from insights.core.models import DOCTYPE_MODELS
    by_table = getattr(_model_of, "cache", None)
    if by_table is None:
        by_table = {m._meta.db_table: m for m in DOCTYPE_MODELS.values()}
        _model_of.cache = by_table
    return by_table.get(table_name)


def from_(t):
    """SELECT ... FROM a table, limited to the acting person's businesses when the table
    has a business_code column and they may not see every one (db.business_scope)."""
    t = _table(t)
    q = _dialect().from_(t)
    model = _model_of(getattr(t, "_table_name", "")) if isinstance(t, Table) else None
    if model is None:
        return q
    from insights.compat.db import NO_BUSINESS, SCOPE_FIELD, _field_names, business_scope
    if SCOPE_FIELD not in _field_names(model):
        return q
    scope = business_scope()
    if scope is None:
        return q
    from insights.compat.state import local
    col = t.field(SCOPE_FIELD)
    cond = col.isin(sorted(scope) or ["\x00"])
    if "owner" in _field_names(model):
        cond = cond | ((col.isnull() | col.isin(list(NO_BUSINESS)))
                       & (t.field("owner") == (getattr(local, "user", None) or "Guest")))
    return q.where(cond)


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
