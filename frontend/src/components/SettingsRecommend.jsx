import React, { useEffect, useState } from "react";
import { settingsApi } from "../api/client.js";
import { useApi } from "../useApi.js";
import { Failed, Loading } from "./States.jsx";
import { Msg, act, when } from "./SettingsParts.jsx";

const UNIT = { amount: "", days: "days", percent: "%", count: "", points: "points" };

/**
 * Administrator only: for each business, which recommendation rules run and at what
 * thresholds, the daily email digest, and the optional Daily Brief by Claude
 * (insights/core/platform_settings.py recommendations / set_recommendations).
 */
export default function SettingsRecommend() {
  const [code, setCode] = useState("");
  const view = useApi(() => settingsApi.recommend(code), [code]);
  const [f, setF] = useState(null);
  const [st, setSt] = useState({});
  const [brief, setBrief] = useState({});

  useEffect(() => {
    const d = view.data;
    if (!d) return;
    setF({
      digest: d.digest,
      brief: d.brief,
      rules: Object.fromEntries(d.rules.map((r) => [r.rule_id, {
        enabled: r.enabled,
        params: Object.fromEntries(r.params.map((p) => [p.key, String(p.value)])),
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

  const digest = d.digest_state;
  const last = d.brief_state;
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
              <th>What it watches</th>
              <th>When it recommends</th>
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
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </form>
  );
}
