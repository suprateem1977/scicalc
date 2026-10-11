// app.js - connects the buttons, the display and the history panel.
// If config.js has an API_URL, the maths and history go to AWS.
// Otherwise everything happens right here in the browser.

const API_URL = ((window.APP_CONFIG && window.APP_CONFIG.API_URL) || "").replace(/\/+$/, "");
const USE_API = API_URL !== "";

const exprEl = document.getElementById("expr");
const resultEl = document.getElementById("result");
const modeBtn = document.getElementById("modeBtn");
const historyList = document.getElementById("historyList");

let expression = "";
let mode = "deg";
let lastAnswer = null;
let justCalculated = false;

// ---------- a random id for this browser, so each visitor sees their own history ----------
function getUserId() {
  try {
    let id = localStorage.getItem("scicalc-user");
    if (!id) {
      id = "user-" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem("scicalc-user", id);
    }
    return id;
  } catch (e) {
    return "user-anonymous";
  }
}
const USER_ID = getUserId();

// ---------- display ----------
function pretty(text) {
  return text
    .replace(/\*/g, "×").replace(/\//g, "÷").replace(/-/g, "−")
    .replace(/sqrt\(/g, "√(").replace(/pi/g, "π")
    .replace(/asin\(/g, "sin⁻¹(").replace(/acos\(/g, "cos⁻¹(").replace(/atan\(/g, "tan⁻¹(");
}

function show(resultText, isError = false) {
  exprEl.textContent = expression ? pretty(expression) : " ";
  resultEl.textContent = resultText;
  resultEl.classList.toggle("error", isError);
}

function insert(text) {
  if (justCalculated) {
    // after "=": an operator continues from the answer, anything else starts fresh
    const ans = lastAnswer < 0 ? "(" + lastAnswer + ")" : String(lastAnswer);
    expression = /^[+\-*/^]/.test(text) ? ans : "";
    justCalculated = false;
  }
  expression += text;
  show(resultEl.classList.contains("error") ? "0" : resultEl.textContent);
}

// ---------- calculating ----------
async function calculate() {
  if (!expression) return;
  try {
    let result;
    if (USE_API) {
      show("…");
      const res = await fetch(API_URL + "/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expression, mode, user_id: USER_ID }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Server error");
      result = data.result;
    } else {
      result = window.Calculator.evaluate(expression, mode);
      saveLocalHistory({ expression, result, mode, created_at: new Date().toISOString() });
    }
    lastAnswer = result;
    justCalculated = true;
    show(String(result));
    loadHistory();
  } catch (err) {
    show(err.message, true);
  }
}

// ---------- history: in the browser (version 1) or in DynamoDB (version 2) ----------
function readLocalHistory() {
  try { return JSON.parse(localStorage.getItem("scicalc-history") || "[]"); } catch (e) { return []; }
}
function saveLocalHistory(item) {
  try {
    const items = [item, ...readLocalHistory()].slice(0, 20);
    localStorage.setItem("scicalc-history", JSON.stringify(items));
  } catch (e) { /* storage blocked: history just won't be kept */ }
}

async function loadHistory() {
  let items = [];
  try {
    if (USE_API) {
      const res = await fetch(API_URL + "/history?user_id=" + encodeURIComponent(USER_ID));
      items = (await res.json()).items || [];
    } else {
      items = readLocalHistory();
    }
  } catch (e) {
    historyList.innerHTML = '<li class="empty">Could not load history</li>';
    return;
  }
  historyList.innerHTML = "";
  if (items.length === 0) {
    historyList.innerHTML = '<li class="empty">No calculations yet</li>';
    return;
  }
  for (const item of items) {
    const li = document.createElement("li");
    li.innerHTML = '<span class="h-expr"></span><span class="h-result"></span>';
    li.querySelector(".h-expr").textContent = pretty(item.expression) + "  (" + item.mode + ")";
    li.querySelector(".h-result").textContent = "= " + item.result;
    li.title = "Click to reuse";
    li.addEventListener("click", () => { expression = item.expression; justCalculated = false; show(String(item.result)); });
    historyList.appendChild(li);
  }
}

async function clearHistory() {
  if (USE_API) {
    await fetch(API_URL + "/history?user_id=" + encodeURIComponent(USER_ID), { method: "DELETE" });
  } else {
    try { localStorage.removeItem("scicalc-history"); } catch (e) {}
  }
  loadHistory();
}

// ---------- buttons and keyboard ----------
function handleAction(action) {
  if (action === "clear") { expression = ""; justCalculated = false; show("0"); }
  if (action === "back") { expression = expression.slice(0, -1); show(resultEl.textContent); }
  if (action === "ans" && lastAnswer !== null) insert(String(lastAnswer));
  if (action === "equals") calculate();
}

document.querySelectorAll(".k").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.insert !== undefined) insert(btn.dataset.insert);
    else handleAction(btn.dataset.action);
  });
});

modeBtn.addEventListener("click", () => {
  mode = mode === "deg" ? "rad" : "deg";
  modeBtn.textContent = mode.toUpperCase();
});

document.getElementById("clearHistory").addEventListener("click", clearHistory);

document.addEventListener("keydown", (e) => {
  if (/^[0-9.+\-*/^()]$/.test(e.key)) insert(e.key);
  else if (e.key === "Enter" || e.key === "=") { e.preventDefault(); calculate(); }
  else if (e.key === "Backspace") handleAction("back");
  else if (e.key === "Escape") handleAction("clear");
});

// ---------- start ----------
if (USE_API) {
  document.getElementById("status").textContent = "☁️ Connected to AWS";
  document.getElementById("status").classList.add("cloud");
  document.getElementById("historySource").textContent = "Saved in DynamoDB ☁️";
}
show("0");
loadHistory();
