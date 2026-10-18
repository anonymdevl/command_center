/**
 * The Reports screen's "Schedule" column, from Command Center Report Schedule.
 *
 * The column used to state the plan agreed for each report, with a note that running on
 * it was not switched on. Each cell now says the schedule that is actually set -- "Mondays
 * at 07:00 · 4 people", "Not scheduled" -- with a button to set or change it
 * (components/ScheduleDialog.jsx). The board report keeps "On request": it is released
 * only with an approval, so it is never sent on a timer.
 */

export function renderSchedules(root, data) {
  if (!root || !data) return;
  const by = Object.fromEntries((data.schedules || []).map((s) => [s.report, s]));
  root.querySelectorAll("button[data-report]").forEach((run) => {
    const code = run.dataset.report;
    const row = run.closest("tr");
    const cell = row?.children?.[2];
    if (!cell || (data.unschedulable || []).includes(code)) return;
    const s = by[code];
    const title = row.querySelector("td b")?.textContent?.trim() || code;
    cell.textContent = "";
    cell.style.color = "";
    const says = document.createElement("span");
    says.className = s?.enabled ? "sch-on" : "sch-off";
    says.textContent = s ? s.says : "Not scheduled";
    if (s?.last_status) says.title = s.last_status;
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "lnk sch-edit";
    edit.dataset.ccWired = "1";
    edit.textContent = s ? "Change" : "Set a schedule";
    edit.onclick = (e) => {
      e.stopPropagation();
      window.dispatchEvent(new CustomEvent("cc-schedule", { detail: { code, title, current: s || null } }));
    };
    cell.append(says, edit);
    if (s?.next_run && s.enabled) {
      const next = document.createElement("small");
      next.className = "sch-next";
      next.textContent = `next ${s.next_run.replace("T", " ")}`;
      cell.append(next);
    }
  });
}
