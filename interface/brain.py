# -*- coding: utf-8 -*-
# Agentic answers: steps shown, then answer, then sources.
BRAIN=[
 {"k":["ubuntu","paid"],"q":"Has UBUNTU ever paid us?",
  "steps":["Looking up UBUNTU ORTHOPAEDIC & SPINE HOSPITAL",
           "Reading their invoices — 27 found",
           "Matching payments received against them",
           "Checking whether we owe them anything"],
  "ans":"<p><b>No payment has ever been matched against their current balance of GHS 636,675</b>, and all of it is more than three months old.</p>"
        "<p>There is something else you should know before calling them. <b>We owe them three installations</b> — a C-arm, a theatre setup and an X-ray — all promised for 28 February 2025 and none started. That is nineteen months.</p>"
        "<p>They are also our second-largest debtor. Asking for payment without addressing the installations is unlikely to go well.</p>",
  "sug":"<b>Suggested:</b> send an engineer and open the payment conversation in the same call.",
  "src":[("Customer account","UBUNTU ORTHOPAEDIC & SPINE HOSPITAL","ar"),
         ("Projects","PROJ-0028 / 0029 / 0030","ubuntu")]},
 {"k":["owe","waiting"],"q":"Which customers owe us money and are also waiting on us?",
  "steps":["Listing customers with money outstanding — 806 unpaid invoices",
           "Listing open complaints and unfinished installations",
           "Matching the two lists"],
  "ans":"<p><b>Three customers appear on both lists.</b></p>"
        "<p><b>HAIRASH ENTERPRISE</b> — owes GHS 737,544, our largest debt, and has been waiting 25 days for an answer about an installation.</p>"
        "<p><b>UBUNTU ORTHOPAEDIC & SPINE HOSPITAL</b> — owes GHS 636,675 and is waiting on three installations promised nineteen months ago.</p>"
        "<p><b>EJURA MUNICIPAL HOSPITAL</b> — has an oxygen concentrator alarming, and a GHS 65,100 order we have taken but not despatched.</p>"
        "<p>Between them that is GHS 1.44M owed by customers who are themselves waiting on us.</p>",
  "sug":"<b>Suggested:</b> fix the service issue first on each, then ask for the money. In that order.",
  "src":[("Customer accounts","10 largest balances","ar"),("Projects","PROJ-0028 / 0029 / 0030","ubuntu"),
         ("Sales order","SAL-ORD-2025-00910","ejura")]},
 {"k":["sichuan","supply","supplier","stops"],"q":"What happens if SICHUAN stops supplying?",
  "steps":["Totalling purchases by supplier",
           "Working out each supplier's share",
           "Checking lead times on their orders",
           "Looking for a second source on the same products"],
  "ans":"<p><b>SICHUAN M.K.R accounts for about 57% of the largest purchase orders</b> — roughly GHS 4.83M across eight of the fourteen biggest.</p>"
        "<p>Add CYNSEL INNOVATION and two suppliers cover about <b>95%</b> of that spend. Both ship from abroad, with lead times between 29 and 184 days.</p>"
        "<p><b>No alternative supplier is recorded for the same products.</b> If either stopped, or a shipment were held at the port, there is nothing in the system that says who else could supply.</p>",
  "sug":"<b>Suggested:</b> identify a second source for the top ten items by value. That is a week of work against a risk that could stop the business.",
  "src":[("Purchase orders","14 largest","spend"),("Suppliers","3 named","supp")]},
 {"k":["ejura","delivery note"],"q":"Find the delivery note for the Ejura order",
  "steps":["Finding the Ejura order","Following it through to despatch","Looking for the delivery note"],
  "ans":"<p><b>There is no delivery note.</b> That absence is the answer.</p>"
        "<p>EJURA MUNICIPAL HOSPITAL placed a GHS 65,100 order on 19 August 2025. Nothing has left the warehouse, so no delivery note exists — and because we cannot invoice what we have not despatched, no invoice exists either.</p>"
        "<p>It is the largest order we have taken and not fulfilled. The three others still open come to GHS 19,850 between them.</p>",
  "sug":"<b>Suggested:</b> confirm a despatch date today. They also have an oxygen concentrator alarming.",
  "src":[("Sales order","SAL-ORD-2025-00910","ejura")]},
 {"k":["ejura","open","why"],"q":"Why is the Ejura order still open?",
  "steps":["Finding the order","Checking what has been despatched","Checking what has been invoiced","Looking for what is blocking it"],
  "ans":"<p>EJURA MUNICIPAL HOSPITAL placed a <b>GHS 65,100</b> order on 19 August 2025. Nothing has left the warehouse and nothing has been invoiced since.</p>"
        "<p>Nothing has been despatched, and until it is we cannot invoice. That is why it shows as waiting on both despatch and payment — it is one hold-up, not two.</p>"
        "<p>It is the largest order we have taken and not fulfilled.</p>",
  "sug":"<b>Suggested:</b> confirm a despatch date today.",
  "src":[("Sales order","SAL-ORD-2025-00910","ejura")]},
 {"k":["owes","most","paid"],"q":"Who owes us the most and have they ever paid?",
  "steps":["Ranking balances outstanding","Checking payment history against each","Checking how old each balance is"],
  "ans":"<p><b>HAIRASH ENTERPRISE owes the most: GHS 737,544</b>, all of it more than three months late.</p>"
        "<p>No payment has ever been matched against any of their invoices. That is different from paying late — there is no record of them paying us at all against this balance.</p>"
        "<p>Behind them: UBUNTU at GHS 636,675 and A.S Hospitex at GHS 541,841. UBUNTU is also waiting on three installations we have not delivered.</p>",
  "sug":"<b>Suggested:</b> HAIRASH is also waiting 25 days on a complaint. Deal with that before asking for the money.",
  "src":[("Customer accounts","10 largest","ar"),("Projects","PROJ-0028 / 0029 / 0030","ubuntu")]},
 {"k":["say","ubuntu"],"q":"What should I say to UBUNTU?",
  "steps":["Reading everything on UBUNTU","Checking what we owe them","Checking what they owe us","Checking who is assigned"],
  "ans":"<p>Lead with the installations, not the money.</p>"
        "<p>We promised them a C-arm, a theatre setup and an X-ray by 28 February 2025. <b>None has been started and nobody is assigned to any of them.</b> That is nineteen months.</p>"
        "<p>They owe GHS 636,675, all beyond three months. From their side, they have paid for equipment and are still waiting for it to be usable.</p>"
        "<p>A realistic call: give them a dated plan for the three installations, then agree a payment schedule that starts when the first one is done.</p>",
  "sug":"<b>I can draft that letter for your approval</b> — it will not be sent without you reading it.",
  "src":[("Projects","PROJ-0028 / 0029 / 0030","ubuntu"),("Customer account","UBUNTU","ar")]},
 {"k":["credit note","refund","issue"],"q":"Issue a credit note for A1 Medicalsupplies",
  "gate":True,
  "steps":["Finding the invoice","Checking the customer's balance","Checking what I am permitted to do"],
  "ans":"", "sug":"", "src":[]},
]
