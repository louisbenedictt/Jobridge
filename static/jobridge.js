// JOBRIDGE: browser side of templates/jobridge.html.
// The page only keeps the user's choices (CV, skills, cutoff month, SDG priorities, chosen roles). Every number it
// shows comes from the Flask API in flask_app.py, which calculates it with core.py from the pipeline's data files.

const PLOT_CONFIG = { responsive: true, displayModeBar: false, displaylogo: false };
const C_OBSERVED = "#1d4ed8", C_MODERATE = "#d97706", C_FAST = "#059669", C_MUTED = "#cbd5e1", C_MISSING = "#e2e8f0";
const PCT_HOVER = "%{x|%b %Y}: %{y:.1%}<extra></extra>";
const TREND = {
  "rising": { text: "▲ rising", cls: "trend-rising" },
  "declining": { text: "▼ declining", cls: "trend-declining" },
  "stable": { text: "● stable", cls: "trend-stable" },
  "limited data": { text: "○ limited data", cls: "trend-limited" },
};
const BADGE_CLS = {
  now: "bg-slate-100 text-slate-700 border-slate-300",
  upgrade: "bg-blue-50 text-blue-700 border-blue-200",
  move: "bg-emerald-50 text-emerald-800 border-emerald-200",
  other: "bg-amber-50 text-amber-800 border-amber-200",
};
const MODE_ON = "cursor-pointer inline-flex items-center gap-2 px-3.5 py-2 rounded-md border border-blue-600 bg-blue-50 text-blue-800 font-semibold text-xs";
const MODE_OFF = "cursor-pointer inline-flex items-center gap-2 px-3.5 py-2 rounded-md border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 font-medium text-xs";
const VIEW_ON = "px-3 py-1.5 rounded bg-white text-blue-700 shadow-2xs font-semibold flex items-center gap-1.5 border border-slate-200/80";
const VIEW_OFF = "px-3 py-1.5 rounded text-slate-600 hover:text-slate-900 flex items-center gap-1.5";
const TABS = ["tab-intake", "tab-radar", "tab-jobs", "tab-pathway", "tab-about"];

const state = {
  meta: null,             // /api/meta
  skillName: {},          // skill_id -> name
  view: "worker",
  tab: "tab-intake",
  mode: "sample",
  sample: null,
  cutoffIndex: 0,
  sdg: [],
  sdgWeight: 0.15,
  skills: {},             // skill_id -> evidence from the CV ("added by you" for manual picks)
  pathRole: null,         // null = the best upgrade or move, chosen by the server
  exploreSkill: null,     // null = the skill the radar suggests
  defaultSkill: null,
  analysis: null,         // last /api/analyze answer
  done: new Set(),        // pathway steps marked done (only in this browser)
  team: { source: "sample", uploaded: [], result: null },
  charts: {},             // last traces and layout per chart, redrawn when the chart becomes visible
};

const byId = id => document.getElementById(id);
const cutoff = () => state.meta.cutoff_options[state.cutoffIndex];
const skillName = id => state.skillName[id] || id;


// ---------------------------------------------------------------- small helpers
function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function short(text, n) {
  return text.length > n ? text.slice(0, n) + "…" : text;
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function trendInfo(t) {
  return TREND[t] || TREND["limited data"];
}

function trendBadge(t) {
  const item = trendInfo(t);
  return `<span class="inline-flex items-center text-[11px] font-mono font-semibold whitespace-nowrap ${item.cls}">${item.text}</span>`;
}

function fillSelect(sel, items, selected) {
  sel.innerHTML = items.map(([v, t]) =>
    `<option value="${esc(v)}"${v === selected ? " selected" : ""}>${esc(t)}</option>`).join("");
}

function emptyRow(cols, text) {
  return `<tr><td colspan="${cols}" class="py-5 text-center text-slate-400 italic">${esc(text)}</td></tr>`;
}

let toastTimer;
function showToast(msg, isError = false) {
  const toast = byId("toast");
  byId("toastMsg").textContent = msg;
  byId("toastIcon").className = isError
    ? "fa-solid fa-triangle-exclamation text-red-400 text-xs"
    : "fa-solid fa-check text-blue-400 text-xs";
  toast.classList.remove("translate-y-24", "opacity-0");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.add("translate-y-24", "opacity-0"), isError ? 6000 : 2800);
}


// ---------------------------------------------------------------- API calls
let busy = 0;
const latestCall = {};

function setBusy(delta) {
  busy += delta;
  byId("mainContent").classList.toggle("is-busy", busy > 0);
}

function postJson(payload) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) };
}

function postFile(file) {
  const form = new FormData();
  form.append("cv_file", file);
  return { method: "POST", body: form };
}

// Calls the API. Returns the JSON answer, or null when the call failed (a message is shown) or when a newer call
// with the same key was made meanwhile (so a slow, outdated answer never overwrites a newer one).
async function call(key, path, options) {
  const id = (latestCall[key] = (latestCall[key] || 0) + 1);
  setBusy(+1);
  try {
    const resp = await fetch(path, options);
    let body = null;
    try { body = await resp.json(); } catch (e) { /* not JSON */ }
    if (!resp.ok) throw new Error((body && body.error) || `The server answered ${resp.status}.`);
    return id === latestCall[key] ? body : null;
  } catch (err) {
    if (id === latestCall[key]) {
      showToast(err instanceof TypeError ? "Could not reach the server. Is flask_app.py running?" : err.message, true);
    }
    return null;
  } finally {
    setBusy(-1);
  }
}


// ---------------------------------------------------------------- charts
function plot(id, traces, layout) {
  state.charts[id] = { traces, layout };
  const el = byId(id);
  if (el.offsetParent !== null) Plotly.react(el, traces, layout, PLOT_CONFIG);
}

// Plotly cannot size a chart inside a hidden tab, so charts are (re)drawn when their tab is shown.
function redrawVisible() {
  for (const [id, c] of Object.entries(state.charts)) {
    const el = byId(id);
    if (el.offsetParent !== null) Plotly.react(el, c.traces, c.layout, PLOT_CONFIG).then(() => Plotly.Plots.resize(el));
  }
}

function baseLayout(extra) {
  return {
    margin: { l: 50, r: 20, t: 10, b: 40 },
    paper_bgcolor: "#ffffff", plot_bgcolor: "#ffffff",
    font: { family: "Inter, sans-serif", size: 11, color: "#334155" },
    xaxis: { gridcolor: "#f8fafc" },
    legend: { orientation: "h", y: -0.18 },
    hovermode: "x unified",
    ...extra,
  };
}


// ---------------------------------------------------------------- start
async function init() {
  restoreSidebar();
  const m = await call("meta", "/api/meta");
  if (!m) return;
  state.meta = m;
  state.skillName = Object.fromEntries(m.skills.map(s => [s.id, s.name]));
  state.cutoffIndex = m.cutoff_options.length - 1;
  state.sdg = [...m.sdg_default];
  state.sdgWeight = m.sdg_weight_default;
  initControls();
  updateCutoffLabels();
  refreshRadar();
  refreshAbout();
  await handleSampleCvChange(m.sample_cvs[0].id);
}

function initControls() {
  const m = state.meta;
  const slider = byId("cutoffSlider");
  slider.max = m.cutoff_options.length - 1;
  slider.value = state.cutoffIndex;
  byId("cutoffMinLabel").textContent = m.cutoff_options[0];
  byId("cutoffMaxLabel").textContent = m.latest;
  byId("sidebarSourceCaption").textContent = m.source_note;
  const weight = byId("sdgWeightSlider");
  weight.max = m.sdg_weight_max;
  weight.value = state.sdgWeight;
  byId("sdgWeightLabel").textContent = state.sdgWeight.toFixed(2);
  fillSelect(byId("sampleCvSelect"), m.sample_cvs.map(c => [c.id, c.label]));
  fillSelect(byId("exploreSkillSelect"), m.skills.map(s => [s.id, s.name]));
  fillSelect(byId("teamRoleSelect"), m.team_roles.map(r => [r.id, r.name]));
  byId("privacyNote").textContent = m.privacy_note;
  byId("currentCaption").textContent = m.current_caption;
  byId("moveCaption").textContent = m.move_caption;
  renderSdgControls();
  renderSkillPills();
  updateTeamCaption();
}


// ---------------------------------------------------------------- sidebar: time machine and SDG priorities
function updateCutoffLabels() {
  const c = cutoff();
  byId("cutoffSlider").value = state.cutoffIndex;
  for (const id of ["cutoffValueLabel", "tableCutoffLabel", "hrCutoffLabel"]) byId(id).textContent = c;
  byId("headerCutoffText").textContent = `Cutoff: ${c}`;
  byId("timeMachineAlert").classList.toggle("hidden", c === state.meta.latest);
  byId("timeMachineAlertText").textContent = `Time machine on: trends use data up to ${c} only.`;
}

const refreshForCutoff = debounce(() => {
  refreshRadar();
  refreshAnalyze();
  refreshAbout();
  if (state.view === "hr") refreshTeam();
}, 250);

function handleCutoffChange(idx) {
  state.cutoffIndex = Number(idx);
  updateCutoffLabels();
  refreshForCutoff();
}

const refreshAnalyzeSoon = debounce(() => refreshAnalyze(), 250);

function handleSdgWeightChange(val) {
  state.sdgWeight = Number(val);
  byId("sdgWeightLabel").textContent = state.sdgWeight.toFixed(2);
  refreshAnalyzeSoon();
}

function renderSdgControls() {
  const goals = state.meta.sdg_goals;
  const chosen = goals.filter(g => state.sdg.includes(g.goal));
  byId("selectedSdgPills").innerHTML = chosen.length ? chosen.map(g => `
    <span class="sdg-pill" title="SDG ${g.goal}: ${esc(g.name)}">
      <span class="w-2 h-2 rounded-sm inline-block" style="background:${esc(g.colour)}"></span>
      <span>SDG ${g.goal}: ${esc(short(g.name, 20))}</span>
      <button type="button" data-action="remove-sdg" data-value="${g.goal}" class="text-slate-400 hover:text-slate-800 ml-1" title="Remove SDG ${g.goal}"><i class="fa-solid fa-xmark"></i></button>
    </span>`).join("")
    : '<span class="text-[11px] text-slate-400 italic py-0.5">None selected (skills match only)</span>';
  byId("sdgAddSelect").innerHTML = '<option value="">+ Add UN SDG Goal...</option>' + goals
    .filter(g => !state.sdg.includes(g.goal))
    .map(g => `<option value="${g.goal}">SDG ${g.goal}: ${esc(g.name)}</option>`).join("");
}

function addSdgPriority(goal) {
  const g = Number(goal);
  if (!g || state.sdg.includes(g)) return;
  state.sdg.push(g);
  state.sdg.sort((a, b) => a - b);
  renderSdgControls();
  refreshAnalyze();
}

function removeSdgPriority(goal) {
  state.sdg = state.sdg.filter(x => x !== Number(goal));
  renderSdgControls();
  refreshAnalyze();
}

function clearAllSdgs() {
  state.sdg = [];
  renderSdgControls();
  refreshAnalyze();
}

// Large screens: a column that can be collapsed (remembered in this browser). Small screens: a drawer over the page.
const DESKTOP = window.matchMedia("(min-width: 1024px)");
const SIDEBAR_KEY = "jobridge-sidebar-collapsed";

function toggleSidebar() {
  if (DESKTOP.matches) {
    const collapsed = document.body.classList.toggle("sidebar-collapsed");
    try { localStorage.setItem(SIDEBAR_KEY, collapsed ? "1" : "0"); } catch (e) { /* storage blocked */ }
  } else {
    document.body.classList.toggle("sidebar-open");
  }
  updateSidebarToggle();
  requestAnimationFrame(redrawVisible);   // charts take the freed width
}

function updateSidebarToggle() {
  const shown = DESKTOP.matches ? !document.body.classList.contains("sidebar-collapsed")
    : document.body.classList.contains("sidebar-open");
  byId("sidebarToggle").setAttribute("aria-expanded", String(shown));
}

function restoreSidebar() {
  try {
    if (localStorage.getItem(SIDEBAR_KEY) === "1") document.body.classList.add("sidebar-collapsed");
  } catch (e) { /* storage blocked */ }
  DESKTOP.addEventListener("change", () => {
    document.body.classList.remove("sidebar-open");
    updateSidebarToggle();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape" && document.body.classList.contains("sidebar-open")) toggleSidebar();
  });
  updateSidebarToggle();
}


// ---------------------------------------------------------------- tab 1: profile
function switchProfileMode(mode) {
  state.mode = mode;
  for (const m of ["sample", "upload", "paste", "list"]) {
    const name = m.charAt(0).toUpperCase() + m.slice(1);
    byId(`mode${name}Box`).classList.toggle("hidden", m !== mode);
    byId(`lblMode${name}`).className = m === mode ? MODE_ON : MODE_OFF;
  }
  if (mode === "sample" && state.sample) handleSampleCvChange(state.sample);
}

// Sends a CV (text or file) to the server and makes the skills it finds the profile.
async function extractCv(options) {
  const d = await call("extract", "/api/extract", options);
  if (!d) return null;
  state.skills = Object.fromEntries(d.skills.map(s => [s.id, s.evidence]));
  state.done.clear();
  skillsChanged();
  return d;
}

async function handleSampleCvChange(id) {
  const cv = state.meta.sample_cvs.find(c => c.id === id) || state.meta.sample_cvs[0];
  state.sample = cv.id;
  byId("sampleCvSelect").value = cv.id;
  byId("sampleCvRawText").textContent = cv.text;
  await extractCv(postJson({ text: cv.text, source: cv.id }));
}

async function handleCvUpload(e) {
  const file = e.target.files[0];
  e.target.value = "";   // choosing the same file again still triggers a change
  if (!file) return;
  const lbl = byId("fileStatusLabel");
  lbl.textContent = `Reading ${file.name}...`;
  lbl.classList.remove("hidden");
  const d = await extractCv(postFile(file));
  lbl.textContent = d ? `Using ${file.name}: ${d.skills.length} skills recognised` : `Could not use ${file.name}`;
  if (d) showToast(`Extracted ${d.skills.length} skills from ${file.name}`);
}

async function submitPastedCv() {
  const text = byId("rawResumeInput").value.trim();
  if (!text) {
    showToast("Please paste CV text first", true);
    return;
  }
  const d = await extractCv(postJson({ text }));
  if (d) showToast(`Extracted ${d.skills.length} skills`);
}

function addSkillFromList(id) {
  if (!id || id in state.skills) return;
  state.skills[id] = "added by you";
  skillsChanged();
  showToast(`Added ${skillName(id)}`);
}

function removeUserSkill(id) {
  delete state.skills[id];
  skillsChanged();
}

function clearAllSkills() {
  state.skills = {};
  skillsChanged();
}

function skillsChanged() {
  renderSkillPills();
  refreshAnalyze();
  if (state.view === "hr") refreshTeam();
}

function renderSkillPills() {
  const ids = Object.keys(state.skills).sort((a, b) => skillName(a).localeCompare(skillName(b)));
  byId("skillCountBadge").textContent = `${ids.length} skill${ids.length === 1 ? "" : "s"}`;
  byId("sidebarSkillCount").textContent = ids.length;
  byId("extractedSkillsContainer").innerHTML = ids.length ? ids.map(id => `
    <span class="skill-pill">
      <span>${esc(skillName(id))}</span>
      <button type="button" data-action="remove-skill" data-value="${esc(id)}" title="Remove ${esc(skillName(id))}"><i class="fa-solid fa-xmark"></i></button>
    </span>`).join("")
    : '<span class="text-xs text-slate-400 italic py-1">No skills selected. Choose a sample CV or pick skills from the dictionary dropdown.</span>';
  byId("addSkillDropdown").innerHTML = '<option value="">+ Add a skill from the dictionary...</option>' + state.meta.skills
    .filter(s => !(s.id in state.skills))
    .map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("");
}

function renderProfileTable(rows) {
  byId("profileSkillsTableBody").innerHTML = rows.length ? rows.map(r => `
    <tr class="hover:bg-slate-50">
      <td class="py-2 px-4 font-medium text-slate-900">${esc(r.name)}</td>
      <td class="py-2 px-4 font-mono text-slate-600">${esc(r.evidence)}</td>
      <td class="py-2 px-4">${trendBadge(r.trend)}</td>
    </tr>`).join("") : emptyRow(3, "No skills in profile.");
}


// ---------------------------------------------------------------- tabs 1, 3 and 4: /api/analyze
async function refreshAnalyze() {
  const d = await call("analyze", "/api/analyze", postJson({
    cutoff: cutoff(), skills: state.skills, sdg: state.sdg, sdg_weight: state.sdgWeight, path_role: state.pathRole,
  }));
  if (!d) return;
  state.analysis = d;
  renderProfileTable(d.profile);
  renderOptions(d);
  renderPathway(d.pathway);
}


// ---------------------------------------------------------------- tab 2: Future Skills Radar
async function refreshRadar() {
  const d = await call("radar", `/api/radar?cutoff=${encodeURIComponent(cutoff())}`);
  if (!d) return;
  byId("metricAiNow").textContent = d.metrics.now;
  byId("metricAiModerate").textContent = d.metrics.moderate;
  byId("metricAiFast").textContent = d.metrics.fast;
  byId("sidebarModelName").textContent = d.model;
  byId("aiChartCaption").textContent = d.source_caption;
  byId("trendCaption").textContent = d.trend_caption;

  plot("aiAdoptionChart", [
    { x: d.ai.months, y: d.ai.observed, name: "Observed (3 month average)", mode: "lines",
      line: { color: C_OBSERVED, width: 2.2 }, hovertemplate: PCT_HOVER },
    { x: d.ai.future_months, y: d.ai.moderate, name: "Moderate AI scenario (estimate)", mode: "lines",
      line: { color: C_MODERATE, width: 2.2, dash: "dash" }, hovertemplate: PCT_HOVER },
    { x: d.ai.future_months, y: d.ai.fast, name: "Fast AI scenario (estimate)", mode: "lines",
      line: { color: C_FAST, width: 2.2, dash: "dot" }, hovertemplate: PCT_HOVER },
  ], baseLayout({ yaxis: { tickformat: ".0%", gridcolor: "#f1f5f9", zeroline: false } }));

  for (const [label, rows, colour] of [["rising", d.rising, "text-emerald-700"], ["declining", d.declining, "text-red-700"]]) {
    byId(`${label}CountLabel`).textContent = `(${rows.length} skill${rows.length === 1 ? "" : "s"})`;
    byId(`${label}TableBody`).innerHTML = rows.length ? rows.map(r => `
      <tr class="hover:bg-slate-50 cursor-pointer" data-action="explore" data-value="${esc(r.id)}" title="Show ${esc(r.name)} below">
        <td class="py-2 px-3 font-medium text-slate-800">${esc(r.name)}</td>
        <td class="py-2 px-3 font-mono text-slate-600">${esc(r.now)}</td>
        <td class="py-2 px-3 font-mono font-semibold ${colour}">${esc(r.future)}</td>
      </tr>`).join("") : emptyRow(3, `No ${label} skills at this cutoff.`);
  }

  state.defaultSkill = d.default_skill;
  refreshSkill();
}

async function refreshSkill() {
  const skill = state.exploreSkill || state.defaultSkill;
  const d = await call("skill", `/api/skill?cutoff=${encodeURIComponent(cutoff())}&skill=${encodeURIComponent(skill || "")}`);
  if (!d) return;
  byId("exploreSkillSelect").value = d.skill;
  plot("singleSkillChart", [
    { x: d.months, y: d.observed, name: "Observed (3 month average)", mode: "lines",
      line: { color: C_OBSERVED, width: 2.2 }, hovertemplate: PCT_HOVER },
    { x: d.forecast_months, y: d.moderate, name: "Moderate AI scenario (estimate)", mode: "lines+markers",
      line: { color: C_MODERATE, width: 2.2, dash: "dash" }, hovertemplate: PCT_HOVER },
    { x: d.forecast_months, y: d.fast, name: "Fast AI scenario (estimate)", mode: "lines+markers",
      line: { color: C_FAST, width: 2.2, dash: "dot" }, hovertemplate: PCT_HOVER },
  ], baseLayout({
    title: { text: d.title, font: { size: 13, family: "Plus Jakarta Sans", color: "#0f172a" }, x: 0 },
    margin: { l: 50, r: 20, t: 36, b: 40 },
    yaxis: { tickformat: ".1%", gridcolor: "#f1f5f9", zeroline: false },
    legend: { orientation: "h", y: -0.2 },
  }));
  byId("singleSkillCaption").textContent = d.caption;
}

function handleExploreSkillChange(id) {
  state.exploreSkill = id;
  refreshSkill();
}


// ---------------------------------------------------------------- tab 3: your options
function renderOptions(d) {
  const has = Boolean(d.current);
  byId("optionsEmpty").classList.toggle("hidden", has);
  byId("optionsContent").classList.toggle("hidden", !has);
  byId("sidebarCurrentRole").textContent = has ? d.current.role : "–";
  if (!has) return;
  byId("currentRoleContainer").innerHTML = roleCard(d.current);
  byId("upgradeRolesContainer").innerHTML = d.upgrades.length ? d.upgrades.map(r => roleCard(r)).join("")
    : '<p class="text-xs text-slate-500 italic">No upgrade role in our list for your current field yet.</p>';
  byId("moveRolesContainer").innerHTML = d.moves.length ? d.moves.map(r => roleCard(r)).join("")
    : '<p class="text-xs text-slate-500 italic">No role passes the recommendation rule at this cutoff.</p>';
  byId("otherRolesSummaryTitle").textContent = `Other roles we checked but do not recommend (${d.others.length})`;
  byId("otherRolesTableBody").innerHTML = d.others.length ? d.others.map(o => `
    <tr>
      <td class="py-2 px-3 font-medium text-slate-800">${esc(o.role)}</td>
      <td class="py-2 px-3 font-mono">${esc(o.match)}</td>
      <td class="py-2 px-3">${esc(o.ilo_gradient)}</td>
      <td class="py-2 px-3 font-mono">${esc(o.transferability)}</td>
      <td class="py-2 px-3 font-mono">${esc(o.posts)}</td>
      <td class="py-2 px-3 text-slate-600">${esc(o.why)}</td>
    </tr>`).join("") : emptyRow(6, "Every role we checked is recommended.");
}

function roleCard(r) {
  const exposure = r.exposure ? `
    <div class="text-xs text-slate-700 bg-slate-50 border border-slate-200 px-3 py-2 rounded">
      <strong>Exposure change:</strong> ${esc(r.exposure.from)} &rarr; <span class="text-blue-700 font-semibold">${esc(r.exposure.to)}</span>
      (ILO score ${esc(r.exposure.from_score)} &rarr; ${esc(r.exposure.to_score)}, ${esc(r.exposure.verdict)})
    </div>` : "";
  const limited = r.limited ? `
    <div class="p-2.5 rounded bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2">
      <i class="fa-solid fa-triangle-exclamation text-amber-700 mt-0.5 text-[11px]"></i><span>${esc(r.limited)}</span>
    </div>` : "";
  const gaps = r.gaps.length ? r.gaps.map(g => `${esc(g.name)} (${trendInfo(g.trend).text})`).join(", ") : "none";
  const sdg = r.sdg ? `
    <div class="text-[11px] text-slate-500">
      SDG fit for your priorities: <strong>${esc(r.sdg.fit)}</strong>.
      Ranking with SDG preference: <strong class="text-blue-700">${esc(r.sdg.ranking)}</strong>
      (skills match alone: ${esc(r.sdg.match)}).
    </div>` : "";
  const rows = r.explain.map(e => `
    <tr class="border-b border-slate-100">
      <td class="py-1.5 px-3 font-medium text-slate-800">${esc(e.skill)}</td>
      <td class="py-1.5 px-3">
        <div class="flex items-center gap-2">
          <div class="w-16 h-1.5 bg-slate-200 rounded-sm overflow-hidden">
            <div class="h-full bg-blue-600" style="width: ${Math.min(Math.max(e.share, 0), 1) * 100}%"></div>
          </div>
          <span class="font-mono text-[11px]">${(e.share * 100).toFixed(1)}%</span>
        </div>
      </td>
      <td class="py-1.5 px-3 font-mono">${e.future_factor.toFixed(2)}</td>
      <td class="py-1.5 px-3">${trendBadge(e.trend)}</td>
      <td class="py-1.5 px-3">${e.in_profile ? '<span class="text-blue-700 font-semibold">Yes</span>' : '<span class="text-slate-400">No</span>'}</td>
      <td class="py-1.5 px-3 font-mono text-slate-500">${esc(e.evidence || "—")}</td>
      <td class="py-1.5 px-3 font-mono font-semibold">${e.importance.toFixed(3)}</td>
    </tr>`).join("");
  const tile = (label, value, extra = "", title = "") => `
    <div class="p-3 rounded bg-slate-50 border border-slate-200/80">
      <div class="text-[11px] text-slate-500"${title ? ` title="${esc(title)}"` : ""}>${label}</div>
      <div class="text-base font-display font-bold ${extra || "text-slate-900"} mt-0.5">${esc(value)}</div>
    </div>`;

  return `
    <div class="surface-card p-5 space-y-3.5">
      <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h4 class="font-display font-bold text-base text-slate-900">${esc(r.role)}</h4>
            <span class="text-[11px] font-medium px-2 py-0.5 rounded border ${BADGE_CLS[r.group] || BADGE_CLS.other}">${esc(r.badge)}</span>
          </div>
          <p class="text-xs text-slate-500 mt-1">${esc(r.description)}</p>
        </div>
        ${r.group !== "now" ? `
          <button type="button" data-action="plan-role" data-value="${esc(r.role_id)}" class="btn-primary px-3.5 py-1.5 text-xs font-semibold whitespace-nowrap flex items-center gap-1.5 self-start">
            <span>Plan pathway</span>
            <i class="fa-solid fa-arrow-right text-[10px]"></i>
          </button>` : ""}
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        ${tile("Skills match", r.match, "", "Range across the moderate and fast AI scenarios. Estimate.")}
        ${tile("GenAI exposure (ILO)", r.ilo_gradient, r.exposure_rank <= 3 ? "text-blue-700" : "text-amber-700", r.ilo_note)}
        ${tile("Builds on admin & finance", r.transferability, "", "Transferability: share of this role's skill demand that admin, finance, payroll and contact centre roles also use.")}
        ${tile("Job posts analysed", r.posts, "", "Hacker News and LinkedIn posts with this job title")}
      </div>

      ${exposure}
      ${limited}

      <div class="text-xs text-slate-700">
        <strong>Top skills to add:</strong> <span class="text-slate-600">${gaps}</span>
      </div>

      ${sdg}

      <details class="group bg-slate-50 rounded border border-slate-200 overflow-hidden">
        <summary class="cursor-pointer px-3.5 py-2 text-xs font-medium text-slate-700 flex items-center justify-between select-none hover:bg-slate-100">
          <span class="flex items-center gap-2">
            <i class="fa-solid fa-chevron-right text-[10px] text-slate-400 group-open:rotate-90 transition-transform"></i>
            <span>Why this score?</span>
          </span>
          <span class="text-[11px] font-mono text-slate-400">Importance = Share × Future Factor</span>
        </summary>
        <div class="p-3 bg-white border-t border-slate-200 space-y-2 overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-slate-50 text-slate-600 border-b border-slate-200">
              <tr>
                <th class="py-1.5 px-3">Skill</th>
                <th class="py-1.5 px-3">Share of job posts</th>
                <th class="py-1.5 px-3">Future factor</th>
                <th class="py-1.5 px-3">Market trend</th>
                <th class="py-1.5 px-3">In your profile</th>
                <th class="py-1.5 px-3">Evidence</th>
                <th class="py-1.5 px-3">Importance</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
          <p class="text-[11px] text-slate-500 pt-1">
            Match = importance of the skills you have ÷ importance of all skills in the role profile. Importance = share of job posts that ask for the skill × its future factor (forecast ÷ today; only clearly rising or declining skills move).
          </p>
        </div>
      </details>
    </div>`;
}


// ---------------------------------------------------------------- tab 4: your pathway
function selectRoleForPathway(roleId) {
  state.pathRole = roleId;
  state.done.clear();
  refreshAnalyze();
  goToTab("tab-pathway");
}

function handlePathwayRoleSelect(roleId) {
  state.pathRole = roleId;
  state.done.clear();
  refreshAnalyze();
}

function toggleStepDone(skillId) {
  if (state.done.has(skillId)) {
    state.done.delete(skillId);
  } else {
    state.done.add(skillId);
    showToast("Step marked as done");
  }
  renderPathway(state.analysis && state.analysis.pathway);
}

function renderPathway(p) {
  byId("pathwayEmpty").classList.toggle("hidden", Boolean(p));
  byId("pathwayContent").classList.toggle("hidden", !p);
  byId("pathwayRoleBox").classList.toggle("hidden", !p);
  if (!p) return;
  fillSelect(byId("pathwayRoleSelect"), p.options.map(o => [o.id, o.label]), p.role_id);
  byId("pathMetricNow").textContent = p.match_now;
  byId("pathMetricAfter").textContent = p.match_after;
  byId("pathMetricHours").textContent = p.hours;
  byId("pathMetricHoursSub").textContent = p.hours_note;
  byId("pathMetricExposure").textContent = p.exposure;
  byId("pathMetricExposureSub").textContent = p.exposure_from;
  byId("pathMetricExposureSub").title = p.exposure_note;
  byId("pathwayStepsCountBadge").textContent = `${p.steps.length} step${p.steps.length === 1 ? "" : "s"}`;
  byId("courseCaption").textContent = p.course_caption;

  byId("pathwayStepsContainer").innerHTML = p.steps.length ? p.steps.map(s => {
    if (!s.url) {
      return `
        <div class="p-4 rounded-md border bg-white border-slate-200 text-xs text-slate-700">
          <span class="font-mono font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200 mr-2">Step ${s.i}</span>
          <strong>${esc(s.skill)}</strong>: no free course in our catalogue yet. We do not suggest courses we have not checked.
        </div>`;
    }
    const isDone = state.done.has(s.skill_id);
    const more = s.more.length ? `
      <details class="group mt-2">
        <summary class="cursor-pointer text-[11px] font-medium text-slate-600 hover:text-blue-700 select-none">
          <i class="fa-solid fa-chevron-right text-[9px] text-slate-400 group-open:rotate-90 transition-transform"></i>
          More courses for ${esc(s.skill)} (${s.more.length})
        </summary>
        <ul class="mt-1.5 space-y-1 pl-4 list-disc text-[11px] text-slate-600">
          ${s.more.map(e => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener" class="text-blue-700 hover:underline">${esc(e.course)}</a>, ${esc(e.provider)}, ${esc(e.level)}, ${esc(e.hours)}, ${esc(e.cost)}</li>`).join("")}
        </ul>
      </details>` : "";
    return `
      <div class="p-4 rounded-md border ${isDone ? "bg-blue-50/50 border-blue-300" : "bg-white border-slate-200"}">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2">
              <span class="font-mono font-semibold text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">Step ${s.i}</span>
              <span class="font-bold text-sm text-slate-900">${esc(s.skill)}</span>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-slate-50 border border-slate-200 text-slate-600">${esc(s.level)}</span>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium">${esc(s.cost)}</span>
            </div>
            <div class="text-xs text-slate-700 pt-0.5">
              <span class="font-semibold text-slate-900">${esc(s.course)}</span>
              • <span>${esc(s.provider)}</span> • <span class="font-mono">${esc(s.hours)}</span>
            </div>
            <div class="text-[11px] text-slate-500">Covers: ${esc(s.covers)}. Page checked on ${esc(s.checked_on)}.</div>
          </div>
          <div class="flex flex-col gap-2 w-full sm:w-36 flex-shrink-0">
            <a href="${esc(s.url)}" target="_blank" rel="noopener" title="Open ${esc(s.course)} (${esc(s.provider)}) in a new tab"
               class="btn-primary px-3 py-1.5 text-xs font-semibold flex items-center justify-center gap-1.5">
              <span>Go to course</span>
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
            </a>
            <button type="button" data-action="step-done" data-value="${esc(s.skill_id)}" class="px-3 py-1.5 rounded border text-xs font-semibold flex items-center justify-center gap-1.5 ${isDone ? "bg-emerald-700 border-emerald-700 text-white" : "bg-white border-slate-300 text-slate-700 hover:bg-slate-50"}">
              <i class="fa-solid fa-check text-[10px]"></i>
              <span>${isDone ? "Completed" : "Mark done"}</span>
            </button>
          </div>
        </div>
        ${more}
      </div>`;
  }).join("") : `
    <div class="p-5 rounded bg-blue-50 border border-blue-200 text-center space-y-1">
      <h4 class="font-display font-bold text-sm text-blue-900">All core competencies covered for ${esc(p.role)}</h4>
      <p class="text-xs text-blue-700">Your current skill set already covers the skills this role's job posts ask for.</p>
    </div>`;

  byId("pathwaySdgLinksContainer").innerHTML = p.sdg.length ? p.sdg.map(goal => `
    <div class="p-3.5 rounded bg-slate-50 border border-slate-200 space-y-1.5">
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-sm inline-block" style="background:${esc(goal.colour)}"></span>
        <span class="font-display font-bold text-xs text-slate-900">${esc(goal.title)}</span>
      </div>
      ${goal.links.map(l => `
        <p class="text-xs text-slate-600 pl-5">Target ${esc(l.target)} (${esc(l.strength)}): <strong>${esc(l.name)}</strong>. ${esc(l.rationale)}</p>`).join("")}
    </div>`).join("")
    : '<p class="text-xs text-slate-500 italic">No specific SDG target is linked to this role and these skills yet.</p>';
}


// ---------------------------------------------------------------- about
async function refreshAbout() {
  const d = await call("about", `/api/about?cutoff=${encodeURIComponent(cutoff())}`);
  if (!d) return;
  // how, model_reason, checks and disclosure are HTML built by flask_app.md() from the server's own text (escaped there)
  byId("aboutHow").innerHTML = d.how;
  byId("modelReason").innerHTML = d.model_reason;
  byId("aboutChecks").innerHTML = d.checks;
  byId("aboutDisclosure").innerHTML = d.disclosure;
  byId("modelChartSubtitle").textContent =
    `Average forecast error at ${d.model.horizon} months, percentage points (lower is better). Blue = model used (${d.model.chosen}).`;
  plot("modelBacktestChart", [{
    type: "bar", orientation: "h", x: d.model.mae, y: d.model.models,
    marker: { color: d.model.models.map(m => (m === d.model.chosen ? C_OBSERVED : C_MUTED)) },
    text: d.model.mae.map(v => v.toFixed(3) + " pp"), textposition: "outside",
    hovertemplate: "%{y}: %{x:.3f} pp<extra></extra>",
  }], baseLayout({
    margin: { l: 120, r: 60, t: 10, b: 40 },
    hovermode: "closest", showlegend: false,
    yaxis: { autorange: "reversed" },
    xaxis: { title: { text: "Mean absolute error (percentage points)" }, gridcolor: "#f1f5f9" },
  }));

  const box = byId("fairnessBox");
  box.classList.toggle("hidden", !d.fairness);
  if (d.fairness) {
    box.className = `p-4 rounded-md border text-xs flex items-center gap-3 ${d.fairness.ok
      ? "bg-emerald-50 border-emerald-200 text-emerald-950" : "bg-red-50 border-red-200 text-red-950"}`;
    box.innerHTML = `<i class="fa-solid ${d.fairness.ok ? "fa-check-circle text-emerald-700" : "fa-circle-xmark text-red-700"} text-base"></i>
      <div>${esc(d.fairness.text)}</div>`;
  }

  byId("rolesTableBody").innerHTML = d.roles.map(r => `
    <tr>
      <td class="py-2 px-3 font-medium text-slate-800">${esc(r.role)}</td>
      <td class="py-2 px-3">${esc(r.type)}</td>
      <td class="py-2 px-3 font-mono">${esc(r.isco)}</td>
      <td class="py-2 px-3">${esc(r.ilo_gradient)}</td>
      <td class="py-2 px-3 font-mono">${esc(r.ilo_score)}</td>
      <td class="py-2 px-3 font-mono">${esc(r.posts)}</td>
      <td class="py-2 px-3 font-mono">${esc(r.transferability)}</td>
      <td class="py-2 px-3">${r.recommended ? '<span class="text-blue-700 font-semibold">✓</span>' : '<span class="text-slate-400">✗</span>'}</td>
      <td class="py-2 px-3 text-slate-600">${esc(r.why)}</td>
    </tr>`).join("");
  byId("rolesCaption").textContent = d.roles_caption;
  byId("sourcesTableBody").innerHTML = d.sources.map(s => `
    <tr>
      <td class="py-2 px-3 font-medium text-slate-800">${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener" class="text-blue-700 hover:underline">${esc(s.name)}</a>` : esc(s.name)}</td>
      <td class="py-2 px-3">${esc(s.publisher)}</td>
      <td class="py-2 px-3">${esc(s.type)}</td>
      <td class="py-2 px-3 text-slate-600">${esc(s.used_for)}</td>
    </tr>`).join("");
  byId("sourcesCaption").textContent = d.sources_caption;
}


// ---------------------------------------------------------------- team view (HR)
function switchTeamSource(source) {
  state.team.source = source;
  byId("teamUploadBox").classList.toggle("hidden", source !== "upload");
  byId("lblTeamSample").className = source === "sample" ? MODE_ON : MODE_OFF;
  byId("lblTeamUpload").className = source === "upload" ? MODE_ON : MODE_OFF;
  updateTeamCaption();
  refreshTeam();
}

function updateTeamCaption() {
  byId("teamCaption").textContent = state.team.source === "sample"
    ? "The synthetic sample CVs and your active profile treated as one team. See which skills most people would need for a role."
    : "Your team's CVs, read in memory on the server and not stored. See which skills most people would need for a role.";
}

function teamMembers() {
  if (state.team.source === "upload") return state.team.uploaded.map(m => ({ name: m.name, skills: m.skills }));
  const you = Object.keys(state.skills).length ? [{ name: "You (active profile)", skills: Object.keys(state.skills) }] : [];
  return [...you, ...state.meta.team_sample];
}

async function handleTeamUpload(e) {
  const files = [...e.target.files];
  e.target.value = "";
  for (const file of files) {
    const d = await call(`team-${file.name}`, "/api/extract", postFile(file));
    if (!d) continue;
    const others = state.team.uploaded.filter(m => m.file !== file.name);   // same file name replaces
    const name = others.some(m => m.name === d.label) ? `${d.label} (${file.name})` : d.label;
    state.team.uploaded = [...others, { file: file.name, name, skills: d.skills.map(s => s.id) }];
  }
  refreshTeam();
}

function removeTeamMember(file) {
  state.team.uploaded = state.team.uploaded.filter(m => m.file !== file);
  refreshTeam();
}

function renderTeamChips() {
  byId("teamMemberChips").innerHTML = state.team.uploaded.map(m => `
    <span class="skill-pill" title="${esc(m.file)}">
      <span>${esc(m.name)}</span>
      <button type="button" data-action="remove-member" data-value="${esc(m.file)}" title="Remove ${esc(m.file)}"><i class="fa-solid fa-xmark"></i></button>
    </span>`).join("");
}

async function refreshTeam() {
  renderTeamChips();
  const members = teamMembers();
  byId("teamEmpty").classList.toggle("hidden", members.length > 0);
  byId("teamResult").classList.toggle("hidden", members.length === 0);
  if (!members.length) {
    state.team.result = null;
    return;
  }
  const d = await call("team", "/api/team", postJson({ cutoff: cutoff(), role: byId("teamRoleSelect").value, members }));
  if (!d) return;
  state.team.result = d;
  byId("teamHeatmapTitle").textContent = d.title;
  const noProfile = d.skills.length === 0;
  byId("teamNoProfile").classList.toggle("hidden", !noProfile);
  byId("teamNoProfile").textContent = `${d.role_name} has no skill profile yet: only ${d.posts} job posts with this ` +
    "title were found, so team readiness cannot be measured. Choose another role.";
  byId("teamHeatmapChart").classList.toggle("hidden", noProfile);
  byId("teamMissingTableBody").innerHTML = emptyRow(3, "No skill profile for this role.");
  if (noProfile) return;
  const height = 120 + 40 * d.people.length;
  byId("teamHeatmapChart").style.height = `${height}px`;
  plot("teamHeatmapChart", [{
    type: "heatmap", z: d.grid, x: d.skills, y: d.people, zmin: 0, zmax: 1, showscale: false,
    colorscale: [[0, C_MISSING], [1, C_OBSERVED]], xgap: 3, ygap: 3,
    customdata: d.grid.map(row => row.map(v => (v ? "has this skill" : "missing"))),
    hovertemplate: "%{y}<br>%{x}: %{customdata}<extra></extra>",
  }], baseLayout({
    height, margin: { l: 10, r: 10, t: 10, b: 10 }, hovermode: "closest",
    xaxis: { tickangle: -30, automargin: true }, yaxis: { automargin: true, autorange: "reversed" },
  }));
  byId("teamMissingTableBody").innerHTML = d.missing.map(m => `
    <tr>
      <td class="py-2 px-4 font-medium text-slate-900">${esc(m.skill)}</td>
      <td class="py-2 px-4 font-mono font-semibold text-slate-800">${m.missing} / ${d.team_size}</td>
      <td class="py-2 px-4">${trendBadge(m.trend)}</td>
    </tr>`).join("");
}

function exportTeamCsv() {
  const d = state.team.result;
  if (!d) {
    showToast("Nothing to export yet", true);
    return;
  }
  const cell = v => (/[",\r\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
  const rows = [["Skill", "People missing it", "Team size", "Market trend", "Role", "Data up to"],
    ...d.missing.map(m => [m.skill, m.missing, d.team_size, m.trend, d.role_name, d.cutoff])];
  const blob = new Blob([rows.map(r => r.map(cell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `team_readiness_${d.role}_${d.cutoff}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  showToast("Exported team readiness CSV");
}


// ---------------------------------------------------------------- views and tabs
function switchRole(view) {
  state.view = view;
  byId("workerSection").classList.toggle("hidden", view !== "worker");
  byId("hrSection").classList.toggle("hidden", view !== "hr");
  byId("btnRoleWorker").className = view === "worker" ? VIEW_ON : VIEW_OFF;
  byId("btnRoleHR").className = view === "hr" ? VIEW_ON : VIEW_OFF;
  if (view === "hr") refreshTeam();
  requestAnimationFrame(redrawVisible);
}

function goToTab(tabId) {
  for (const t of TABS) {
    byId(t).classList.toggle("hidden", t !== tabId);
    byId(`nav-${t}`).classList.toggle("tab-active", t === tabId);
  }
  state.tab = tabId;
  requestAnimationFrame(redrawVisible);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Buttons drawn from API data carry data-action instead of inline handlers, so no data ends up inside JavaScript.
document.addEventListener("click", e => {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const value = el.dataset.value;
  switch (el.dataset.action) {
    case "remove-skill": removeUserSkill(value); break;
    case "remove-sdg": removeSdgPriority(value); break;
    case "plan-role": selectRoleForPathway(value); break;
    case "step-done": toggleStepDone(value); break;
    case "remove-member": removeTeamMember(value); break;
    case "explore":
      state.exploreSkill = value;
      refreshSkill();
      byId("singleSkillChart").scrollIntoView({ behavior: "smooth", block: "center" });
      break;
  }
});

init();
