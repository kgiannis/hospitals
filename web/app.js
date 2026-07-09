// Serverless client for the Attica hospitals PWA.
// Reads the static JSON published under ./data/ and computes everything
// (today's date, "open now") in the browser — no backend involved.

const results = document.getElementById("results");
const input = document.getElementById("specialty");
const datalist = document.getElementById("specialties");

const DATA_BASE = "./data";

// The one day's schedule currently loaded into memory.
let schedule = null;

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

  results.innerHTML =
    '<p class="hint">Διάλεξε ειδικότητα για να δεις ποιο νοσοκομείο εφημερεύει.</p>';
}

// --- views ---

function showSpecialty(name) {
  if (!schedule) return;
  const spec = schedule.specialties.find((s) => s.name === name);
  if (!spec) return;
  results.innerHTML = `<h2>${spec.name}</h2>`;
  for (const h of withOpenNow(spec.hospitals)) results.appendChild(hospitalCard(h));
}

function showHealthCenters() {
  if (!schedule) return;
  results.innerHTML = `<h2>Κέντρα Υγείας</h2>`;
  for (const c of withOpenNow(schedule.health_centers)) results.appendChild(hospitalCard(c));
}

input.addEventListener("change", () => {
  if (input.value) showSpecialty(input.value);
});
document.getElementById("show-health-centers").addEventListener("click", showHealthCenters);

load();
