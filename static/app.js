"use strict";

// ---- settings and state -------------------------------------------------------
const PAGE_SIZE = 20;
const MAX_COMPARE = 3;
const SORTS = ["title:asc", "pay:desc", "pay:asc", "growth:desc", "growth:asc"];
const CURRENCY_SYMBOL = { UK: "£", US: "$" };

// Everything the page shows is derived from this one object (and mirrored in the URL).
const state = {
  country: "UK", q: "", min_pay: "", education: "",
  sort: "title:asc", page: 1, compare: [], view: "search",
};

let latestRequest = 0; // used to ignore out-of-date responses
let educationLoaded = false;

const $ = (id) => document.getElementById(id);

// ---- small helpers ------------------------------------------------------------
// Builds an element. Text is added as text nodes (never as HTML), which keeps the page safe.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  node.append(...children.flat().filter((child) => child != null));
  return node;
}

function debounce(fn, ms = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function formatMoney(value, currency) {
  if (value == null) return "Not published";
  return new Intl.NumberFormat("en-GB", {
    style: "currency", currency, maximumFractionDigits: 0,
  }).format(value);
}

function formatGrowth(value) {
  if (value == null) return "n/a";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function formatJobs(value) {
  return value == null ? "n/a" : new Intl.NumberFormat("en-GB").format(value);
}

async function api(path, params = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== "" && value != null) query.set(key, value);
  }
  let response;
  try {
    response = await fetch(`${path}?${query}`);
  } catch {
    throw new Error("Can't reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const body = await response.json();
      message = typeof body.detail === "string" ? body.detail : "Please check your filters.";
    } catch { /* keep the generic message */ }
    throw new Error(message);
  }
  return response.json();
}

// ---- URL <-> state (so a search can be shared as a link) ----------------------------
function readUrl() {
  const params = new URLSearchParams(location.search);
  state.country = params.get("country") === "US" ? "US" : "UK";
  state.q = params.get("q") || "";
  state.min_pay = params.get("min_pay") || "";
  state.education = state.country === "US" ? params.get("education") || "" : "";
  state.sort = SORTS.includes(params.get("sort")) ? params.get("sort") : "title:asc";
  state.page = Math.max(1, parseInt(params.get("page"), 10) || 1);
  state.compare = (params.get("compare") || "")
    .split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0).slice(0, MAX_COMPARE);
  state.view = params.get("view") === "compare" ? "compare" : "search";
}

function writeUrl() {
  const params = new URLSearchParams();
  if (state.country !== "UK") params.set("country", state.country);
  if (state.q) params.set("q", state.q);
  if (state.min_pay) params.set("min_pay", state.min_pay);
  if (state.education) params.set("education", state.education);
  if (state.sort !== "title:asc") params.set("sort", state.sort);
  if (state.page > 1) params.set("page", state.page);
  if (state.compare.length) params.set("compare", state.compare.join(","));
  if (state.view === "compare") params.set("view", "compare");
  const text = params.toString();
  history.replaceState(null, "", text ? `?${text}` : location.pathname);
}

// ---- controls ----------------------------------------------------------------------
function syncControls() {
  $("q").value = state.q;
  $("min-pay").value = state.min_pay;
  $("sort").value = state.sort;
  $("education").value = state.education;
  $("min-pay-label").textContent = `Minimum annual pay (${CURRENCY_SYMBOL[state.country]})`;
  $("education-field").hidden = state.country !== "US"; // UK sources have no education data
  document.querySelectorAll(".country-toggle button").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.country === state.country));
  });
}

async function loadEducationLevels() {
  if (educationLoaded) return;
  try {
    const levels = await api("/education-levels");
    const select = $("education");
    levels.forEach((level) => select.append(el("option", { value: level }, level)));
    educationLoaded = true;
    select.value = state.education;
  } catch { /* the filter just stays on "Any" */ }
}

function updateCompareBar() {
  const count = state.compare.length;
  $("compare-bar").hidden = count === 0 || state.view === "compare";
  $("compare-count").textContent = count < 2
    ? `${count} selected (pick at least 2)`
    : `${count} selected`;
  $("compare-go").disabled = count < 2;
  document.querySelectorAll(".compare-pick input").forEach((box) => {
    box.disabled = !box.checked && count >= MAX_COMPARE; // cap at 3
  });
}

function toggleCompare(id, box) {
  if (box.checked && state.compare.length < MAX_COMPARE) state.compare.push(id);
  else state.compare = state.compare.filter((existing) => existing !== id);
  box.checked = state.compare.includes(id);
  writeUrl();
  updateCompareBar();
}

// ---- search view ---------------------------------------------------------------------
function statCell(label, value, className = "") {
  return el("div", {}, el("dt", {}, label), el("dd", { class: className }, value));
}

function card(item) {
  const box = el("input", {
    type: "checkbox", checked: state.compare.includes(item.id),
    onchange: () => toggleCompare(item.id, box),
  });
  const growthClass = item.growth_pct > 0 ? "growth-up" : item.growth_pct < 0 ? "growth-down" : "";
  const stats = [
    statCell("Median annual pay", formatMoney(item.median_pay, item.currency)),
    statCell("Projected growth, 2025–35", formatGrowth(item.growth_pct), growthClass),
    statCell("Jobs (2025)", formatJobs(item.employment)),
  ];
  if (item.education) stats.push(statCell("Typical entry education", item.education));

  return el("li", { class: "card" },
    el("div", { class: "card-top" },
      el("div", {}, el("h2", {}, item.title), el("span", { class: "code" }, `Code ${item.code}`)),
      el("label", { class: "compare-pick" }, box, "Compare"),
    ),
    el("dl", { class: "stats" }, ...stats),
  );
}

function renderPager(data) {
  const pages = Math.max(1, Math.ceil(data.total / data.page_size));
  const go = (page) => { state.page = page; refresh(); window.scrollTo({ top: 0 }); };
  $("pager").replaceChildren(
    ...(pages > 1 ? [
      el("button", { type: "button", disabled: state.page <= 1, onclick: () => go(state.page - 1) }, "Previous"),
      el("span", {}, `Page ${state.page} of ${pages}`),
      el("button", { type: "button", disabled: state.page >= pages, onclick: () => go(state.page + 1) }, "Next"),
    ] : []),
  );
}

function setStatus(text, isError = false) {
  const status = $("status");
  status.textContent = text;
  status.classList.toggle("error", isError);
}

async function runSearch() {
  const request = ++latestRequest;
  $("search-view").hidden = false;
  $("compare-view").hidden = true;
  setStatus("Loading…");
  const [sort, order] = state.sort.split(":");
  try {
    const data = await api("/occupations", {
      country: state.country, q: state.q, min_pay: state.min_pay, education: state.education,
      sort, order, page: state.page, page_size: PAGE_SIZE,
    });
    if (request !== latestRequest) return;
    const noun = data.total === 1 ? "career" : "careers";
    setStatus(data.total ? `${new Intl.NumberFormat("en-GB").format(data.total)} ${noun}` : "No careers match. Try a different search.");
    $("results").replaceChildren(...data.items.map(card));
    renderPager(data);
    updateCompareBar();
  } catch (error) {
    if (request !== latestRequest) return;
    setStatus(error.message, true);
    $("results").replaceChildren();
    $("pager").replaceChildren();
  }
}

// ---- compare view ----------------------------------------------------------------------
const COMPARE_ROWS = [
  { label: "Median annual pay", value: (i) => formatMoney(i.median_pay, i.currency), field: "median_pay" },
  { label: "Projected job growth, 2025–35", value: (i) => formatGrowth(i.growth_pct), field: "growth_pct" },
  { label: "Jobs (2025)", value: (i) => formatJobs(i.employment), field: "employment" },
  { label: "Typical entry education", value: (i) => i.education ?? "Not available" },
  { label: "Occupation code", value: (i) => i.code },
];

function compareTable(items) {
  const head = el("tr", {}, el("th", { scope: "col" }, el("span", { class: "sr-only" }, "Measure")),
    ...items.map((item) => el("th", { scope: "col" }, item.title)));

  const rows = COMPARE_ROWS.map((row) => {
    const numbers = row.field ? items.map((i) => i[row.field]).filter((n) => n != null) : [];
    const top = numbers.length > 1 ? Math.max(...numbers) : null; // highlight only when there is a real comparison
    return el("tr", {},
      el("th", { scope: "row" }, row.label),
      ...items.map((item) => {
        const isBest = top !== null && item[row.field] === top;
        return el("td", { class: isBest ? "best" : "" },
          row.value(item), isBest ? el("span", { class: "sr-only" }, " (highest)") : null);
      }),
    );
  });
  return el("table", {}, el("thead", {}, head), el("tbody", {}, ...rows));
}

async function runCompare() {
  const request = ++latestRequest;
  $("search-view").hidden = true;
  $("compare-view").hidden = false;
  $("compare-body").replaceChildren(el("p", { class: "status" }, "Loading…"));
  try {
    const items = await api("/compare", { ids: state.compare.join(",") });
    if (request !== latestRequest) return;
    $("compare-body").replaceChildren(compareTable(items));
  } catch (error) {
    if (request !== latestRequest) return;
    $("compare-body").replaceChildren(el("p", { class: "status error" }, error.message));
  }
}

// ---- wiring ---------------------------------------------------------------------------
function refresh() {
  if (state.view === "compare" && state.compare.length < 2) state.view = "search";
  writeUrl();
  syncControls();
  if (state.country === "US") loadEducationLevels();
  updateCompareBar();
  return state.view === "compare" ? runCompare() : runSearch();
}

function setupEvents() {
  document.querySelectorAll(".country-toggle button").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.country === state.country) return;
      Object.assign(state, {
        country: button.dataset.country, education: "", page: 1, compare: [], view: "search",
      });
      refresh(); // the two countries never mix, so selections are cleared
    });
  });

  const onFilterChange = debounce(() => {
    state.q = $("q").value.trim();
    state.min_pay = $("min-pay").value;
    state.page = 1;
    refresh();
  });
  $("q").addEventListener("input", onFilterChange);
  $("min-pay").addEventListener("input", onFilterChange);
  $("education").addEventListener("change", () => { state.education = $("education").value; state.page = 1; refresh(); });
  $("sort").addEventListener("change", () => { state.sort = $("sort").value; state.page = 1; refresh(); });
  $("filters").addEventListener("submit", (event) => event.preventDefault());

  $("compare-go").addEventListener("click", () => { state.view = "compare"; refresh(); window.scrollTo({ top: 0 }); });
  $("compare-clear").addEventListener("click", () => { state.compare = []; refresh(); });
  $("back").addEventListener("click", () => { state.view = "search"; refresh(); });
}

readUrl();
setupEvents();
refresh();
