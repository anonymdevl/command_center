import React, { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";
import { historyFor, recentQuestions, remember, replaceAnswer } from "../askHistory.js";
import { followDeep, withSteps } from "../askFlow.js";
import { renderAnswer } from "../legacy/answer.js";
import { renderMarkdown } from "../legacy/markdown.js";
import Icon from "./Icon.jsx";
import ExportButton from "./ExportButton.jsx";
import { tablesFrom } from "../exportTables.js";
import Records from "./Records.jsx";

/**
 * The question bar, answering in place.
 *
 * A question asked here is answered in a panel under the bar, so a manager never
 * leaves the screen they are reading. It is the same endpoint and the same
 * conversation as the Ask AI screen (askHistory.js) -- one engine, one history.
 *
 * The analyst can take tens of seconds on a real question, because it looks several
 * things up before it answers. So the wait is shown honestly -- what is happening and
 * for how long -- and can be cancelled, rather than a spinner that implies a second.
 */

// Used until the server's list arrives, or if it cannot be fetched.
const FALLBACK = [
  { q: "Who owes us the most, and how long have they owed it?", area: "Money owed" },
  { q: "How did sales trend over the last 12 months, and where are we heading?", area: "Sales" },
  { q: "Which suppliers do we depend on most?", area: "Buying" },
];
let examplesCache = null;

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
  const [examples, setExamples] = useState(examplesCache || FALLBACK);
  const [hi, setHi] = useState(-1);
  const wrap = useRef(null);
  const input = useRef(null);
  const ctrl = useRef(null);

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

  // The suggestions, once per page, from the server's own list.
  useEffect(() => {
    if (!open || examplesCache) return;
    api.answerable()
      .then((r) => {
        const list = (r?.examples || []).filter((e) => e?.q);
        if (list.length) {
          examplesCache = list;
          setExamples(list);
        }
      })
      .catch(() => {});
  }, [open]);

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
    ctrl.current?.abort();
    stopDeep.current?.();
    setDeep(null);
    const c = new AbortController();
    ctrl.current = c;
    setOpen(true);
    setPending(text);
    setQ("");
    setHi(-1);
    setElapsed(0);
    setSteps([]);
    setPhase("thinking");
    try {
      const args = { question: text, business_code: scope, history: historyFor(scope) };
      const payload = await withSteps(args, c.signal, setSteps);
      if (c.signal.aborted) return;
      remember(scope, text, payload);
      setAsked(text);
      setResult(payload);
      setPhase("answer");
      if (payload?.deep?.ask_id) {
        setDeep({ state: "running", steps: [] });
        stopDeep.current = followDeep(payload.deep.ask_id, {
          onSteps: (st) => setDeep((d) => (d?.state === "running" ? { ...d, steps: st } : d)),
          onDone: (full) => {
            replaceAnswer(scope, text, full);
            setResult(full);
            setDeep(null);
          },
          onFailed: (why) => setDeep({ state: "failed", error: why }),
          onStuck: () => setDeep({ state: "stuck" }),
        });
      }
    } catch (e) {
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

  const cancel = () => {
    ctrl.current?.abort();
    setPhase(result ? "answer" : "idle");
  };

  const reset = () => {
    ctrl.current?.abort();
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
          {phase === "idle" ? (
            <Suggestions choices={choices} recentCount={recent.length} hi={hi} onPick={ask} />
          ) : null}

          {phase === "thinking" ? (
            <div className="ap-think">
              <span className="ap-spin" aria-hidden="true" />
              <div>
                <b>Looking into “{pending}”</b>
                <span>
                  {steps.length ? "Working through it"
                    : elapsed >= 12 ? "Waiting for Gemini, the AI model, to reply" : "Reading the question"}
                  {elapsed >= 3 ? ` · ${elapsed}s` : ""}
                  {elapsed >= 40 ? " — Google is replying slowly; a model that stalls is swapped for another" : ""}
                </span>
                {steps.length ? (
                  <ol className="ap-steps">
                    {steps.map((s, i) => (
                      <li key={i} className={i === steps.length - 1 ? "now" : "done"}>
                        {s}
                      </li>
                    ))}
                  </ol>
                ) : null}
              </div>
              <button className="ap-act" type="button" onClick={cancel}>
                Cancel
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

function Answer({ asked, result, scope, openDrawer, onReset, onAsk, onContinue, deep }) {
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
          ? `Gemini · read from your ERPNext data · it cannot change anything`
          : "Answered from your ERPNext data"}
      </div>
      <div className="ap-q">{asked}</div>
      {result.notice ? <div className="ap-note info">{result.notice}</div> : null}
      <DeepLook deep={deep} />
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

/** Where a big question's deeper look has got to, above the first answer. */
export function DeepLook({ deep }) {
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
          {deep.steps?.length ? (
            <ol className="ap-steps">
              {deep.steps.map((s, i) => (
                <li key={i} className={i === deep.steps.length - 1 ? "now" : "done"}>{s}</li>
              ))}
            </ol>
          ) : null}
        </div>
      </div>
    );
  }
  return (
    <div className="ap-note">
      {deep.state === "stuck"
        ? "The deeper look could not start: the server's background workers are not running. This is the first-pass answer."
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
