// Serverless client for the Attica hospitals PWA.
// Reads the static JSON published under ./data/ and computes everything
// (today's date, "open now") in the browser — no backend involved.

const results = document.getElementById("results");
const input = document.getElementById("specialty");
const datalist = document.getElementById("specialties");
const clearBtn = document.getElementById("clear");
const toggleBtn = document.getElementById("toggle-health-centers");

const DATA_BASE = "./data";

const HINT_HTML =
  '<p class="hint">Διάλεξε ειδικότητα για να δεις ποιο νοσοκομείο εφημερεύει.</p>';

// toggleBtn swaps between these two, so its label always names where it goes.
const HEALTH_LABEL = "Κέντρα Υγείας";
const HOSPITALS_LABEL = "Νοσοκομεία";

// The one day's schedule currently loaded into memory.
let schedule = null;

// Which panel is on screen, and the specialty to return to when leaving the
// health-centre view. The search box is emptied while health centres show (so
// it cannot contradict the panel), so the name has to be remembered here.
let view = "hint"; // "hint" | "specialty" | "health"
let lastSpecialty = null;

// --- time helpers (always Europe/Athens, regardless of device timezone) ---

// "YYYY-MM-DD" for the current instant in Athens.
function athensToday() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Athens",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

// "HH:MM" for the current instant in Athens.
function athensNow() {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Athens",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function toMinutes(hhmm) {
  const [h, m] = hhmm.split(":");
  return parseInt(h, 10) * 60 + parseInt(m, 10);
}

// Port of hospitals/windows.py::is_open_at.
function isOpenAt(window, nowHhmm) {
  const now = toMinutes(nowHhmm);
  const start = toMinutes(window.start);
  const end = toMinutes(window.end);
  if (window.crosses_midnight) {
    if (start === end) return true; // 08:00->08:00 == 24h
    return now >= start || now <= end;
  }
  return start <= now && now <= end;
}

// --- rendering (kept from the original UI) ---

function fmtWindow(w) {
  const suffix = w.crosses_midnight ? " (επομένης)" : "";
  return `${w.start} – ${w.end}${suffix}`;
}

function hospitalCard(h) {
  const card = document.createElement("div");
  card.className = "hospital" + (h.open_now ? " open" : "");
  const note = h.note ? `<div class="note">${h.note}</div>` : "";
  const badge = h.open_now ? `<span class="badge">ΑΝΟΙΧΤΟ ΤΩΡΑ</span>` : "";
  card.innerHTML =
    `<div>${h.name} ${badge}</div>` +
    `<div class="window">${fmtWindow(h.window)}</div>${note}`;
  return card;
}

// Attach open_now (against Athens time) and sort so open ones come first,
// preserving the source order within each group.
function withOpenNow(entries) {
  const now = athensNow();
  return entries
    .map((e, i) => ({ ...e, open_now: isOpenAt(e.window, now), _i: i }))
    .sort((a, b) => (b.open_now - a.open_now) || (a._i - b._i));
}

// --- data loading ---

async function fetchJson(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

// Pick today's date if published, else the most recent published date <= today.
function pickDate(dates, today) {
  if (dates.includes(today)) return today;
  const past = dates.filter((d) => d <= today).sort();
  if (past.length) return past[past.length - 1];
  return dates.length ? [...dates].sort()[dates.length - 1] : null;
}

async function load() {
  let index;
  try {
    index = await fetchJson(`${DATA_BASE}/index.json`);
  } catch {
    results.textContent = "Το πρόγραμμα δεν είναι ακόμη διαθέσιμο.";
    return;
  }

  const today = athensToday();
  const date = pickDate(index.dates || [], today);
  if (!date) {
    results.textContent = "Το πρόγραμμα δεν είναι ακόμη διαθέσιμο.";
    return;
  }

  schedule = await fetchJson(`${DATA_BASE}/${date}.json`);

  const dateEl = document.getElementById("date");
  dateEl.textContent = schedule.date_greek || date;
  if (date !== today) {
    dateEl.textContent += "  (πιο πρόσφατο διαθέσιμο)";
  }

  datalist.innerHTML = "";
  for (const s of schedule.specialties) {
    const opt = document.createElement("option");
    opt.value = s.name;
    datalist.appendChild(opt);
  }

  showHint();
}

// --- views ---

// Each view function owns the whole toolbar state — panel, search box, and both
// button labels — so no combination of clicks can leave them inconsistent.

// The empty state. Both the initial render and "Καθαρισμός" go through here so
// the two cannot drift apart.
function showHint() {
  view = "hint";
  lastSpecialty = null;
  input.value = "";
  results.innerHTML = HINT_HTML;
  clearBtn.hidden = true;
  toggleBtn.textContent = HEALTH_LABEL;
}

function showSpecialty(name) {
  if (!schedule) return;
  const spec = schedule.specialties.find((s) => s.name === name);
  if (!spec) return;
  view = "specialty";
  lastSpecialty = spec.name;
  results.innerHTML = `<h2>${spec.name}</h2>`;
  for (const h of withOpenNow(spec.hospitals)) results.appendChild(hospitalCard(h));
  clearBtn.hidden = false;
  toggleBtn.textContent = HEALTH_LABEL;
}

function showHealthCenters() {
  if (!schedule) return;
  view = "health";
  // Clear the box so it never contradicts the panel; lastSpecialty remembers it.
  input.value = "";
  results.innerHTML = `<h2>${HEALTH_LABEL}</h2>`;
  for (const c of withOpenNow(schedule.health_centers)) results.appendChild(hospitalCard(c));
  clearBtn.hidden = false;
  toggleBtn.textContent = HOSPITALS_LABEL;
}

// Back out of the health-centre view: to the specialty that was showing before
// it, or to the hint if health centres were opened straight from the hint.
function showHospitals() {
  if (lastSpecialty) {
    input.value = lastSpecialty;
    showSpecialty(lastSpecialty);
    return;
  }
  showHint();
}

// Bound to both events: "change" covers datalist selection and blur, "input"
// catches the keystroke that empties the field. A partial or misspelled value
// falls through to showSpecialty's no-match guard, leaving the panel as-is.
function onSpecialtyChanged() {
  if (!input.value) {
    showHint();
    return;
  }
  showSpecialty(input.value);
}

input.addEventListener("input", onSpecialtyChanged);
input.addEventListener("change", onSpecialtyChanged);
toggleBtn.addEventListener("click", () => {
  if (view === "health") showHospitals();
  else showHealthCenters();
});
clearBtn.addEventListener("click", () => {
  showHint();
  // The button hides itself on click, so move focus somewhere useful.
  input.focus();
});

load();
