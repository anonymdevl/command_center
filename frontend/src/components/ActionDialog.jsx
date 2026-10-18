import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

/**
 * Put a piece of work on someone's desk, from wherever it was noticed.
 *
 * Opened by the buttons on alerts, findings and the like (legacy/actions.js) through a
 * "cc-action" event. Whatever the kind -- assign, request evidence, escalate, raise a
 * finding -- the result is the same honest thing: a real ERPNext To-Do on that
 * person's list, created as the manager who sent it (api/actions.create_task), so
 * ERPNext's own notifications, permissions and history apply. The assistant never
 * reaches this; only a person pressing the button does.
 *
 * Two decisions come through here too (legacy/work.js): "decide" applies a workflow
 * action to a document waiting on this person, and "review" accepts or sends back work
 * they handed out. Both ask first and say exactly what will change; after either, a
 * "cc-work-changed" event tells the screen to read the queue again.
 */

const KINDS = {
  assign: { title: "Assign this", verb: "Assign", lead: "", days: 3 },
  evidence: { title: "Request evidence", verb: "Send the request", lead: "Please send the evidence for: ", days: 3 },
  escalate: { title: "Escalate", verb: "Escalate", lead: "Escalated: ", days: 1, priority: "High" },
  finding: { title: "Raise as a finding", verb: "Raise it", lead: "Finding: ", days: 7 },
};

let peopleCache = {};

function addDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  // The local date, not toISOString's UTC one, which is a day out east or west of GMT.
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export default function ActionDialog({ scope }) {
  const [req, setReq] = useState(null); // {kind, title, detail, owner} or a decision
  const [people, setPeople] = useState([]);
  const [who, setWho] = useState("");
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");
  const [state, setState] = useState("idle"); // idle | saving | done | failed
  const [done, setDone] = useState(null);
  const [error, setError] = useState("");
  const first = useRef(null);

  useEffect(() => {
    const open = (e) => {
      const r = e.detail || {};
      const decision = r.kind === "decide" || r.kind === "review" || r.kind === "alert";
      const k = KINDS[r.kind] || KINDS.assign;
      setReq({ ...r, kind: decision || KINDS[r.kind] ? r.kind : "assign" });
      setWho("");
      setDue(addDays(k.days));
      setNote(decision ? "" : [r.title, r.detail].filter(Boolean).join("\n\n"));
      setState("idle");
      setError("");
      setDone(null);
    };
    window.addEventListener("cc-action", open);
    return () => window.removeEventListener("cc-action", open);
  }, []);

  useEffect(() => {
    if (!req) return;
    const esc = (e) => e.key === "Escape" && setReq(null);
    document.addEventListener("keydown", esc);
    if (!KINDS[req.kind]) return () => document.removeEventListener("keydown", esc);
    const key = scope || "__all__";
    if (peopleCache[key]) {
      setPeople(peopleCache[key]);
    } else {
      api.people(scope).then((p) => {
        peopleCache[key] = p || [];
        setPeople(peopleCache[key]);
      }).catch(() => setPeople([]));
    }
    setTimeout(() => first.current?.focus(), 30);
    return () => document.removeEventListener("keydown", esc);
  }, [req, scope]);

  if (!req) return null;
  if (!KINDS[req.kind]) {
    return <Decision req={req} scope={scope} note={note} setNote={setNote} close={() => setReq(null)} />;
  }
  const k = KINDS[req.kind];
  const person = people.find((p) => p.user === who);

  const submit = async (e) => {
    e.preventDefault();
    if (!who) {
      setError("Choose who this goes to.");
      return;
    }
    setState("saving");
    setError("");
    try {
      const subject = `${k.lead}${req.title || "From the Command Center"}`.slice(0, 140);
      const res = await api.createTask({
        business_code: scope,
        subject,
        description: note,
        allocated_to: who,
        due_date: due || null,
        priority: k.priority || null,
        reference_type: req.alert ? "Command Center Alert" : null,
        reference_name: req.alert || null,
      });
      // An alert that has become someone's To-Do says so, and says which.
      if (req.alert && res?.name) {
        await api.alertAct({ name: req.alert, action: "actioned", todo: res.name }).catch(() => {});
        window.dispatchEvent(new CustomEvent("cc-alerts-changed"));
      }
      window.dispatchEvent(new CustomEvent("cc-work-changed"));
      setDone({ name: res?.name, person: person?.name || who, due });
      setState("done");
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setState("failed");
    }
  };

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && setReq(null)}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {state === "done" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="dlg-t">On {done.person}’s list</h3>
            <p className="dlg-sub">
              It is a To-Do in ERPNext{done.due ? `, due ${new Date(`${done.due}T00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}` : ""},
              from you. ERPNext tells them in the usual way.
            </p>
            <div className="dlg-acts">
              {done.name ? (
                <a className="ap-act" href={`/app/todo/${encodeURIComponent(done.name)}`} target="_blank" rel="noreferrer">
                  Open the To-Do ↗
                </a>
              ) : null}
              <button type="button" className="ap-act pri" onClick={() => setReq(null)}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{k.title}</h3>
            <p className="dlg-sub">{req.title}</p>
            {req.owner ? <p className="dlg-hint">Suggested owner: {req.owner}</p> : null}

            <label htmlFor="dlg-who">To</label>
            <select id="dlg-who" ref={first} value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">{people.length ? "Choose a person" : "Loading people…"}</option>
              {people.map((p) => (
                <option key={p.user} value={p.user}>{p.name}</option>
              ))}
            </select>

            <label htmlFor="dlg-due">By</label>
            <input id="dlg-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />

            <label htmlFor="dlg-note">Note</label>
            <textarea id="dlg-note" rows={5} value={note} onChange={(e) => setNote(e.target.value)} />

            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={() => setReq(null)}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"}>
                {state === "saving" ? "Sending…" : k.verb}
              </button>
            </div>
            <p className="dlg-foot">Creates a To-Do in ERPNext, as you. Nothing else changes.</p>
          </form>
        )}
      </div>
    </div>
  );
}


/** Approve / reject a document, or accept / send back handed-out work. Asks first. */
const ALERT_VERBS = {
  defer: ["Defer", "It leaves your list until the date you choose, then comes back if the condition is still there.", "Deferred"],
  dismiss: ["Dismiss", "It stays dismissed while the condition lasts. Your reason is kept so the rule can be tuned.", "Dismissed"],
  false_positive: ["Not a real problem", "Marked as a false alarm. Your reason is kept so the rule that raised it can be corrected.", "Marked not a real problem"],
};

function inDays(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function Decision({ req, scope, note, setNote, close }) {
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [until, setUntil] = useState(inDays(7));
  const alertVerb = req.kind === "alert" ? ALERT_VERBS[req.verb] : null;
  const back = req.kind === "review" && req.verdict === "return";
  const needsNote = back || !!alertVerb;
  const verb = alertVerb ? alertVerb[0] : req.kind === "decide" ? req.action : back ? "Send it back" : "Accept it";
  const what = alertVerb ? alertVerb[1] : req.kind === "decide"
    ? `This applies “${req.action}” to ${req.doctype} ${req.name} in ERPNext, as you. ERPNext checks that your role may take this step, and records it in the document's history.`
    : back
      ? "The To-Do reopens on their list, with your note as a comment they will see."
      : "The To-Do is tagged Accepted and leaves your list of evidence to check.";

  const submit = async (e) => {
    e.preventDefault();
    if (needsNote && !note.trim()) {
      setError(back ? "Say what is still needed, so they know what to do."
        : "Give a reason. It is kept so the rule can be tuned.");
      return;
    }
    setState("saving");
    setError("");
    try {
      const res = alertVerb
        ? await api.alertAct({ name: req.alert, action: req.verb, reason: note,
                               until: req.verb === "defer" ? until : null })
        : req.kind === "decide"
          ? await api.decide({ business_code: scope, doctype: req.doctype, name: req.name, action: req.action })
          : await api.review({ todo: req.todo, verdict: req.verdict, note });
      setResult(res || {});
      setState("done");
      window.dispatchEvent(new CustomEvent(alertVerb ? "cc-alerts-changed" : "cc-work-changed"));
    } catch (err) {
      setError(err?.message || "ERPNext did not accept it.");
      setState("failed");
    }
  };

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && close()}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="dlg-t">
        {state === "done" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="dlg-t">{alertVerb ? alertVerb[2] : req.kind === "decide" ? `${req.action}: done` : back ? "Sent back" : "Accepted"}</h3>
            <p className="dlg-sub">
              {alertVerb
                ? req.verb === "defer"
                  ? `It comes back on ${new Date(`${until}T00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" })} if the condition is still there.`
                  : "It is off the list, with your reason on record."
                : req.kind === "decide"
                ? `${req.doctype} ${req.name} is now at “${result.workflow_state || "its next step"}”.`
                : back ? "It is open on their list again, with your note." : "It is off your list."}
            </p>
            <div className="dlg-acts">
              <button type="button" className="ap-act pri" onClick={close}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={submit}>
            <h3 id="dlg-t">{verb}</h3>
            <p className="dlg-sub">{req.title}</p>
            <p className="dlg-hint">{what}</p>
            {alertVerb && req.verb === "defer" ? (
              <>
                <label htmlFor="dlg-until">Bring it back on</label>
                <input id="dlg-until" type="date" value={until} min={inDays(1)} onChange={(e) => setUntil(e.target.value)} />
              </>
            ) : null}
            {req.kind === "review" || alertVerb ? (
              <>
                <label htmlFor="dlg-note">{alertVerb ? "Reason" : back ? "What is still needed" : "Note (optional)"}</label>
                <textarea id="dlg-note" rows={4} value={note} onChange={(e) => setNote(e.target.value)} autoFocus />
              </>
            ) : null}
            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={close}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"} autoFocus={req.kind === "decide"}>
                {state === "saving" ? "Working…" : verb}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
