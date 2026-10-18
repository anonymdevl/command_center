import React, { useEffect, useState } from "react";
import { api } from "../api/client.js";

/**
 * Set when a report is written and who receives it (api/reports.save_schedule).
 *
 * The people offered are the enabled accounts on this site (api/actions.people), which
 * is also all the server will accept: a scheduled report never leaves the company. The
 * report is written with the permissions of whoever saves the schedule, and the dialog
 * says so. "Send a copy now" writes and sends it once, to check the list.
 */
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const HOURS = Array.from({ length: 24 }, (_, h) => h);

export default function ScheduleDialog({ scope }) {
  const [req, setReq] = useState(null);
  const [people, setPeople] = useState([]);
  const [form, setForm] = useState(null);
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(null);

  useEffect(() => {
    const open = (e) => {
      const r = e.detail || {};
      const c = r.current;
      setReq(r);
      setForm({
        frequency: c?.frequency || "Weekly", weekday: c?.weekday || "Monday",
        day_of_month: c?.day_of_month || 1, hour: c?.hour ?? 7,
        recipients: c?.recipients || [], enabled: c ? !!c.enabled : true,
      });
      setState("idle");
      setError("");
      setSaved(null);
      api.people(scope).then((p) => setPeople(p || [])).catch(() => setPeople([]));
    };
    window.addEventListener("cc-schedule", open);
    return () => window.removeEventListener("cc-schedule", open);
  }, [scope]);

  useEffect(() => {
    if (!req) return;
    const esc = (e) => e.key === "Escape" && setReq(null);
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [req]);

  if (!req || !form) return null;
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const toggle = (user) => setForm((f) => ({
    ...f, recipients: f.recipients.includes(user) ? f.recipients.filter((u) => u !== user) : [...f.recipients, user] }));

  const save = async (e) => {
    e.preventDefault();
    if (form.enabled && !form.recipients.length) {
      setError("Choose at least one person to receive it.");
      return;
    }
    setState("saving");
    setError("");
    try {
      const res = await api.saveSchedule({
        code: req.code, business_code: scope, frequency: form.frequency, weekday: form.weekday,
        day_of_month: Number(form.day_of_month), hour: Number(form.hour),
        recipients: JSON.stringify(form.recipients), enabled: form.enabled ? 1 : 0,
      });
      setSaved(res);
      setState("done");
      window.dispatchEvent(new CustomEvent("cc-schedules-changed"));
    } catch (err) {
      setError(err?.message || "The schedule was not saved.");
      setState("failed");
    }
  };

  const sendNow = async () => {
    setState("sending");
    try {
      await api.sendNow({ code: req.code, business_code: scope });
      setState("sent");
    } catch (err) {
      setError(err?.message || "It could not be sent.");
      setState("done");
    }
  };

  return (
    <div className="dlg-scrim" onMouseDown={(e) => e.target === e.currentTarget && setReq(null)}>
      <div className="dlg" role="dialog" aria-modal="true" aria-labelledby="sch-t">
        {state === "done" || state === "sending" || state === "sent" ? (
          <>
            <div className="dlg-ok" aria-hidden="true">✓</div>
            <h3 id="sch-t">{saved?.says === "switched off" ? "Schedule switched off" : "Scheduled"}</h3>
            <p className="dlg-sub">
              {req.title}: {saved?.says}{saved?.next_run ? `. Next on ${saved.next_run}.` : "."}
            </p>
            {state === "sent" ? (
              <p className="dlg-hint">A copy is being written and will be emailed to the list in a few minutes.</p>
            ) : null}
            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              {saved?.says !== "switched off" && state !== "sent" ? (
                <button type="button" className="ap-act" onClick={sendNow} disabled={state === "sending"}>
                  {state === "sending" ? "Starting…" : "Send a copy now"}
                </button>
              ) : null}
              <button type="button" className="ap-act pri" onClick={() => setReq(null)}>Done</button>
            </div>
          </>
        ) : (
          <form onSubmit={save}>
            <h3 id="sch-t">Schedule: {req.title}</h3>
            <p className="dlg-sub">Written from the records at the time, and emailed as a PDF.</p>

            <label htmlFor="sch-f">How often</label>
            <select id="sch-f" value={form.frequency} onChange={set("frequency")}>
              <option>Daily</option><option>Weekly</option><option>Monthly</option>
            </select>
            {form.frequency === "Weekly" ? (
              <>
                <label htmlFor="sch-d">On</label>
                <select id="sch-d" value={form.weekday} onChange={set("weekday")}>
                  {DAYS.map((d) => <option key={d}>{d}</option>)}
                </select>
              </>
            ) : null}
            {form.frequency === "Monthly" ? (
              <>
                <label htmlFor="sch-m">Day of the month (1–28)</label>
                <input id="sch-m" type="number" min="1" max="28" value={form.day_of_month} onChange={set("day_of_month")} />
              </>
            ) : null}
            <label htmlFor="sch-h">At</label>
            <select id="sch-h" value={form.hour} onChange={set("hour")}>
              {HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
            </select>

            <label>Who receives it</label>
            <div className="sch-people">
              {people.length ? people.map((p) => (
                <label key={p.user} className="sch-person">
                  <input type="checkbox" checked={form.recipients.includes(p.user)} onChange={() => toggle(p.user)} />
                  <span>{p.name}</span>
                </label>
              )) : <span className="dlg-hint">Loading people…</span>}
            </div>

            <label className="sch-person sch-enabled">
              <input type="checkbox" checked={form.enabled} onChange={set("enabled")} />
              <span>Send it on this schedule</span>
            </label>

            {error ? <div className="dlg-err" role="alert">{error}</div> : null}
            <div className="dlg-acts">
              <button type="button" className="ap-act" onClick={() => setReq(null)}>Cancel</button>
              <button type="submit" className="ap-act pri" disabled={state === "saving"}>
                {state === "saving" ? "Saving…" : "Save"}
              </button>
            </div>
            <p className="dlg-foot">Only people with an account here can receive it. It is written with your permissions.</p>
          </form>
        )}
      </div>
    </div>
  );
}
