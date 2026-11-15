import React, { useEffect, useState } from "react";
import { settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Msg, act, when } from "./SettingsParts.jsx";

const UNIT = { amount: "", days: "days", percent: "%", count: "", points: "points" };

/**
 * Administrator only: for each business, which recommendation rules run and at what
 * thresholds (Fixed, or Adaptive: learned from the business's own history), the
 * unusual-movement findings, the daily email digest, the optional Daily Brief by Claude,
 * the daily AI review, and what the platform has learned -- each figure's history and
 * usual range, the rules' learned weights and the outcomes of advice marked done
 * (insights/core/platform_settings.py recommendations / set_recommendations /
 * run_review_now).
 */
export default function SettingsRecommend() {
  const [code, setCode] = useState("");
  const view = useApi(() => settingsApi.recommend(code), [code]);
  const [f, setF] = useState(null);
  const [st, setSt] = useState({});
  const [brief, setBrief] = useState({});
  const [rev, setRev] = useState({});

  useEffect(() => {
    const d = view.data;
    if (!d) return;
    setF({
      digest: d.digest,
      brief: d.brief,
      anomalies: d.anomalies,
      ai_review: d.ai_review,
      rules: Object.fromEntries(d.rules.map((r) => [r.rule_id, {
        enabled: r.enabled,
        params: Object.fromEntries(r.params.map((p) => [p.key, String(p.value)])),
        ...(r.mode ? { mode: r.mode } : {}),
      }])),
    });
  }, [view.data]);

  if (view.loading && !view.data) return <Loading what="Reading the recommendation rules" />;
  if (view.error && !view.data) return <Failed error={view.error} onRetry={view.reload} what="the recommendation rules" />;
  if (!f) return null;
  const d = view.data;

  const setRule = (id, change) => setF((x) => ({
    ...x, rules: { ...x.rules, [id]: { ...x.rules[id], ...change } },
  }));
  const setParam = (id, key) => (e) => setF((x) => ({
    ...x,
    rules: { ...x.rules, [id]: { ...x.rules[id], params: { ...x.rules[id].params, [key]: e.target.value } } },
  }));

  const save = async (e) => {
    e.preventDefault();
    const out = await act(setSt, () => settingsApi.setRecommend({
      business_code: d.business_code, rules: f.rules, digest: f.digest, brief: f.brief,
      anomalies: f.anomalies, ai_review: f.ai_review,
    }), "Saved. The recommendations are worked out again with these settings.");
    if (out) view.reload();
  };

  const writeNow = async () => {
    const out = await act(setBrief, () => settingsApi.writeBriefNow(d.business_code));
    if (out) {
      setBrief({ [out.ok ? "ok" : "bad"]: out.says });
      view.reload();
    }
  };

  const reviewNow = async () => {
    const out = await act(setRev, () => settingsApi.runReviewNow(d.business_code));
    if (out) {
      setRev({ [out.ok ? "ok" : "bad"]: out.says });
      view.reload();
    }
  };

  const digest = d.digest_state;
  const last = d.brief_state;
  const review = d.ai_review_state;
  const learning = d.learning || {};
  return (
    <form className="st-stack" onSubmit={save}>
      <div className="panel">
        <div className="ph">
          <div>
            <b>Recommendations</b>
            <span>What the platform recommends to the managers, from each business&apos;s own figures. Every number in a recommendation comes from that business&apos;s data.</span>
          </div>
          {d.businesses.length > 1 ? (
            <select aria-label="Business" value={d.business_code} onChange={(e) => setCode(e.target.value)}>
              {d.businesses.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
            </select>
          ) : null}
        </div>
        <div className="st-rec-switch">
          <label className="st-check">
            <input type="checkbox" checked={f.digest} onChange={(e) => setF((x) => ({ ...x, digest: e.target.checked }))} />
            <span>
              Email a daily digest to the managers
              <span className="st-sub">
                At 07:00: what is new since the last digest, and the largest still open.
                {d.email_configured ? "" : " Email is not set up yet (Settings, Email), so it would be recorded as not sent."}
                {digest?.at ? ` Last: ${when(digest.at)}, ${digest.says}` : ""}
              </span>
            </span>
          </label>
          <label className="st-check">
            <input type="checkbox" checked={f.brief} onChange={(e) => setF((x) => ({ ...x, brief: e.target.checked }))} />
            <span>
              Daily Brief by Claude
              <span className="st-sub">
                A short plain-English brief at the top of the Executive Summary and in the digest: what changed since yesterday and the top three actions, written only from the recommendations and headline figures. {d.brief_cost}
                {d.claude_configured ? "" : " No Claude key is set (Settings, Claude), so it cannot be written yet."}
                {last?.at ? ` Last: ${when(last.at)}, ${last.text ? "written" : last.error}` : ""}
              </span>
            </span>
          </label>
          {d.brief ? (
            <div>
              <button type="button" className="btn" onClick={writeNow} disabled={brief.busy}>
                {brief.busy ? "Writing…" : "Write Today's Brief Now"}
              </button>
              <Msg tone="ok">{brief.ok}</Msg>
              <Msg tone="bad">{brief.bad}</Msg>
            </div>
          ) : null}
          <label className="st-check">
            <input type="checkbox" checked={f.anomalies} onChange={(e) => setF((x) => ({ ...x, anomalies: e.target.checked }))} />
            <span>
              Unusual Movements
              <span className="st-sub">
                Recommend looking into a figure that has moved well outside this business&apos;s own usual range when no rule already speaks to it. Worked out from the business&apos;s history only; no Claude request.
              </span>
            </span>
          </label>
          <label className="st-check">
            <input type="checkbox" checked={f.ai_review} onChange={(e) => setF((x) => ({ ...x, ai_review: e.target.checked }))} />
            <span>
              Daily AI Review
              <span className="st-sub">
                Claude reads the findings, the figures with their usual ranges, managers&apos; decisions and what came of them, and proposes what no single rule covers. Every figure it gives is checked against that evidence; anything that fails is not used. Shown as AI-found. {d.ai_review_cost}
                {d.claude_configured ? "" : " No Claude key is set (Settings, Claude), so it cannot run yet."}
                {review?.at ? ` Last: ${when(review.at)}, ${review.ok ? `${review.accepted || 0} accepted, ${(review.rejected || []).length} not used` : review.error || review.skipped || ""}.` : ""}
              </span>
            </span>
          </label>
          {d.ai_review ? (
            <div>
              <button type="button" className="btn" onClick={reviewNow} disabled={rev.busy}>
                {rev.busy ? "Reviewing…" : "Run Today's Review Now"}
              </button>
              <Msg tone="ok">{rev.ok}</Msg>
              <Msg tone="bad">{rev.bad}</Msg>
              {(review?.rejected || []).length ? (
                <ul className="st-rec-list">
                  {review.rejected.map((x, i) => <li key={i}><b>Not used:</b> {x.title} — {x.why}</li>)}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel">
        <div className="ph">
          <div>
            <b>Rules</b>
            <span>Switch a rule off, or change when it recommends. A rule managers keep marking not relevant says so here.</span>
          </div>
          <button type="submit" className="btn pri" disabled={st.busy}>{st.busy ? "Saving…" : "Save Changes"}</button>
        </div>
        <Msg tone="ok">{st.ok}</Msg>
        <Msg tone="bad">{st.bad}</Msg>
        <table className="dt st-rec">
          <thead>
            <tr>
              <th>On</th>
              <th>What It Watches</th>
              <th>When It Recommends</th>
            </tr>
          </thead>
          <tbody>
            {d.rules.map((r) => (
              <tr key={r.rule_id}>
                <td>
                  <input type="checkbox" aria-label={`${r.title} on`} checked={f.rules[r.rule_id].enabled}
                    onChange={(e) => setRule(r.rule_id, { enabled: e.target.checked })} />
                </td>
                <td>
                  {r.title}
                  <span className="st-sub">{r.area_label}</span>
                  {r.suggestion ? <span className="tag t-wt">{r.suggestion}</span> : null}
                  {r.weight_explain && r.weight !== 1 ? <span className="st-sub">{r.weight_explain}</span> : null}
                </td>
                <td>
                  <div className="st-rec-params">
                    {r.params.map((p) => (
                      <label key={p.key}>
                        <span>{p.label}{UNIT[p.unit] ? ` (${UNIT[p.unit]})` : ""}</span>
                        <input inputMode="decimal" value={f.rules[r.rule_id].params[p.key]}
                          onChange={setParam(r.rule_id, p.key)} disabled={!f.rules[r.rule_id].enabled} />
                      </label>
                    ))}
                    {r.mode ? (
                      <label>
                        <span>Threshold</span>
                        <select aria-label={`${r.title} threshold`} value={f.rules[r.rule_id].mode}
                          disabled={!f.rules[r.rule_id].enabled}
                          onChange={(e) => setRule(r.rule_id, { mode: e.target.value })}>
                          <option value="adaptive">Adaptive</option>
                          <option value="fixed">Fixed</option>
                        </select>
                      </label>
                    ) : null}
                  </div>
                  {r.threshold?.says ? <span className="st-sub">{r.threshold.says}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="panel">
        <div className="ph">
          <div>
            <b>Learning</b>
            <span>What the platform has learned about {d.business_name}: each figure&apos;s history and usual range, and what came of advice marked done. A figure with too little history says how much more it needs; no range is invented.</span>
          </div>
        </div>
        {learning.what_worked?.says ? <p className="st-sub st-rec-worked">{learning.what_worked.says}</p> : null}
        <table className="dt st-rec st-learn">
          <thead>
            <tr>
              <th>Figure</th>
              <th>History</th>
              <th>Usual Range</th>
            </tr>
          </thead>
          <tbody>
            {(learning.figures || []).map((x) => (
              <tr key={x.key}>
                <td>{x.label}<span className="st-sub">{x.grain}</span></td>
                <td>{x.points ? `${x.points} ${x.grain === "Monthly" ? "month" : "day"}${x.points === 1 ? "" : "s"}` : "None yet"}</td>
                <td>
                  {x.says}
                  {x.why_now ? <span className="st-sub st-rec-flag">{x.why_now}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(learning.outcomes || []).length ? (
          <>
            <div className="st-rec-h">Outcomes of Advice Marked Done</div>
            <ul className="st-rec-list">
              {learning.outcomes.map((o, i) => (
                <li key={i}><b>{o.outcome}:</b> {o.title}{o.note ? ` — ${o.note}` : ""}{o.checked_on ? ` (checked ${o.checked_on})` : ""}</li>
              ))}
            </ul>
          </>
        ) : null}
        {(review?.patterns || []).length ? (
          <>
            <div className="st-rec-h">Patterns the Last AI Review Noticed</div>
            <ul className="st-rec-list">
              {review.patterns.map((x, i) => <li key={i}><b>{x.title}.</b> {x.explanation}</li>)}
            </ul>
          </>
        ) : null}
      </div>
    </form>
  );
}
