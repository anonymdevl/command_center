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
  const [req, setReq] = useState(null); // {kind, title, detail, owner}
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
      const k = KINDS[r.kind] || KINDS.assign;
      setReq({ ...r, kind: KINDS[r.kind] ? r.kind : "assign" });
      setWho("");
      setDue(addDays(k.days));
      setNote([r.title, r.detail].filter(Boolean).join("\n\n"));
      setState("idle");
      setError("");
      setDone(null);
    };
    window.addEventListener("cc-action", open);
    return () => window.removeEventListener("cc-action", open);
  }, []);

  useEffect(() => {
    if (!req) return;
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
    const esc = (e) => e.key === "Escape" && setReq(null);
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [req, scope]);

  if (!req) return null;
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
      });
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
