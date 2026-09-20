# -*- coding: utf-8 -*-
# Record-level detail shown INSIDE the drawer, so a manager can decide without opening ERPNext.
def tbl(cols, rows, foot=""):
    th="".join(f'<th{" style=text-align:right" if c[1] else ""}>{c[0]}</th>' for c in cols)
    tr=""
    for r in rows:
        tds=""
        for (c,num),v in zip(cols,r):
            st=' class="num"' if num else ''
            tds+=f'<td{st}>{v}</td>'
        tr+=f"<tr>{tds}</tr>"
    f=f'<div class="drfoot">{foot}</div>' if foot else ''
    return f'<table class="dt drt"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>{f}'

C=lambda v:f"{v:,.0f}"
RED=lambda v:f'<span style="color:var(--crit)">{v}</span>'

RECORDS={
"ar": tbl([("Customer",0),("Owed GHS",1),("Age",0),("Ever paid this balance?",0)],
 [("HAIRASH ENTERPRISE",C(737544),RED("over 3 months"),RED("No payment matched")),
  ("UBUNTU ORTHOPAEDIC & SPINE HOSPITAL",C(636675),RED("over 3 months"),RED("No payment matched")),
  ("A.S Hospitex",C(541841),RED("over 3 months"),"—"),
  ("ILEE MEDICAL CENTRE",C(503850),RED("over 3 months"),"—"),
  ("VINEYARD HOSPITAL",C(493011),RED("over 3 months"),"—"),
  ("DIVINE FAVOUR HOSPITAL- AGONA",C(481175),RED("over 3 months"),"—"),
  ("KING JO MEDICAL SUPPLIES",C(380280),RED("over 3 months"),"—"),
  ("BANY HOSPITAL",C(338003),RED("over 3 months"),"—"),
  ("ST JOHN OF GOD-SEFWI-ASAFO",C(270868),RED("over 3 months"),"—"),
  ("ELANTH MEDICAL CENTER",C(209235),RED("over 3 months"),"—"),
  ("<b>Ten largest</b>","<b>"+C(4592482)+"</b>","","")],
 "806 invoices are unpaid in total. Three of these customers are also waiting on us — HAIRASH, UBUNTU and EJURA."),

"worst": tbl([("Product",0),("Where",0),("Reserved",1),("Available",1),("Short by",1)],
 [("Syringe &amp; needle 5ml","Central Warehouse",C(40080),C(139),RED(C(39941))),
  ("Syringe &amp; needle 10ml","Central Warehouse",C(16021),"0",RED(C(16021))),
  ("Infusion sets","Central Warehouse",C(8000),"0",RED(C(8000))),
  ("Infusion sets","Central Store",C(7750),"0",RED(C(7750)))],
 "The 5ml syringe is the single worst line on the site: 288 promised for every one held. "
 "These four lines alone account for 71,712 units promised against 139 actually present, "
 "and all four are everyday consumables sold constantly."),

"reserved": tbl([("Cover",0),("Lines",1),("Share",1),("What it means",0)],
 [("Nothing held at all",C(491),"64%",RED("any order will fail at picking")),
  ("Some stock held",C(280),"36%","may or may not cover the promise"),
  ("<b>Lines with a reservation</b>","<b>"+C(771)+"</b>","<b>100%</b>",""),
  ("Lines with no reservation",C(1604),"","nothing promised against them")],
 "Of 2,375 product-location records, 771 carry a promise to a customer. "
 "<b>Only 36% of those have any stock behind them.</b>"),

"nodate": tbl([("Order",0),("Supplier",0),("Ordered",0),("Value GHS",1),("Promised for",0)],
 [("PUR-ORD-2025-00054","SICHUAN M.K.R CO LTD","24 Feb 2025",C(571519),RED("never set")),
  ("PUR-ORD-2025-00052","SICHUAN M.K.R CO LTD","24 Feb 2025",C(405558),RED("never set")),
  ("<b>Two orders</b>","","","<b>"+C(977077)+"</b>","")],
 "Both placed on the same day with the same supplier, and neither carries a delivery date. "
 "Nothing can be chased because nothing is late &mdash; there is no date to be late against."),

"disabled": tbl([("Person",0),("Roles still attached",1),("Last seen",0),("Sign-in",0)],
 [("Bright Yomaah","5","Jun 2025","blocked"),
  ("Thomas Billa","2","Mar 2024","blocked"),
  ("Sandra Oppong","1","Jul 2025","blocked"),
  ("Sandra Oppong","2","Feb 2024","blocked")],
 "Every departed person checked has had sign-in blocked, which is the right outcome. "
 "Two points worth noting: the roles stay attached, so re-enabling an account restores everything it had; "
 "and Sandra Oppong appears twice under two addresses, which is a records problem rather than a security one."),

"conflicts": tbl([("Person",0),("Roles held",0),("What one account can do",0)],
 [("Simon Nketiah Sieh","HR, Accounts, Stock, Purchase &mdash; 5 roles",
   RED("raise a purchase and approve its payment; adjust stock and post it; change pay and approve it")),
  ("Samuel Opoku","Accounts, Sales, HR, Projects &mdash; 5 roles",
   RED("change pay and approve paying it")),
  ("John-Paul Iwuoha","Purchase, Accounts, Projects &mdash; 4 roles",
   RED("raise a purchase and approve its payment"))],
 "Three of thirteen active accounts. This is not evidence of wrongdoing &mdash; it is evidence that "
 "the four-stage approval cannot work as designed, because one person can satisfy several stages."),

"roles5": tbl([("Person",0),("Roles",1),("Which ones",0)],
 [("Simon Nketiah Sieh","5","HR Manager, Accounts Manager, Accounts User, Stock Manager, Purchase Manager"),
  ("Samuel Opoku","5","Accounts Manager, Accounts User, Sales Manager, HR Manager, Projects Manager"),
  ("Samuel Adjei","5","Accounts User, HR Manager, Stock Manager, Purchase Manager, Projects Manager")],
 "Three people hold five manager roles each, spanning finance, stock, buying and HR."),

"raise": tbl([("Finding",0),("Risk",0),("Area",0)],
 [("Customers promised stock the company does not hold, across 491 products","Critical","Stock"),
  ("Nearly a third of stock value sits outside every warehouse","Critical","Stock"),
  ("The entire GHS 9.18M owed is over three months old","Critical","Money owed"),
  ("Almost all buying depends on two overseas suppliers","High","Buying"),
  ("Three installations are nineteen months past their promised date","High","Engineering"),
  ("GHS 903,632 of purchase orders were never submitted for approval","High","Buying")],
 "Every one was found in the records on the first morning, before anything was built."),

"over": tbl([("Product",0),("Where",0),("Reserved",1),("Available",1),("Short by",1)],
 [("Syringe &amp; needle 5ml","Central Warehouse",C(40080),C(139),RED(C(39941))),
  ("Syringe &amp; needle 10ml","Central Warehouse",C(16021),"0",RED(C(16021))),
  ("Infusion sets","Central Warehouse",C(8000),"0",RED(C(8000))),
  ("Infusion sets","Central Store",C(7750),"0",RED(C(7750))),
  ("Examination gloves","Central Store",C(2844),C(93),RED(C(2751))),
  ("Examination gloves","Central Warehouse",C(2752),C(610),RED(C(2142))),
  ("Blood transfusion sets","Central Warehouse",C(2140),"0",RED(C(2140))),
  ("Crepe bandage brown 6in","Central Warehouse",C(1665),"0",RED(C(1665))),
  ("Test kit — typhoid","Central Warehouse",C(1628),"0",RED(C(1628))),
  ("Microscope slides frosted","Central Warehouse",C(1532),"0",RED(C(1532)))],
 "Ten worst of 491. All are everyday consumables a medical supplier sells constantly."),

"recon": tbl([("Item",0),("Qty",1),("Value GHS",1)],
 [("Haematology analyser — Mindray BC 10 (new)","2",C(81500)),
  ("Haematology analyser — Mindray BC-5000 (new)","1",C(78800)),
  ("Anaesthesia machine — Eternity AM 832","1",C(55000)),
  ("Ultrasound scanner — Mindray DP 20","2",C(54120)),
  ("Hospital beds, 2-crank complete","15",C(47719)),
  ("Test kits — H. pylori antibody","442",C(41662)),
  ("Armpit crutches — small","320",C(36878)),
  ("Armpit crutches — large","313",C(36537)),
  ("Armpit crutches — medium","313",C(36529)),
  ("Orthopaedic theatre bed","1",C(34740)),
  ("<b>Top 100 of 207 lines</b>","","<b>"+C(1175920)+"</b>")],
 "Roughly a third of everything the company owns. None of it can be sold or reserved from here."),

"late": tbl([("Job",0),("Customer",0),("Promised",0),("Late by",0),("Assigned to",0)],
 [("C-arm installation","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025",RED("19 months"),RED("Nobody")),
  ("Theatre setup","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025",RED("19 months"),RED("Nobody")),
  ("X-ray installation","UBUNTU ORTHOPAEDIC &amp; SPINE HOSPITAL","28 Feb 2025",RED("19 months"),RED("Nobody")),
  ("Lab setup","SAMKWARTH PHARMACEUTICAL LTD","20 May 2024",RED("28 months"),RED("Nobody")),
  ("AGAHF maintenance and servicing","—","30 May 2024",RED("28 months"),RED("Nobody"))],
 "Three engineers employed in total. Eleven of fourteen open jobs have nobody's name against them."),

"supp": tbl([("Supplier",0),("Spend GHS",1),("Orders",1),("Share",1),("Ships from",0)],
 [("SICHUAN M.K.R CO LTD",C(4831075),"8","57%","China"),
  ("CYNSEL INNOVATION",C(3157343),"5","37%","Overseas"),
  ("QINGDAO HIGHTOP BIOTECH",C(439380),"1","5%","China"),
  ("<b>Fourteen largest orders</b>","<b>"+C(8427798)+"</b>","14","100%","")],
 "No alternative supplier is recorded for any of the same products."),

"lead": tbl([("Supplier",0),("Ordered",0),("Promised for",0),("Wait",1),("Value GHS",1)],
 [("CYNSEL INNOVATION","28 Dec 2024","30 Jun 2025",RED("184 days"),C(1283800)),
  ("CYNSEL INNOVATION","4 Mar 2024","4 Jul 2024",RED("122 days"),C(866803)),
  ("QINGDAO HIGHTOP BIOTECH","10 Apr 2024","3 Jul 2024","84 days",C(439380)),
  ("SICHUAN M.K.R CO LTD","25 Apr 2025","25 Jun 2025","61 days",C(409655)),
  ("SICHUAN M.K.R CO LTD","20 Nov 2024","17 Jan 2025","58 days",C(1084007)),
  ("SICHUAN M.K.R CO LTD","3 Mar 2025","25 Apr 2025","53 days",C(530833)),
  ("SICHUAN M.K.R CO LTD","10 Mar 2025","14 Apr 2025","35 days",C(278603)),
  ("SICHUAN M.K.R CO LTD","9 Nov 2024","9 Dec 2024","30 days",C(743578)),
  ("SICHUAN M.K.R CO LTD","18 Feb 2025","19 Mar 2025","29 days",C(807322)),
  ("CYNSEL INNOVATION","4 Nov 2024","2 Dec 2024","28 days",C(337600)),
  ("CYNSEL INNOVATION","10 Aug 2024","4 Sep 2024","25 days",C(277400)),
  ("CYNSEL INNOVATION","2 Sep 2024","6 Sep 2024","4 days",C(391740)),
  ("SICHUAN M.K.R CO LTD","24 Feb 2025","—",RED("never set"),C(571519)),
  ("SICHUAN M.K.R CO LTD","24 Feb 2025","—",RED("never set"),C(405558))],
 "Two orders worth GHS 977,077 between them were placed with no promised delivery date at all."),

"openorders": tbl([("Order",0),("Customer",0),("Value GHS",1),("Placed",0),("Despatched",0)],
 [("SAL-ORD-2025-00910","EJURA MUNICIPAL HOSPITAL",C(65100),"19 Aug 2025",RED("None of it")),
  ("SAL-ORD-2025-00909","ROSSY'S SUPPLY",C(16700),"19 Aug 2025",RED("None of it")),
  ("SAL-ORD-2025-00906-1","ST MARYS HOSPITAL (DROBO)",C(1750),"18 Aug 2025",RED("None of it")),
  ("SAL-ORD-2025-00907","LILIAN ACHIAA",C(1400),"18 Aug 2025",RED("None of it"))],
 "The Ejura order alone is 77% of the value waiting to go out."),

"cases": tbl([("Complaint",0),("Customer",0),("Waiting",0),("Urgency",0),("Owes us?",0)],
 [("No response to installation follow-up","HAIRASH ENTERPRISE",RED("25 days"),"Urgent",RED("GHS 737,544")),
  ("Autoclave not reaching temperature","VINEYARD HOSPITAL",RED("22 days"),"Urgent",RED("GHS 493,011")),
  ("Refund requested — invoiced twice","KING JO MEDICAL SUPPLIES","18 days","Normal",RED("GHS 380,280")),
  ("X-ray generator tripping — unit down","ST JOHN OF GOD-SEFWI-ASAFO","7 days","Urgent","GHS 270,868"),
  ("Monitor probe failed under warranty","ILEE MEDICAL CENTRE","4 days","Normal","GHS 503,850"),
  ("Oxygen concentrator alarming","EJURA MUNICIPAL HOSPITAL","2 days","Urgent","—")],
 "All eleven cases were seeded by us for this demonstration. The customers and their balances are real."),

"depts": tbl([("As recorded in ERPNext",0),("People",1),("Looks like",0)],
 [("Customer Service Dept.","10",""),
  ("Procurement &amp; Inventory - GMSL","5",RED("same as the row below")),
  ("Procurement Inventory &amp; Logistics Department - GMSL","1",RED("same as the row above")),
  ("Directorate","4",""),
  ("Finance Dept","3",""),
  ("Sales and Marketing Dept","3",""),
  ("Medical Engineering Dept","2",RED("overlaps with Project &amp; Engineering")),
  ("PROJECT AND ENGINEERING DEPT - GMSL","1",RED("overlaps with Medical Engineering")),
  ("Operations Dept","1",RED("same as the row below")),
  ("Operations  - GMSL","1",RED("same as the row above")),
  ("HUMAN RESOURCES AND ADMINISTRATION - GMSL","2",""),
  ("Executive Office - GMSL","2","")],
 "At least three pairs are the same department entered twice. Headcount by department cannot be trusted until they are merged."),

"turnover": tbl([("Person",0),("Role",0),("Where",0),("Joined",0),("Left",0),("Stayed",1)],
 [("Bright Yomaah","Finance officer","Sunyani","Feb 2024","Jun 2025","17 mths"),
  ("ERIC HOLBROOK-SMITH","HR/Admin Manager","Sunyani","Aug 2024","May 2025","10 mths"),
  ("Emmanuel Boateng","Customer Service Assistant","Sunyani","Nov 2023","Jun 2024","7 mths"),
  ("Ernest Opoku","Logistics &amp; Delivery Assistant","Sunyani","Nov 2023","Jun 2024","7 mths"),
  ("Thomas Kwame Billa","Operations Manager","Sunyani","Nov 2023","Jun 2024",RED("6 mths")),
  ("Andy Anim Antwi","Personal Assistant","Sunyani","Dec 2024","Mar 2025",RED("4 mths")),
  ("Rachel Amoakoaa","Customer Service Associate III","Kumasi","Oct 2024","Jan 2025",RED("4 mths")),
  ("Linus Tangpuor","Warehouse Coordinator","Kumasi","Oct 2024","Dec 2024",RED("3 mths")),
  ("<b>Eight departures</b>","","","","","<b>7 mths average</b>")],
 "Four of the eight lasted under six months, and three of those under five. "
 "Three more are marked inactive rather than departed: Seth Tweneboah, Abiba Bukari and Isaac Anderson &mdash; "
 "the last having joined in October 2020."),

"head": tbl([("Branch",0),("Active",1),("Inactive",1),("Left",1),("Total",1)],
 [("Sunyani (head office)","14","1","6","21"),
  ("Kumasi","6","2","1","9"),
  ("Accra","2","0","1","3"),
  ("Central Administration","2","0","0","2"),
  ("<b>All</b>","<b>24</b>","<b>3</b>","<b>8</b>","<b>35</b>")],
 "Names, salaries and conduct records are hidden from every role except HR."),

"capacity": tbl([("Role",0),("Branch",0),("Standing",0)],
 [("Snr. Biomedical Sales Engineer","Accra","Active"),
  ("Zonal Coordinator — Medical Engineering","Kumasi","Active"),
  ("Bio-Medical Sales Engineer","Central Administration","Active")],
 "Three engineers for the whole country, all titled sales engineers, against fourteen open jobs."),

"drafts": tbl([("What",0),("Count",1),("Effect",0)],
 [("Invoices written but never issued","88","Excluded from every total on this platform"),
  ("Invoices confirmed and unpaid","806","Counted as money owed"),
  ("Invoices confirmed in total","7,765","")],
 "An unissued invoice is not money owed, so counting it would overstate the position. But nobody is chasing them either."),

"funnel": tbl([("Stage",0),("Count",1),("Value GHS",1),("What it means",0)],
 [("Enquiries","17","—","Barely used"),
  ("Opportunities","0","—",RED("Not used at all")),
  ("Quotations","122",C(1668921),"Only 122 against 1,436 orders"),
  ("Orders","1,436",C(20363857),"Most never begin as a quotation")],
 "Conversion cannot be measured properly until quotations are used consistently — and it is the one number that predicts next quarter."),

"stockval": tbl([("Where",0),("Value GHS",1),("Can it be sold from here?",0)],
 [("Stock adjustment account",C(1175920),RED("No — not a warehouse")),
  ("Kumasi Warehouse &amp; Store","~900,000","Yes"),
  ("Central Warehouse &amp; Store","~860,000","Yes"),
  ("Accra Warehouse","~380,000","Yes"),
  ("Other locations","~454,050","Yes"),
  ("<b>All locations</b>","<b>"+C(3769970)+"</b>","")],
 "704 product-location records carry a value and reconcile exactly to GHS 3,769,970."),

"workingcap": tbl([("What",0),("GHS",1),("Why it is stuck",0)],
 [("Owed to us, over three months",C(4592482),"No collection activity recorded"),
  ("Stock outside any warehouse",C(1175920),"Cannot be sold or reserved"),
  ("Orders taken, not despatched",C(84950),"Customer waiting, we cannot invoice"),
  ("<b>Total not presently usable</b>","<b>"+C(5853352)+"</b>","")],
 "Against a total stock holding of GHS 3,769,970. These three figures normally live in three different reports."),
}
