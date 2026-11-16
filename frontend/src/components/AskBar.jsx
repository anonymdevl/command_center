import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { historyFor, recentQuestions, remember, replaceAnswer } from "../askHistory.js";
import { fetchStarters, followDeep, runAsk, runningFor, stopDeepLook, stopRunning } from "../askFlow.js";
import { groupSteps, hasHidden } from "../legacy/steps.js";
import { renderAnswer } from "../legacy/answer.js";
import { renderMarkdown } from "../legacy/markdown.js";
import Icon from "./Icon.jsx";
import ExportButton from "./ExportButton.jsx";
import { tablesFrom } from "../exportTables.js";
import Records from "./Records.jsx";
import { boot } from "../api/boot.js";

// The model answering on this site (www/command_center.py _ai), named while it works.

/**
 * The question bar, answering in place.
 *
 * A question asked here is answered in a panel under the bar, so a manager never
 * leaves the screen they are reading. It is the same endpoint and the same
 * conversation as the Ask AI screen (askHistory.js) -- one engine, one history.
 *
 * The analyst can take tens of seconds on a real question, because it looks several
 * things up before it answers. So the wait is shown honestly -- what is happening and
 * for how long -- and can be stopped, keeping what it has found, rather than a spinner
 * that implies a second.
 */

// Used until the server's list arrives, or if it cannot be fetched.
const FALLBACK = [
  { q: "Who owes us the most, and how long have they owed it?", area: "Money owed" },
  { q: "How did sales trend over the last 12 months, and where are we heading?", area: "Sales" },
  { q: "Which suppliers do we depend on most?", area: "Buying" },
];
// The starter questions (api/starters.py), per business: chosen from the person's role
// and from what that business's figures say today. Fetched once a page per business;
// the server keeps them for ten minutes.
const startersCache = {};

export default function AskBar({ scope, openDrawer }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | thinking | answer | error
  const [asked, setAsked] = useState(""); // the question the shown answer belongs to
  const [pending, setPending] = useState(""); // the question being worked on now
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [steps, setSteps] = useState([]);
  // A big question's deeper look, carrying on in the background after the first answer.
  const [deep, setDeep] = useState(null); // {state: running|stuck|failed, steps, error}
  const stopDeep = useRef(null);
  const [examples, setExamples] = useState(startersCache[scope] || FALLBACK);
  const [stopping, setStopping] = useState(false);
  const [busy, setBusy] = useState(""); // a question is already running in this conversation
  const [hi, setHi] = useState(-1);
  const wrap = useRef(null);
  const input = useRef(null);
  const run = useRef(null); // this bar's running question (askFlow.runAsk)

  // Cmd/Ctrl-K from anywhere.
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
        setOpen(true);
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);

  // Click outside closes; the answer is kept, and reopening the bar shows it again.
  useEffect(() => {
    if (!open) return;
    const away = (e) => {
      if (wrap.current && !wrap.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

  // The starter questions for this business, once a page per business.
  useEffect(() => {
    if (startersCache[scope]) {
      setExamples(startersCache[scope]);
      return;
    }
    setExamples(FALLBACK);
    if (!open) return;
    let live = true;
    fetchStarters(scope)
      .then((list) => {
        if (!list.length) return;
        startersCache[scope] = list;
        if (live) setExamples(list);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [open, scope]);

  // One question at a time per conversation: the note saying so goes once it is free.
  useEffect(() => {
    const on = () => {
      if (!runningFor(scope)) setBusy("");
    };
    window.addEventListener("cc-ask-running", on);
    return () => window.removeEventListener("cc-ask-running", on);
  }, [scope]);

  // Seconds counter while the analyst works.
  useEffect(() => {
    if (phase !== "thinking") return;
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500);
    return () => clearInterval(t);
  }, [phase]);

  const ask = async (question) => {
    const text = (question || "").trim();
    if (!text) {
      input.current?.focus();
      return;
    }
    setOpen(true);
    const other = runningFor(scope);
    if (other) {
      setBusy(other === run.current
        ? "This question is still being worked out. Stop it to ask another."
        : "A question is still being worked out on the Ask AI screen. Wait for its answer, or stop it.");
      return;
    }
    const args = { question: text, business_code: scope, history: historyFor(scope) };
    const handle = runAsk(scope, args, setSteps);
    if (!handle) return;
    run.current = handle;
    stopDeep.current?.();
    setDeep(null);
    setBusy("");
    setStopping(false);
    setPending(text);
    setQ("");
    setHi(-1);
    setElapsed(0);
    setSteps([]);
    setPhase("thinking");
    try {
      const payload = await handle.answer;
      if (run.current !== handle) return;
      run.current = null;
      setStopping(false);
      remember(scope, text, payload);
      setAsked(text);
      setResult(payload);
      setPhase("answer");
      if (payload?.deep?.ask_id) {
        const deepId = payload.deep.ask_id;
        setDeep({ state: "running", steps: [], askId: deepId });
        stopDeep.current = followDeep(deepId, {
          onSteps: (st) => setDeep((d) => (d?.state === "running" ? { ...d, steps: st } : d)),
          onDone: (full) => {
            replaceAnswer(scope, text, full);
            setResult(full);
            setDeep(null);
          },
          onFailed: (why) => setDeep({ state: "failed", error: why }),
          onStuck: () => setDeep({ state: "stuck" }),
          onStopped: () => setDeep({ state: "stopped" }),
        });
      }
    } catch (e) {
      if (run.current === handle) run.current = null;
      setStopping(false);
      if (e?.name === "AbortError") return;
      setError(e?.message || "The question could not be answered.");
      setPhase("error");
    }
  };

  // "Ask AI about this" on an alert card (legacy/actions.js) asks here, in the bar.
  const askRef = useRef(ask);
  askRef.current = ask;
  useEffect(() => {
    const on = (e) => {
      const question = e.detail?.question;
      if (!question) return;
      window.scrollTo?.({ top: 0 });
      askRef.current(question);
    };
    window.addEventListener("cc-ask", on);
    return () => window.removeEventListener("cc-ask", on);
  }, []);

  // Stop: the server ends the question at its next check and answers with what it had;
  // that partial answer is shown like any other, and the bar is ready for the next one.
  const stop = () => {
    if (!run.current) return;
    setStopping(true);
    run.current.stop();
  };

  const stopDeepLookNow = () => {
    if (deep?.askId) stopDeepLook(deep.askId);
    stopDeep.current?.();
    setDeep({ state: "stopped" });
  };

  const reset = () => {
    stopDeep.current?.();
    setDeep(null);
    setPhase("idle");
    setResult(null);
    setAsked("");
    input.current?.focus();
  };

  // Room for a table, chart or figure cards; a one-line answer keeps the bar's width.
  const wide = phase === "answer" && result?.format === "markdown"
    && /```\s*(chart|figures)|^\s*\|.*\|\s*$/m.test(result.answer || "");
  const recent = recentQuestions(scope);
  const choices = phase === "idle" ? [...recent.map((r) => ({ q: r, area: "Recent" })), ...examples] : [];

  const onKey = (e) => {
    if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
      return;
    }
    if (!choices.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setHi((h) => (h + 1) % choices.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi((h) => (h <= 0 ? choices.length - 1 : h - 1));
    } else if (e.key === "Enter" && hi >= 0 && !q.trim()) {
      e.preventDefault();
      ask(choices[hi].q);
    }
  };

  return (
    <div className={`askwrap${open ? " open" : ""}`} ref={wrap}>
      <form
        className="ask"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <Icon name="spark" className="ask-i" />
        <input
          ref={input}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setHi(-1);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          placeholder={
            phase === "answer" ? "Ask a follow-up…" : "Ask anything about the business — who owes us the most?"
          }
          aria-label="Ask a question about the business"
          aria-expanded={open}
          aria-controls="askpop"
          autoComplete="off"
        />
        <kbd className="ask-k" aria-hidden="true">
          ⌘K
        </kbd>
        <button className="ask-go" type="submit" disabled={phase === "thinking"}>
          <Icon name="search" size={16} />
          <span>Ask</span>
        </button>
      </form>

      {open ? (
        <div className={`askpop${wide ? " wide" : ""}`} id="askpop" role="region"
          aria-live="polite" aria-label="Answer">
          {busy ? (
            <div className="ap-note ap-busy">
              {busy}
              <button className="ap-act" type="button" onClick={() => stopRunning(scope)}>
                Stop it
              </button>
            </div>
          ) : null}

          {phase === "idle" ? (
            <Suggestions choices={choices} recentCount={recent.length} hi={hi} onPick={ask} />
          ) : null}

          {phase === "thinking" ? (
            <div className="ap-think">
              <span className="ap-spin" aria-hidden="true" />
              <div>
                <b>Looking into “{pending}”</b>
                <span>
                  {stopping ? "Stopping — keeping what it has found so far"
                    : steps.length ? "Working through it"
                    : elapsed >= 12 ? "Thinking it through — gathering the figures it needs" : "Reading the question"}
                  {elapsed >= 3 ? ` · ${elapsed}s` : ""}
                  {elapsed >= 40 ? " — big questions take a little longer; a fuller look carries on if needed" : ""}
                </span>
                <StepList steps={steps} />
              </div>
              <button className="ap-act" type="button" onClick={stop} disabled={stopping}
                title="Stop working on this question and show what it has found so far">
                {stopping ? "Stopping…" : "Stop"}
              </button>
            </div>
          ) : null}

          {phase === "error" ? (
            <div className="ap-err">
              <b>Could not answer that.</b> <span>{error}</span>
              <div className="ap-acts">
                <button className="ap-act" type="button" onClick={() => ask(pending)}>
                  Try again
                </button>
                <button className="ap-act" type="button" onClick={reset}>
                  New question
                </button>
              </div>
            </div>
          ) : null}

          {phase === "answer" && result ? (
            <Answer
              asked={asked}
              result={result}
              scope={scope}
              openDrawer={openDrawer}
              onReset={reset}
              onAsk={ask}
              deep={deep}
              onStopDeep={stopDeepLookNow}
              onContinue={() => {
                setOpen(false);
                window.location.hash = "ask";
              }}
            />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Suggestions({ choices, recentCount, hi, onPick }) {
  return (
    <div className="ap-list" role="listbox" aria-label="Suggested questions">
      {choices.map((c, i) => (
        <React.Fragment key={`${c.area}-${c.q}`}>
          {i === 0 && recentCount ? <div className="ap-h">Recent</div> : null}
          {i === recentCount ? <div className="ap-h">Try asking</div> : null}
          <button
            type="button"
            role="option"
            aria-selected={hi === i}
            className={`ap-s${hi === i ? " hl" : ""}`}
            onClick={() => onPick(c.q)}
          >
            <Icon name={c.area === "Recent" ? "list" : "spark"} size={16} />
            <span>{c.q}</span>
            {c.area && c.area !== "Recent" ? <em>{c.area}</em> : null}
          </button>
        </React.Fragment>
      ))}
    </div>
  );
}

function Answer({ asked, result, scope, openDrawer, onReset, onAsk, onContinue, deep, onStopDeep }) {
  const body = useRef(null);
  const [copied, setCopied] = useState(false);
  const [hasTables, setHasTables] = useState(false);
  // Follow-up chips are built once per answer; the ref keeps them asking through the
  // current ask, not the one captured when the answer was drawn.
  const askRef = useRef(onAsk);
  askRef.current = onAsk;
  const markdown = result.format === "markdown";

  // The analyst's markdown is rendered compactly here; a pattern answer has its own
  // layout (tables, entity notes, suggestions), and that renderer is the one used.
  useEffect(() => {
    const el = body.current;
    if (!el) return;
    el.textContent = "";
    if (markdown) el.append(renderMarkdown(result.answer, { onFollowup: (q) => askRef.current(q) }));
    else
      renderAnswer(el, result, {
        onOpen: (records, title) => openRecords(openDrawer, scope, records, title),
      });
    setHasTables(!!el.querySelector("table.dt tbody tr"));
  }, [result, markdown, openDrawer, scope]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${asked}\n\n${result.answer || ""}`);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard refused: nothing to do */
    }
  };

  return (
    <div className="ap-ans">
      <div className="ap-src">
        <Icon name="spark" size={15} />
        {result.mode === "analyst"
          ? `${result.planner === "claude" ? "Claude" : "Gemini"} · read from your ERPNext data · it cannot change anything`
          : "Answered from your ERPNext data"}
      </div>
      <div className="ap-q">{asked}</div>
      {result.notice ? <div className="ap-note info">{result.notice}</div> : null}
      <DeepLook deep={deep} onStop={onStopDeep} />
      {result.analyst_error ? (
        // The analyst failed and the basic engine answered. Said, not hidden: a
        // fallback that passes for the analyst is how a broken one goes unnoticed.
        <div className="ap-note">
          The analyst could not answer this time, so this is the basic engine's answer.
          <span>Reason: {result.analyst_error}</span>
        </div>
      ) : null}
      <div className="ap-body" ref={body} />

      {markdown && result.checked?.length ? (
        <details className="ap-checked">
          <summary>What it checked ({result.checked.length})</summary>
          <ul>
            {result.checked.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="ap-acts">
        {markdown && result.records?.fact ? (
          <button
            className="ap-act pri"
            type="button"
            onClick={() => openRecords(openDrawer, scope, result.records, asked)}
          >
            Open the records behind this
            <Icon name="arrow" size={14} />
          </button>
        ) : null}
        <ExportButton
          label="PDF"
          title="Download this answer as a PDF"
          run={() =>
            api.answerPdf({
              question: asked,
              answer: result.answer,
              checked: result.checked,
              business_code: scope,
              model: result.model,
            })
          }
        />
        {hasTables ? (
          <ExportButton
            label="Excel"
            title="Download the tables in this answer as an Excel file"
            run={() =>
              api.tablesXlsx({ title: asked, tables: tablesFrom(body.current), business_code: scope })
            }
          />
        ) : null}
        <button className="ap-act" type="button" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
        <span className="ap-gap" />
        <button className="ap-act" type="button" onClick={onContinue}
          title="Open this conversation on the Ask AI screen">
          Continue in Ask AI
        </button>
        <button className="ap-act" type="button" onClick={onReset}>
          New question
        </button>
      </div>
    </div>
  );
}

/**
 * The live steps, a run of one kind of lookup shown as one line with a count, and
 * "Show all" for each step's own line (the same grouping as legacy/steps.js draws).
 */
export function StepList({ steps }) {
  const [all, setAll] = useState(false);
  const rows = groupSteps(steps);
  if (!rows.length) return null;
  return (
    <div className="ap-stepwrap">
      <ol className="ap-steps">
        {rows.map((r, i) => (
          <li key={i} className={i === rows.length - 1 ? "now" : "done"}>
            {r.label}
            {r.count > 1 ? <span className="ap-stepn">×{r.count}</span> : null}
            {all && r.count > 1 ? (
              <ul className="ap-stepd">
                {r.details.map((d, j) => <li key={j}>{d}</li>)}
              </ul>
            ) : null}
          </li>
        ))}
      </ol>
      {hasHidden(rows) ? (
        <button type="button" className="ap-stepall" onClick={() => setAll((a) => !a)}>
          {all ? "Show less" : "Show all"}
        </button>
      ) : null}
    </div>
  );
}

/** Where a big question's deeper look has got to, above the first answer. */
export function DeepLook({ deep, onStop }) {
  if (!deep) return null;
  if (deep.state === "running") {
    return (
      <div className="ap-deep">
        <span className="ap-spin" aria-hidden="true" />
        <div>
          <b>Taking a deeper look</b>
          <span>
            This question needs more than a quick pass. A fuller answer will replace this one in a
            few minutes; the first pass is below.
          </span>
          <StepList steps={deep.steps} />
        </div>
        {onStop ? (
          <button className="ap-act" type="button" onClick={onStop}
            title="Stop the deeper look and keep the first-pass answer">
            Stop
          </button>
        ) : null}
      </div>
    );
  }
  return (
    <div className="ap-note">
      {deep.state === "stuck"
        ? "The deeper look could not start: the server's background workers are not running. This is the first-pass answer."
        : deep.state === "stopped"
          ? "You stopped the deeper look, so this is the first-pass answer."
          : "The deeper look stopped before it finished, so this is the first-pass answer."}
      {deep.error ? <span>Reason: {deep.error}</span> : null}
    </div>
  );
}

function openRecords(openDrawer, scope, records, title) {
  if (!openDrawer || !records?.fact) return;
  openDrawer(
    <Records
      scope={scope}
      fact={records.fact}
      filters={records.filters}
      title={(title || "The records behind it").slice(0, 80)}
      openDrawer={openDrawer}
    />,
  );
}
