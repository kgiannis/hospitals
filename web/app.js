const results = document.getElementById("results");
const input = document.getElementById("specialty");
const datalist = document.getElementById("specialties");

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
  card.addEventListener("click", () => showHospital(h.name));
  return card;
}

async function loadSpecialties() {
  const res = await fetch("/api/specialties");
  if (!res.ok) {
    results.textContent = "Το πρόγραμμα δεν είναι ακόμη διαθέσιμο.";
    return;
  }
  const data = await res.json();
  document.getElementById("date").textContent = data.date_greek;
  datalist.innerHTML = "";
  for (const name of data.specialties) {
    const opt = document.createElement("option");
    opt.value = name;
    datalist.appendChild(opt);
  }
  showNow();
}

async function showNow() {
  const res = await fetch("/api/now");
  const data = await res.json();
  results.innerHTML = `<h2>Ανοιχτά τώρα (${data.now})</h2>`;
  for (const group of data.groups) {
    const block = document.createElement("div");
    block.className = "group";
    block.innerHTML = `<h2>${group.specialty}</h2>`;
    for (const h of group.hospitals) block.appendChild(hospitalCard({ ...h, open_now: true }));
    results.appendChild(block);
  }
}

async function showSpecialty(name) {
  const res = await fetch(`/api/specialties/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>${data.specialty} (τώρα ${data.now})</h2>`;
  for (const h of data.hospitals) results.appendChild(hospitalCard(h));
}

async function showHospital(name) {
  const res = await fetch(`/api/hospitals/${encodeURIComponent(name)}`);
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>${data.hospital} (τώρα ${data.now})</h2>`;
  for (const e of data.entries) {
    const card = document.createElement("div");
    card.className = "hospital" + (e.open_now ? " open" : "");
    const note = e.note ? `<div class="note">${e.note}</div>` : "";
    card.innerHTML =
      `<div>${e.specialty}</div><div class="window">${fmtWindow(e.window)}</div>${note}`;
    results.appendChild(card);
  }
}

async function showHealthCenters() {
  const res = await fetch("/api/health-centers");
  if (!res.ok) return;
  const data = await res.json();
  results.innerHTML = `<h2>Κέντρα Υγείας (τώρα ${data.now})</h2>`;
  for (const c of data.health_centers) results.appendChild(hospitalCard(c));
}

input.addEventListener("change", () => {
  if (input.value) showSpecialty(input.value);
});
document.getElementById("show-health-centers").addEventListener("click", showHealthCenters);

loadSpecialties();
