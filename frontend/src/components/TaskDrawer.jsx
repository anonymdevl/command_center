import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api/client.js";
import { DrawerHead } from "./Drawer.jsx";
import { Loading, Failed, Empty } from "./States.jsx";
import { count, shortDate } from "../format.js";
import { Sec } from "./Understanding.jsx";

/**
 * One task handed out, in the platform's own drawer (Outstanding Tasks and Today open it
 * from a row or a card; legacy/work.js). Read from api/work.task as the manager: what it
 * is, who has it and who gave it, its dates, priority and status, the ERPNext document it
 * is about, and ERPNext's comments on the To-Do and the document when the manager may
 * read them there. The buttons are the same as the row's -- Edit, Reassign, Escalate,
 * Cancel Assignment, and Accept It / Send It Back once it is marked done -- and each goes
 * through the action dialog, which asks first. ERPNext is a secondary link only.
 */
export default function TaskDrawer({ task, scope }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api.task({ business_code: scope, todo: task.name })
      .then((d) => setData(d || null))
      .catch((e) => setError(e))
      .finally(() => setLoading(false));
  }, [scope, task.name]);

  useEffect(() => {
    load();
    window.addEventListener("cc-work-changed", load);
    return () => window.removeEventListener("cc-work-changed", load);
  }, [load]);

  const t = { ...task, ...(data || {}) };
  const isOpen = t.status === "Open";
  const toCheck = t.status === "Closed" && !t.accepted;
  const fire = (detail) => window.dispatchEvent(new CustomEvent("cc-action", { detail }));
  const req = (kind) => ({ kind, title: t.title, detail: t.detail, todo: t.name, assignee: t.to,
                           assignee_name: t.to_name, date: t.date, priority: t.priority,
                           doctype: t.reference?.doctype, docname: t.reference?.name });
  const doc = t.document || (t.reference ? { ...t.reference } : null);

  return (
    <>
      <DrawerHead title={t.title || t.name} />
      <section className="dw-hero">
        <div className="dw-hero-fig">
          <div className="dw-lab">Given to</div>
          <div className="dw-big task-who" title={t.to_name || t.to}>{t.to_name || t.to || "—"}</div>
          <div className="dw-chips">
            <span className={`dw-chip${isOpen ? "" : t.status === "Cancelled" ? " dw-c-crit" : " dw-c-ok"}`}>
              {t.accepted ? "Accepted" : toCheck ? "Marked Done" : t.status || "—"}
            </span>
            <span className={`dw-chip${t.priority === "High" ? " dw-c-high" : ""}`}>{t.priority || "Medium"} Priority</span>
            {t.late_days > 0 ? (
              <span className="dw-chip dw-c-crit">Late by {count(t.late_days)} day{t.late_days === 1 ? "" : "s"}</span>
            ) : null}
            {t.sent_back > 0 ? (
              <span className="dw-chip dw-c-high">Sent back {count(t.sent_back)} time{t.sent_back === 1 ? "" : "s"}</span>
            ) : null}
          </div>
        </div>
        {t.detail ? <p className="dw-say task-detail">{t.detail}</p> : null}
      </section>

      <div className="dw-pane">
        {isOpen || toCheck ? (
          <Sec title="Actions">
            <div className="task-acts">
              {isOpen ? (
                <>
                  <button type="button" className="dw-btn" onClick={() => fire(req("edit_task"))}>Edit Date And Priority</button>
                  <button type="button" className="dw-btn" onClick={() => fire(req("reassign"))}>Reassign</button>
                  <button type="button" className="dw-btn" onClick={() => fire(req("escalate"))}>Escalate</button>
                  <button type="button" className="dw-btn failed" onClick={() => fire(req("cancel_task"))}>Cancel Assignment</button>
                </>
              ) : (
                <>
                  <button type="button" className="dw-btn" onClick={() => fire({ kind: "review", verdict: "accept", todo: t.name, title: t.title })}>Accept It</button>
                  <button type="button" className="dw-btn failed" onClick={() => fire({ kind: "review", verdict: "return", todo: t.name, title: t.title })}>Send It Back</button>
                </>
              )}
            </div>
          </Sec>
        ) : null}

        <Sec title="Details">
          <dl className="task-facts">
            <dt>Given To</dt><dd>{t.to_name || t.to || "—"}</dd>
            <dt>Given By</dt><dd>{t.assigned_by_name || (loading ? "…" : "You")}</dd>
            <dt>Given On</dt><dd>{t.created ? shortDate(t.created) : "—"}</dd>
            <dt>Due</dt><dd>{t.date ? shortDate(t.date) : "No date set"}</dd>
            <dt>Priority</dt><dd>{t.priority || "Medium"}</dd>
            <dt>Status</dt><dd>{t.accepted ? "Accepted" : toCheck ? `Marked done${t.closed_on ? ` on ${shortDate(t.closed_on)}` : ""}` : t.status || "—"}</dd>
            {t.modified ? (<><dt>Last Changed</dt><dd>{shortDate(t.modified.slice(0, 10))}</dd></>) : null}
          </dl>
        </Sec>

        <Sec title="Document">
          {doc ? (
            <p className="dw-p"><b>{doc.doctype}</b> {doc.name}</p>
          ) : (
            <p className="dw-p">It concerns no single ERPNext document: it is a To-Do of its own.</p>
          )}
          <div className="task-links">
            {doc?.url ? <a className="dlink" href={doc.url} target="_blank" rel="noreferrer">Open {doc.doctype} in ERPNext ↗</a> : null}
            {t.url ? <a className="dlink" href={t.url} target="_blank" rel="noreferrer">Open the To-Do in ERPNext ↗</a> : null}
          </div>
        </Sec>

        <Sec title="Comments">
          {loading && !data ? <Loading what="Reading the comments in ERPNext" /> : null}
          {error ? <Failed error={error} onRetry={load} what="this task" /> : null}
          {data && data.comments === null ? (
            <p className="dw-note">ERPNext does not let your account read the comments on this task, so they
              are not shown here. They are on the To-Do in ERPNext.</p>
          ) : null}
          {data && Array.isArray(data.comments) && !data.comments.length ? <Empty>No comments yet.</Empty> : null}
          {data && Array.isArray(data.comments) && data.comments.length ? (
            <ol className="task-comments">
              {data.comments.map((c, i) => (
                <li key={`${c.when}-${i}`}>
                  <div className="task-c-meta">
                    <b>{c.by || "Someone"}</b>
                    <span>{c.when ? shortDate(c.when.slice(0, 10)) : ""}{c.when?.length > 10 ? ` ${c.when.slice(11, 16)}` : ""}</span>
                    {c.on && c.on !== "ToDo" ? <span>on the {c.on}</span> : null}
                  </div>
                  <p>{c.text}</p>
                </li>
              ))}
            </ol>
          ) : null}
        </Sec>
      </div>
    </>
  );
}
TaskDrawer.ownsHeader = true;
