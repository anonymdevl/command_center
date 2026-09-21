# -*- coding: utf-8 -*-
AR=[("HAIRASH ENTERPRISE",737544),("UBUNTU ORTHOPAEDIC & SPINE HOSPITAL",636675),
 ("A.S Hospitex",541841),("ILEE MEDICAL CENTRE",503850),("VINEYARD HOSPITAL",493011),
 ("DIVINE FAVOUR HOSPITAL- AGONA",481175),("KING JO MEDICAL SUPPLIES",380280),
 ("BANY HOSPITAL",338003),("ST JOHN OF GOD-SEFWI-ASAFO",270868),("ELANTH MEDICAL CENTER",209235)]
def g(n): return f"{n:,.0f}"

def _money(val, cur):
    """GHS leads; magnitude and any qualifier follow. Non-money units keep the old suffix form."""
    c=(cur or "").strip()
    if "GHS" in c:
        rest=c.replace("GHS","",1).strip()          # "M" / "k" / "owed" / "at risk" / ""
        mag=rest if rest in ("M","k","m","K") else ""
        note=""  if mag else rest
        return (f'<span class="cx">GHS</span>{val}'
                + (f'<span class="mag">{mag}</span>' if mag else "")
                + (f' <span class="cur">{note}</span>' if note else ""))
    return f'{val}' + (f' <span class="cur">{c}</span>' if c else "")

def kpi(lab, val, cur="", delta="", dcls="flat", flag="", dr="", explain=""):
    """The card. One definition, used by every view.

    This function was defined twice -- here and again in views_a.py, which
    silently shadowed it. The two differed by one class: the later one added
    `clickable`, the earlier one did not. So views generated before the
    redefinition had working click targets and no chevron, and views generated
    after had both. Same component, two appearances, which is the one thing a
    component is supposed to make impossible.

    It must match components/Figure.jsx. Both render the same contract:
    centred figure, label and flag on one line, hairline above the footnote
    whether or not there is a footnote, and the chevron exactly when the card
    opens something.
    """
    f = f'<span class="flag">{flag}</span>' if flag else ''
    d = f'<div class="delta {dcls}">{delta or "&nbsp;"}</div>'
    # Every figure opens to its records -- that is the product's promise, and a
    # card that cannot be opened would be an exception to it. Cards not yet
    # wired fall back to a shared panel that says so plainly, rather than
    # showing no affordance and looking like a different component.
    action = dr or f"explain('{explain or 'unwired'}')"
    od = f' onclick="{action}"'
    cl = "kpi clickable"
    return (f'<div class="{cl}"{od}><div class="khead"><div class="lab">{lab}</div>{f}</div>'
            f'<div class="val">{_money(val, cur)}</div>{d}</div>')


def _afig(fig,cur):
    c=(cur or "").strip()
    if c.startswith("GHS"):
        rest=c[3:].strip()
        return (f'<span class="cx">GHS</span>{fig}'
                + (f' <small>{rest}</small>' if rest else ""))
    return f'{fig}' + (f' <small>{c}</small>' if c else "")

def alert(sev, what, why, sowhat, fig, cur, srcdt, srcnm, owner, elapsed, drawer='', acts=None):
    acts = acts or ['Assign', 'Request evidence', 'Approve', 'Defer', 'Escalate', 'Dismiss']
    first = acts[0]
    restacts = acts[1:]
    menu = ''.join((f'''<button class="{('dgr' if a in ('Dismiss', 'Reject') else '')}">{a}</button>''' for a in restacts))
    ab = f'<button class="btn pri">{first}</button>' + (f'<span class="more"><button class="morebtn" onclick="moreMenu(this)">&#8943;</button><div class="moremenu">{menu}</div></span>' if restacts else '')
        # Callers pass either a drawer key or a ready-made handler. Both styles
    # exist because this function was defined twice and each copy taught its
    # own callers a different convention; accepting both is how they unify
    # without rewriting every call site.
    od = ''
    if drawer:
        handler = drawer if '(' in drawer else f'openDrawer({SQ}{drawer}{SQ})'
        od = f' onclick="{handler}"'
    return f'<div class="alert {sev}"><div class="arow"><div>\n<div class="awhat">{what}</div><div class="awhy">{why}</div><div class="asw">→ {sowhat}</div></div>\n<div class="afig">{_afig(fig, cur)}</div></div>\n<div class="ameta"><span class="chip src"{od}>{srcdt} · <b>{srcnm}</b></span>\n<span class="chip">Owner <b>{owner}</b></span><span class="chip">Elapsed <b>{elapsed}</b></span></div>\n<div class="acts">{ab}</div></div>'

# ---------------- V: COMMAND ----------------
V_COMMAND=f'''<div class="topbar"><div><h3 class="hello" id="greet">Good morning</h3></div></div>
<div class="banner"><b>This is a prototype.</b> Every customer, order, invoice and figure is real data
from Gigmann's own ERPNext. Buttons that would change a record are inert — nothing here writes back.</div>
<div class="kpis" style="grid-template-columns:repeat(6,1fr)">
{kpi("Money in, month","0","GHS","no invoices raised in the period","flat","stale")}
{kpi("Owed to us","9.18","M GHS","74% more than 3 months late","dn","review","go('sales')")}
{kpi("Days to get paid","—","","no payments received in period","flat")}
{kpi("Waiting","4","","GHS 84,950 not yet delivered","flat","","go('sales')")}
{kpi("Past due","4","","GHS 13,537","dn","","go('sales')")}
{kpi("Stock we hold","3.77","M GHS","a third is not in any warehouse","dn","review","go('health')")}
</div>
<div class="sect"><span>Needs your attention — 4 items</span><span class="lnk" onclick="go('brief')">Open the full brief →</span></div>
{alert("crit","GHS 6.78M of the 9.18M owed is more than three months late",
 "Nothing is sitting in the earlier stages, so this did not creep up on us. Ten customers hold all of it.",
 "Pick the three largest and agree payment dates this week.",
 "6,777,143","GHS","Customer accounts","647 invoices","Finance","over 3 months","openDrawer('ar')")}
{alert("crit","We have promised customers stock we do not physically have, across 491 products",
 "Any of those orders can fail the moment the warehouse goes to pick it. Sales has committed goods the shelves do not hold.",
 "Freeze new commitments on the worst lines until a count is done.",
 "491","products","Stock position","Central, Kumasi, Accra","Stock Manager","ongoing","openDrawer('stock')")}
{alert("high","UBUNTU has been waiting for three installations since February last year",
 "The same hospital owes us GHS 636,675, all more than three months late. We have not delivered and they have not paid — it is one story, not two.",
 "Send an engineer and open the payment conversation in the same call.",
 "636,675","GHS at risk","Projects","PROJ-0028 / 0029 / 0030","Engineering","19 months","openDrawer('ubuntu')")}
{alert("med","EJURA MUNICIPAL HOSPITAL is still waiting for a GHS 65,100 order",
 "Placed on 19 August. Nothing has left the warehouse and nothing has been invoiced, so we are neither serving them nor being paid.",
 "Confirm a despatch date today.",
 "65,100","GHS","Sales order","SAL-ORD-2025-00910","Sales","31 days","openDrawer('ejura')")}'''

# ---------------- V: BRIEF ----------------
V_BRIEF=f'''<div class="topbar"><div><h3>Executive Summary</h3>
<div class="when">Generated 07:00 · reconciled to the customer account balances</div></div></div>
<div class="banner">Each item states six things: <b>what happened · why it matters · the figure ·
where it came from · who owns it · how long it has been true</b>. Every one links to the record behind it.</div>
{alert("crit","GHS 6.78M of the 9.18M owed is more than three months late",
 "Nothing is sitting in the earlier stages. Ten customers hold all of it.",
 "Pick the three largest and agree payment dates this week.",
 "6,777,143","GHS","Customer accounts","647 invoices","Finance","over 3 months","openDrawer('ar')")}
{alert("crit","We have committed 40,080 syringes to customers. There are 139 in the building.",
 "The same is true of 10ml syringes (16,021 promised, none held) and infusion sets (8,000 promised, none held). These are everyday items we sell constantly.",
 "Stop quoting these lines until the count is confirmed.",
 "39,941","short","Stock position","Central Warehouse","Stock Manager","ongoing","openDrawer('stock')")}
{alert("high","Almost a third of everything we own is not in any warehouse",
 "GHS 1.18M of real equipment is recorded in a stock-adjustment account: two brand-new haematology analysers, an anaesthesia machine, 15 hospital beds, 946 crutches. Nobody can sell it from there.",
 "Decide where this equipment physically is, then move it onto a sellable location.",
 "1,175,920","GHS","Stock adjustment account","207 product lines","Stock Manager","unknown","openDrawer('recon')")}
{alert("med","88 invoices were written but never issued",
 "That revenue is in nobody's figures. It is correctly left out of the totals — but no one is chasing it either.",
 "Ask Sales to issue or void them by Friday.",
 "88","invoices","Unissued invoices","Sales","Sales","varies")}
{alert("info","Six customer complaints are past the time we promised to resolve them",
 "Two concern equipment that is down — an X-ray generator and an autoclave — so those customers cannot treat patients with them.",
 "Escalate the two equipment-down cases to Engineering today.",
 "6","cases","Customer cases","Seeded for demonstration","Customer Service","up to 3 weeks","go('cx')")}'''
