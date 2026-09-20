/**
 * "Good morning, Michael" with an icon for the time of day.
 *
 * The command screen's markup still has the empty #greet element the old script
 * filled. Until that view becomes a component, this fills it -- built from DOM
 * nodes rather than innerHTML, so a person's name is text and never markup.
 */

const DAY = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

const ICONS = {
  dawn: `<g class="todrise"><path d="M13 34a11 11 0 0 1 22 0Z" fill="var(--dawn)"/>
    <g class="todglow" stroke="var(--sun)" stroke-width="2.2" stroke-linecap="round">
    <path d="M24 8v5M8.6 16.6l3.5 3.5M39.4 16.6L35.9 20.1"/></g></g>
    <path d="M6 34h36" stroke="var(--dawn)" stroke-width="2.4" stroke-linecap="round"/>
    <path d="M11 40h26" stroke="var(--dawn)" stroke-width="2.2" stroke-linecap="round" opacity=".45"/>`,
  sun: `<g class="todray" stroke="var(--sun)" stroke-width="2.4" stroke-linecap="round">
    <path d="M24 4v6M24 38v6M4 24h6M38 24h6M9.9 9.9l4.3 4.3M33.8 33.8l4.3 4.3M38.1 9.9l-4.3 4.3M14.2 33.8l-4.3 4.3"/></g>
    <circle class="todcore" cx="24" cy="24" r="9" fill="var(--sun)"/>`,
  moon: `<path class="todcore" d="M31 6a18 18 0 1 0 11 32A19 19 0 0 1 31 6Z" fill="var(--moon)"/>
    <circle class="todstar" cx="12" cy="13" r="1.7" fill="var(--star)"/>
    <circle class="todstar" cx="20" cy="7" r="1.2" fill="var(--star)"/>
    <circle class="todstar" cx="9" cy="21" r="1.2" fill="var(--star)"/>`,
};

function partOfDay(hour) {
  if (hour >= 12 && hour < 17) return { word: "Good afternoon", icon: "sun" };
  if (hour >= 17 || hour < 5) return { word: "Good evening", icon: "moon" };
  return { word: "Good morning", icon: "dawn" };
}

export function renderGreeting(el, user) {
  if (!el) return;
  const now = new Date();
  const { word, icon } = partOfDay(now.getHours());

  el.textContent = "";

  const text = document.createElement("div");
  const line = document.createElement("div");
  // textContent, not innerHTML: the name comes from the session.
  line.textContent = `${word}, ${user?.name || "there"}`;
  const when = document.createElement("div");
  when.className = "when";
  when.style.fontWeight = "400";
  when.textContent =
    `${DAY[now.getDay()]} ${now.toLocaleDateString("en-GB", {
      day: "numeric",
      month: "long",
      year: "numeric",
    })} · ${now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
  text.append(line, when);

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "tod");
  svg.setAttribute("viewBox", "0 0 48 48");
  svg.setAttribute("fill", "none");
  svg.innerHTML = ICONS[icon];

  el.append(text, svg);
}
