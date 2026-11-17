"""frappe.db -- the platform's tables, through Django's ORM.

The calls and their answers are Frappe's: filters as {field: value | [op, value]} or
[[field, op, value]], rows as attribute dicts, "!=" and "not in" keeping rows where the
field is empty (Frappe wraps those in ifnull, and the business logic relies on it).
Numbers come back as float, dates as datetime.date, on SQLite and MariaDB alike.

Transactions are Frappe's too: work is committed at the end of a request, rolled back
when it fails, and frappe.db.commit() / rollback() mean what they say -- the ingest
rolls back a half-loaded fact, the analyst's write guard rolls back anything a question
wrote. `transaction_writes` counts writes since the last commit, for that guard.
"""

from __future__ import annotations

import re
import threading

from insights.compat.state import DoesNotExistError, _dict
from insights.compat.utils import to_plain

OPERATORS = {">", ">=", "<", "<=", "=", "!=", "in", "not in", "like", "not like",
             "between", "is", "descendants of", "ancestors of", "timespan"}


# --- which table --------------------------------------------------------------
def model_for(doctype: str):
    from insights.core.models import DOCTYPE_MODELS, DefaultValue, ErrorLog
    m = DOCTYPE_MODELS.get(doctype)
    if m is not None:
        return m
    if doctype == "DefaultValue":
        return DefaultValue
    if doctype == "Error Log":
        return ErrorLog
    raise DoesNotExistError(f"DocType {doctype} not found")


def _field_names(model) -> set:
    return {f.name for f in model._meta.concrete_fields} | {f.attname for f in model._meta.concrete_fields}


# --- whose businesses ----------------------------------------------------------------
# Every read of a table that has a business_code column, by anyone who may not see every
# business, is limited here to the businesses they may see -- through get_all, get_value,
# exists, count, get_doc and frappe.qb.from_, so no endpoint, screen, report, question or
# export can forget to (17 Nov 2026: any manager could read and act on any business).
# The rule is insights/core/plans.py visible_codes. Rows of no business ("" or "__all__":
# a conversation over all businesses, a report run over all of them) are the person's own
# only. The platform itself (Administrator: the scheduler and the command line; Guest:
# the single sign-on), an administrator, and anyone who may see every business are not
# limited at all, so for them nothing about a query changes.
SCOPE_FIELD = "business_code"
NO_BUSINESS = ("", "__all__")


def business_scope():
    """The business codes the acting person may read (a frozenset), or None for all.
    Worked out once per person per unit of work (a request, a job, a thread)."""
    from insights.compat.state import local
    if getattr(local, "cc_scope_off", False):
        return None
    user = getattr(local, "user", None) or "Guest"
    memo = getattr(local, "cc_scope", None)
    if memo is not None and memo[0] == user:
        return memo[1]
    scope = _work_out_scope(user)
    local.cc_scope = (user, scope)
    return scope


def _work_out_scope(user):
    from insights.core.models import ConnectedBusiness
    from insights.core.plans import visible_codes
    codes = visible_codes(user)
    if codes is None:
        return None
    every = set(ConnectedBusiness.objects.values_list("business_code", flat=True))
    return None if every <= codes else frozenset(codes)


def forget_scope():
    """The person's customers or businesses changed in this unit of work: work it out
    again at the next read."""
    from insights.compat.state import local
    local.__dict__.pop("cc_scope", None)


class unscoped:
    """`with unscoped():` -- reads as the platform, for an administrative step that
    has already checked who may take it (registering a business a delegate adds)."""

    def __enter__(self):
        from insights.compat.state import local
        self.was = getattr(local, "cc_scope_off", False)
        local.cc_scope_off = True
        return self

    def __exit__(self, *exc):
        from insights.compat.state import local
        local.cc_scope_off = self.was
        return False


def _scope_q(model):
    """The Q that limits a model's rows to the acting person's businesses, or None."""
    if SCOPE_FIELD not in _field_names(model):
        return None
    scope = business_scope()
    if scope is None:
        return None
    from django.db.models import Q

    from insights.compat.state import local
    q = Q(**{f"{SCOPE_FIELD}__in": sorted(scope)})
    if "owner" in _field_names(model):
        q |= (Q(**{f"{SCOPE_FIELD}__isnull": True}) | Q(**{f"{SCOPE_FIELD}__in": list(NO_BUSINESS)})) \
            & Q(owner=getattr(local, "user", None) or "Guest")
    return q


def scoped(model, qs):
    q = _scope_q(model)
    return qs if q is None else qs.filter(q)


# --- filters -> Django Q ------------------------------------------------------
def to_q(model, filters):
    from django.db.models import Q
    q = Q()
    if not filters:
        return q
    if isinstance(filters, str):
        return Q(pk=filters)
    if isinstance(filters, dict):
        items = list(filters.items())
    else:
        items = []
        for f in filters:
            if isinstance(f, dict):
                items += list(f.items())
            elif len(f) == 4:
                items.append((f[1], [f[2], f[3]]))
            elif len(f) == 3:
                items.append((f[0], [f[1], f[2]]))
            elif len(f) == 2:
                items.append((f[0], f[1]))
    names = _field_names(model)
    for field, value in items:
        if field not in names:
            raise ValueError(f"{model._meta.db_table}: no column {field!r}")
        q &= _condition(field, value, _is_text(model, field))
    return q


def _is_text(model, field) -> bool:
    try:
        f = model._meta.get_field(field)
    except Exception:
        return True
    return f.get_internal_type() in ("CharField", "TextField")


def _condition(field, value, text=True):
    """One filter. On a text column an empty string and NULL are both "not set", as
    Frappe treats them; on a date or number column only NULL is (an empty string is
    not a value there, and Frappe's ifnull made it mean NULL)."""
    from django.db.models import Q
    if isinstance(value, (list, tuple)) and len(value) == 2 and str(value[0]).lower() in OPERATORS:
        op, val = str(value[0]).lower(), value[1]
    elif isinstance(value, (list, tuple)):
        op, val = "in", list(value)
    else:
        op, val = "=", value

    if val == "" and not text:
        val = None
    if op == "=":
        return Q(**{f"{field}__isnull": True}) if val is None else Q(**{field: val})
    if op == "!=":
        return Q(**{f"{field}__isnull": False}) if val is None else ~Q(**{field: val})
    if op in ("in", "not in"):
        vals = val if isinstance(val, (list, tuple, set)) else [
            v.strip() for v in str(val).split(",")]
        cond = Q(**{f"{field}__in": list(vals)})
        return cond if op == "in" else ~cond
    if op in (">", ">=", "<", "<="):
        return Q(**{f"{field}__{ {'>': 'gt', '>=': 'gte', '<': 'lt', '<=': 'lte'}[op]}": val})
    if op in ("like", "not like"):
        cond = Q(**{f"{field}__iregex": _like_regex(str(val))})
        return cond if op == "like" else ~cond
    if op == "between":
        low, high = val
        return Q(**{f"{field}__gte": low, f"{field}__lte": high})
    if op == "is":
        is_set = str(val).lower() == "set"
        if not text:
            return Q(**{f"{field}__isnull": not is_set})
        return (~Q(**{f"{field}__isnull": True}) & ~Q(**{field: ""})) if is_set else (
            Q(**{f"{field}__isnull": True}) | Q(**{field: ""}))
    raise ValueError(f"filter operator {op!r} is not supported")


def _like_regex(pattern: str) -> str:
    out = []
    for ch in pattern:
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
    return "^" + "".join(out) + "$"


def _order(model, order_by):
    if not order_by:
        return ["-modified"] if "modified" in _field_names(model) else []
    out = []
    for part in str(order_by).split(","):
        bits = part.strip().replace("`", "").split()
        if not bits:
            continue
        col = bits[0].split(".")[-1]
        desc = len(bits) > 1 and bits[1].lower() == "desc"
        out.append(("-" if desc else "") + col)
    return out


def _fields(fields):
    """Plain column names, and "col as alias"."""
    cols, alias = [], {}
    for f in fields or ["name"]:
        f = str(f).strip().replace("`", "")
        m = re.match(r"^([\w.]+)\s+as\s+(\w+)$", f, re.I)
        if m:
            col = m.group(1).split(".")[-1]
            cols.append(col)
            alias[col] = m.group(2)
        else:
            cols.append(f.split(".")[-1])
    return cols, alias


# --- the database object --------------------------------------------------------
class _Writes(threading.local):
    n = 0


_writes = _Writes()


# Statements that never change a row. A statement that returns no result set used to
# count as a write whatever it was, so the analyst's `SET SESSION max_statement_time`
# (ask/agent.py, MariaDB only) counted as two writes and every question with a lookup
# was rolled back as "a database write happened while answering" (17 Nov 2026).
_READS = ("SELECT", "SHOW", "SET", "DESCRIBE", "DESC", "EXPLAIN")


def is_write(sql: str) -> bool:
    """Whether a statement may change data: anything but a read or a session setting.
    A WITH ... starts a read or a write; it is a write unless what follows is a SELECT."""
    text = re.sub(r"^(\s|/\*.*?\*/|--[^\n]*\n)+", "", str(sql or ""), flags=re.S)
    word = (re.match(r"\(*\s*(\w+)", text) or [None, ""])[1].upper()
    if word == "WITH":
        return not re.search(r"\)\s*SELECT\b", text, re.I) or bool(
            re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE)\b", text, re.I))
    return word not in _READS


class Database:
    @property
    def db_type(self) -> str:
        """Frappe's name for the database: "mariadb" on MySQL/MariaDB, else Django's
        vendor ("sqlite", "postgresql"). The analyst's statement limit is MariaDB's own
        (max_statement_time) and is set only where it exists."""
        from django.db import connection
        return "mariadb" if connection.vendor == "mysql" else connection.vendor

    @property
    def transaction_writes(self) -> int:
        return _writes.n

    def _wrote(self, n=1):
        _writes.n += n

    # transactions
    def begin(self):
        from django.db import transaction
        if transaction.get_autocommit():
            transaction.set_autocommit(False)
        _writes.n = 0

    def commit(self):
        from django.db import transaction
        if not transaction.get_autocommit():
            transaction.commit()
        _writes.n = 0

    def rollback(self, save_point=None):
        from django.db import transaction
        if not transaction.get_autocommit():
            transaction.rollback()
        _writes.n = 0

    def end(self, ok: bool):
        from django.db import transaction
        try:
            if ok:
                self.commit()
            else:
                self.rollback()
        finally:
            if not transaction.get_autocommit():
                transaction.set_autocommit(True)

    # reads
    def get_all(self, doctype, filters=None, fields=None, order_by=None, limit=None,
                limit_page_length=None, limit_start=None, start=None, page_length=None,
                pluck=None, group_by=None, or_filters=None, distinct=False, as_list=False,
                ignore_permissions=None, **kw):
        if doctype in ("User", "Has Role"):
            from insights.compat import users
            return users.get_all(doctype, filters=filters, fields=fields, order_by=order_by,
                                 limit=limit or limit_page_length or page_length, pluck=pluck)
        model = model_for(doctype)
        qs = scoped(model, model.objects.filter(to_q(model, filters)))
        if or_filters:
            from django.db.models import Q
            oq = Q()
            items = or_filters.items() if isinstance(or_filters, dict) else [
                (f[0], [f[1], f[2]]) if len(f) == 3 else (f[1], [f[2], f[3]]) for f in or_filters]
            for field, value in items:
                oq |= _condition(field, value, _is_text(model, field))
            qs = qs.filter(oq)
        cols, alias = _fields([pluck] if pluck else fields)
        if cols == ["*"]:
            cols = [f.attname for f in model._meta.concrete_fields]
        order = _order(model, order_by)
        if group_by:
            qs = qs.values(*cols).distinct()
            order = [o for o in order if o.lstrip("-") in cols]
        else:
            qs = qs.values(*cols)
            if distinct:
                qs = qs.distinct()
        if order:
            qs = qs.order_by(*order)
        offset = int(limit_start or start or 0)
        n = limit or limit_page_length or page_length
        if n:
            qs = qs[offset:offset + int(n)]
        elif offset:
            qs = qs[offset:]
        rows = [_dict({alias.get(k, k): to_plain(v) for k, v in r.items()}) for r in qs]
        if pluck:
            return [r[pluck] for r in rows]
        if as_list:
            return [tuple(r.values()) for r in rows]
        return rows

    get_list = get_all

    def get_value(self, doctype, filters=None, fieldname="name", as_dict=False,
                  order_by=None, cache=False, **kw):
        if doctype in ("System Settings", "Print Settings", "Global Defaults"):
            return self.get_single_value(doctype, fieldname)
        many = isinstance(fieldname, (list, tuple))
        fields = list(fieldname) if many else [fieldname]
        if isinstance(filters, str):
            filters = {"name": filters}
        rows = self.get_all(doctype, filters=filters, fields=fields, order_by=order_by, limit=1)
        if not rows:
            return None
        r = rows[0]
        if as_dict:
            return r
        return tuple(r.get(f) for f in fields) if many else r.get(fields[0])

    def exists(self, doctype, filters=None, cache=False):
        if filters is None and isinstance(doctype, dict):
            filters, doctype = {k: v for k, v in doctype.items() if k != "doctype"}, doctype["doctype"]
        if doctype in ("User", "Has Role"):
            from insights.compat import users
            return users.exists(doctype, filters)
        if doctype == "Role":
            from insights.compat import users
            return users.role_exists(filters)
        try:
            model = model_for(doctype)
        except DoesNotExistError:
            return None
        return scoped(model, model.objects.filter(to_q(model, filters))).values_list(
            "pk", flat=True).first()

    def count(self, doctype, filters=None, **kw):
        if doctype in ("User", "Has Role"):
            from insights.compat import users
            return len(users.get_all(doctype, filters=filters, fields=["name"]))
        model = model_for(doctype)
        return scoped(model, model.objects.filter(to_q(model, filters))).count()

    def get_single_value(self, doctype, fieldname, cache=False):
        from django.conf import settings
        if doctype == "System Settings" and fieldname == "time_zone":
            return settings.TIME_ZONE
        if doctype == "Print Settings" and fieldname == "pdf_generator":
            return "wkhtmltopdf"
        from insights.compat import defaults
        return defaults.get_global_default(f"{doctype}:{fieldname}")

    # writes
    def set_value(self, doctype, name, fieldname, value=None, update_modified=True, **kw):
        from insights.compat import documents
        if doctype == "User":
            from insights.compat import users
            users.set_value(name, fieldname, value)
            return
        model = model_for(doctype)
        values = dict(fieldname) if isinstance(fieldname, dict) else {fieldname: value}
        meta_pw = documents.password_fields(doctype)
        for f in [k for k in values if k in meta_pw]:
            documents.set_password(doctype, name, f, values.pop(f))
        values = {k: v for k, v in values.items() if k in _field_names(model)}
        if update_modified and "modified" in _field_names(model):
            from insights.compat.utils import now_datetime
            from insights.compat.state import local
            values.setdefault("modified", now_datetime())
            values.setdefault("modified_by", local.user)
        qs = scoped(model, model.objects.filter(
            to_q(model, name if isinstance(name, (dict, list)) else {"name": name})))
        n = qs.update(**values) if values else 0
        self._wrote(max(1, n))

    def set_single_value(self, doctype, fieldname, value):
        from insights.compat import defaults
        defaults.set_global_default(f"{doctype}:{fieldname}", value)

    def delete(self, doctype, filters=None):
        model = model_for(doctype)
        n, _ = scoped(model, model.objects.filter(to_q(model, filters))).delete()
        self._wrote(max(1, n))

    def bulk_insert(self, doctype, fields, values, ignore_duplicates=False, chunk_size=1000):
        model = model_for(doctype)
        names = _field_names(model)
        keep = [i for i, f in enumerate(fields) if f in names]
        from insights.compat.utils import now_datetime
        from insights.compat.state import local
        stamp = now_datetime()
        objs = []
        for row in values:
            kw = {fields[i]: row[i] for i in keep}
            kw.setdefault("creation", stamp)
            kw.setdefault("modified", stamp)
            kw.setdefault("owner", local.user)
            kw.setdefault("modified_by", local.user)
            objs.append(model(**kw))
        model.objects.bulk_create(objs, batch_size=chunk_size, ignore_conflicts=ignore_duplicates)
        self._wrote(len(objs))

    def add_index(self, doctype, fields, index_name=None):
        """Indexes are declared on the models (insights/tools/gen_models.py)."""
        return None

    def escape(self, value, percent=True) -> str:
        s = str(value).replace("\\", "\\\\").replace("'", "''")
        if percent:
            s = s.replace("%", "%%")
        return f"'{s}'"

    def sql(self, query, values=None, as_dict=False, as_list=False, **kw):
        from django.db import connection
        text = str(query).strip()
        if text.upper().startswith("SET SESSION") and connection.vendor != "mysql":
            return []
        text = text.replace("`", '"') if connection.vendor == "sqlite" else text
        with connection.cursor() as cur:
            cur.execute(text, values or None)
            if cur.description is None:
                if is_write(text):
                    self._wrote()
                return []
            cols = [c[0] for c in cur.description]
            rows = cur.fetchall()
        if as_dict:
            return [_dict({c: to_plain(v) for c, v in zip(cols, r)}) for r in rows]
        return [tuple(to_plain(v) for v in r) for r in rows]

    def get_table_columns(self, doctype):
        return sorted(_field_names(model_for(doctype)))


db = Database()
