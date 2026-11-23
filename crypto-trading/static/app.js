const STRATEGY_COLORS = {
  buy_hold: "#64748b",
  baseline_2pct: "#dc2626",
  sma_crossover: "#2f5fdb",
  rsi_meanrev: "#059669",
  dip_buy_volume: "#d97706",
  equity_filtered: "#7c3aed",
};

async function api(path, options) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function fmtEur(n) {
  return `${Number(n).toLocaleString("hr-HR", { maximumFractionDigits: 2 })} €`;
}

function fmtPct(n) {
  return `${Number(n).toFixed(1)}%`;
}

// ---------- Init ----------

let STRATEGIES = [];
let PAIRS = [];

async function init() {
  const [{ strategies }, { pairs }] = await Promise.all([api("/api/strategies"), api("/api/pairs")]);
  STRATEGIES = strategies;
  PAIRS = pairs;

  fillSelect("btPair", pairs);
  fillSelect("ppPair", pairs.filter((p) => p !== "BTC/EUR" || true));
  fillSelect("lvPair", pairs);
  fillSelect("optPair", pairs);
  fillSelect(
    "btStrategy",
    strategies.map((s) => s.key),
    strategies.reduce((acc, s) => ({ ...acc, [s.key]: s.label }), {}),
  );
  const tradable = strategies.filter((s) => !s.backtest_only);
  fillSelect(
    "optStrategy",
    tradable.map((s) => s.key),
    tradable.reduce((acc, s) => ({ ...acc, [s.key]: s.label }), {}),
  );
  fillSelect(
    "ppStrategy",
    tradable.map((s) => s.key),
    tradable.reduce((acc, s) => ({ ...acc, [s.key]: s.label }), {}),
  );
  fillSelect(
    "lvStrategy",
    tradable.map((s) => s.key),
    tradable.reduce((acc, s) => ({ ...acc, [s.key]: s.label }), {}),
  );

  await refreshLiveStatus();
  await refreshPaperRuns();
  await refreshLiveRuns();
}

function fillSelect(id, values, labels) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = labels ? labels[v] || v : v;
    el.appendChild(opt);
  }
}

// ---------- Backtest ----------

document.getElementById("btRunAll").addEventListener("click", async () => {
  const pair = document.getElementById("btPair").value;
  const start_date = document.getElementById("btStart").value;
  const end_date = document.getElementById("btEnd").value;
  const starting_balance = Number(document.getElementById("btBalance").value);

  const keys = STRATEGIES.filter((s) => s.key !== "baseline_2pct" || pair === "BTC/EUR").map((s) => s.key);
  const results = [];
  for (const key of keys) {
    try {
      const r = await api("/api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ strategy: key, pair, start_date, end_date, starting_balance }),
      });
      results.push(r);
    } catch (err) {
      console.warn(key, err.message);
    }
  }
  renderBacktestTable(results, starting_balance);
  renderBacktestChart(results);
});

document.getElementById("btRunOne").addEventListener("click", async () => {
  const pair = document.getElementById("btPair").value;
  const start_date = document.getElementById("btStart").value;
  const end_date = document.getElementById("btEnd").value;
  const starting_balance = Number(document.getElementById("btBalance").value);
  const strategy = document.getElementById("btStrategy").value;
  let params = {};
  try {
    params = JSON.parse(document.getElementById("btParams").value || "{}");
  } catch {
    alert("Parametri nisu valjan JSON.");
    return;
  }
  const r = await api("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy, pair, start_date, end_date, starting_balance, params }),
  });
  renderBacktestTable([r], starting_balance);
  renderBacktestChart([r]);
});

function renderBacktestTable(results, startingBalance) {
  const sorted = [...results].sort((a, b) => b.final_balance - a.final_balance);
  const table = document.getElementById("btTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  sorted.forEach((r, i) => {
    const tr = document.createElement("tr");
    if (i === 0) tr.className = "best";
    if (i === sorted.length - 1 && sorted.length > 1) tr.className = "worst";
    const returnPct = ((r.final_balance / startingBalance - 1) * 100).toFixed(1);
    const label = (STRATEGIES.find((s) => s.key === r.strategy) || {}).label || r.strategy;
    tr.innerHTML = `<td>${label}</td><td>${fmtEur(r.final_balance)}</td><td>${returnPct}%</td>
      <td>${r.trades}</td><td>${r.winning_trades}</td><td>${fmtPct(r.max_drawdown_pct)}</td>`;
    tbody.appendChild(tr);
  });
  table.style.display = "table";
}

function renderBacktestChart(results) {
  const canvas = document.getElementById("btChart");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!results.length) return;

  const allPoints = results.flatMap((r) => r.equity_curve);
  const minAt = Math.min(...allPoints.map((p) => p.at));
  const maxAt = Math.max(...allPoints.map((p) => p.at));
  const minEq = Math.min(...allPoints.map((p) => p.equity));
  const maxEq = Math.max(...allPoints.map((p) => p.equity));

  const pad = 30;
  const w = canvas.width - pad * 2;
  const h = canvas.height - pad * 2;
  const x = (at) => pad + ((at - minAt) / (maxAt - minAt || 1)) * w;
  const y = (eq) => pad + h - ((eq - minEq) / (maxEq - minEq || 1)) * h;

  ctx.strokeStyle = "#e2e8f0";
  ctx.strokeRect(pad, pad, w, h);

  for (const r of results) {
    ctx.strokeStyle = STRATEGY_COLORS[r.strategy] || "#334155";
    ctx.lineWidth = 2;
    ctx.beginPath();
    r.equity_curve.forEach((p, i) => {
      const px = x(p.at);
      const py = y(p.equity);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }

  let legendX = pad;
  ctx.font = "11px sans-serif";
  for (const r of results) {
    ctx.fillStyle = STRATEGY_COLORS[r.strategy] || "#334155";
    ctx.fillRect(legendX, 6, 10, 10);
    ctx.fillStyle = "#334155";
    const label = (STRATEGIES.find((s) => s.key === r.strategy) || {}).label || r.strategy;
    ctx.fillText(label, legendX + 14, 15);
    legendX += ctx.measureText(label).width + 36;
  }
}

// ---------- Wall Street / equity ----------

document.getElementById("eqTest").addEventListener("click", async () => {
  const el = document.getElementById("eqResult");
  el.textContent = "Testiram…";
  try {
    const r = await api("/api/equity/test-connection");
    el.innerHTML = Object.entries(r)
      .map(([label, s]) => `<p><span class="pill ${s.ok ? "ok" : "fail"}">${label}</span> ${s.message}</p>`)
      .join("");
  } catch (err) {
    el.textContent = "Greška: " + err.message;
  }
});

document.getElementById("eqSyncAll").addEventListener("click", async () => {
  const el = document.getElementById("eqResult");
  el.textContent = "Sinkroniziram…";
  const { labels } = await api("/api/equity/labels");
  const lines = [];
  for (const label of labels) {
    try {
      const r = await api(`/api/equity/sync/${label}`, { method: "POST" });
      lines.push(`<p><span class="pill ok">${label}</span> ${r.rows} redaka sinkronizirano.</p>`);
    } catch (err) {
      lines.push(`<p><span class="pill fail">${label}</span> ${err.message}</p>`);
    }
  }
  el.innerHTML = lines.join("");
});

// ---------- Optimizacija ----------

document.getElementById("optRun").addEventListener("click", async () => {
  const statusEl = document.getElementById("optStatus");
  const table = document.getElementById("optTable");
  statusEl.style.display = "block";
  statusEl.textContent = "Pretražujem kombinacije parametara…";
  table.style.display = "none";

  const body = {
    strategy: document.getElementById("optStrategy").value,
    pair: document.getElementById("optPair").value,
    starting_balance: Number(document.getElementById("optBalance").value),
    in_start_date: document.getElementById("optInStart").value,
    in_end_date: document.getElementById("optInEnd").value,
    out_start_date: document.getElementById("optOutStart").value,
    out_end_date: document.getElementById("optOutEnd").value,
  };

  try {
    const r = await api("/api/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    statusEl.textContent = `Testirano ${r.combinations_tested} kombinacija (${r.combinations_with_result} dalo rezultat). Prikazano top ${r.top_with_out_of_sample.length} s out-of-sample provjerom.`;
    renderOptTable(r, body.starting_balance);
  } catch (err) {
    statusEl.textContent = "Greška: " + err.message;
  }
});

function renderOptTable(result, startingBalance) {
  const table = document.getElementById("optTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";

  for (const entry of result.top_with_out_of_sample) {
    const inOk = entry.in_sample.final_balance > startingBalance;
    const outOk = entry.out_of_sample && entry.out_of_sample.final_balance > startingBalance;
    let verdict, cls;
    if (inOk && outOk) {
      verdict = "✅ Profitabilno na oba razdoblja";
      cls = "best";
    } else if (inOk && !outOk) {
      verdict = "⚠️ Samo in-sample — vjerojatno curve fitting";
      cls = "worst";
    } else {
      verdict = "❌ Gubi na in-sample";
      cls = "worst";
    }

    const tr = document.createElement("tr");
    tr.className = cls;
    const outCell = entry.out_of_sample
      ? `<td>${fmtEur(entry.out_of_sample.final_balance)}</td><td>${fmtPct(entry.out_of_sample.max_drawdown_pct)}</td>`
      : `<td colspan="2">${entry.out_of_sample_error || "nema podataka"}</td>`;
    tr.innerHTML = `<td><code>${JSON.stringify(entry.params)}</code></td>
      <td>${fmtEur(entry.in_sample.final_balance)}</td><td>${fmtPct(entry.in_sample.max_drawdown_pct)}</td>
      ${outCell}<td>${verdict}</td>`;
    tbody.appendChild(tr);
  }
  table.style.display = "table";
}

// ---------- Coinbase ----------

document.getElementById("cbTest").addEventListener("click", async () => {
  const el = document.getElementById("cbResult");
  el.textContent = "Testiram…";
  try {
    const r = await api("/api/coinbase/test-connection");
    el.innerHTML = `
      <p><span class="pill ${r.public_feed.ok ? "ok" : "fail"}">Javni feed</span> ${r.public_feed.message}</p>
      <p><span class="pill ${r.authenticated.ok ? "ok" : "fail"}">Autenticirano</span> ${r.authenticated.message}</p>
    `;
  } catch (err) {
    el.textContent = "Greška: " + err.message;
  }
});

// ---------- Paper trading ----------

document.getElementById("ppStart").addEventListener("click", async () => {
  const strategy = document.getElementById("ppStrategy").value;
  const pair = document.getElementById("ppPair").value;
  const starting_balance = Number(document.getElementById("ppBalance").value);
  try {
    await api("/api/paper/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, pair, starting_balance }),
    });
    refreshPaperRuns();
  } catch (err) {
    alert(err.message);
  }
});

async function refreshPaperRuns() {
  const { runs } = await api("/api/paper/runs");
  const table = document.getElementById("ppTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const run of runs) {
    const label = (STRATEGIES.find((s) => s.key === run.strategy) || {}).label || run.strategy;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${run.id}</td><td>${label}</td><td>${run.pair}</td><td>${run.status}</td>
      <td>${fmtEur(run.current_equity_eur)}</td><td></td>`;
    const actionCell = tr.querySelector("td:last-child");
    const viewBtn = document.createElement("button");
    viewBtn.className = "secondary";
    viewBtn.textContent = "Detalji";
    viewBtn.onclick = () => showPaperDetail(run.id);
    actionCell.appendChild(viewBtn);
    if (run.status === "running") {
      const stopBtn = document.createElement("button");
      stopBtn.className = "danger-btn";
      stopBtn.textContent = "Zaustavi";
      stopBtn.style.marginLeft = "6px";
      stopBtn.onclick = async () => {
        await api(`/api/paper/${run.id}/stop`, { method: "POST" });
        refreshPaperRuns();
      };
      actionCell.appendChild(stopBtn);
    }
    tbody.appendChild(tr);
  }
  table.style.display = runs.length ? "table" : "none";
}

async function showPaperDetail(runId) {
  const { run, trades } = await api(`/api/paper/${runId}`);
  const el = document.getElementById("ppDetail");
  el.innerHTML = `<h3>Run #${run.id} — ${run.pair}</h3>
    <p class="muted">Pokrenut ${new Date(run.started_at * 1000).toLocaleString("hr-HR")}. ${trades.length} trgovina.</p>`;
  if (trades.length) {
    const list = document.createElement("table");
    list.innerHTML = `<thead><tr><th>Kad</th><th>Strana</th><th>Cijena</th></tr></thead><tbody>${trades
      .map(
        (t) =>
          `<tr><td>${new Date(t.executed_at * 1000).toLocaleString("hr-HR")}</td><td>${t.side}</td><td>${fmtEur(t.price)}</td></tr>`,
      )
      .join("")}</tbody>`;
    el.appendChild(list);
  }
}

// ---------- Live trading ----------

document.getElementById("lvConfirm").addEventListener("change", (e) => {
  document.getElementById("lvStart").disabled = !e.target.checked;
});

document.getElementById("lvStart").addEventListener("click", async () => {
  const strategy = document.getElementById("lvStrategy").value;
  const pair = document.getElementById("lvPair").value;
  try {
    await api("/api/live/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, pair }),
    });
    refreshLiveRuns();
  } catch (err) {
    alert(err.message);
  }
});

async function refreshLiveStatus() {
  const status = await api("/api/live/status");
  const banner = document.getElementById("liveBanner");
  const detailBanner = document.getElementById("liveDetailBanner");
  const form = document.getElementById("liveStartForm");

  if (status.enabled) {
    banner.className = "banner danger";
    banner.innerHTML = `⚠️ Live trgovanje je UKLJUČENO (LIVE_TRADING_ENABLED=true). Max po nalogu: ${fmtEur(
      status.max_position_eur,
    )}. Ovo šalje prave naloge s pravim novcem.`;
    detailBanner.innerHTML = "";
    form.style.display = "flex";
  } else {
    banner.className = "banner ok";
    banner.innerHTML = "✓ Live trgovanje je isključeno. Sve što radiš je backtest ili paper trading (bez pravog novca).";
    detailBanner.innerHTML =
      '<p class="muted">Live trgovanje je namjerno isključeno dok ga ručno ne uključiš u .env (LIVE_TRADING_ENABLED=true) nakon što si zadovoljan/na paper trading rezultatima. Vidi README.</p>';
    form.style.display = "none";
  }
}

async function refreshLiveRuns() {
  const { runs } = await api("/api/live/runs");
  const table = document.getElementById("lvTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const run of runs) {
    const label = (STRATEGIES.find((s) => s.key === run.strategy) || {}).label || run.strategy;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${run.id}</td><td>${label}</td><td>${run.pair}</td><td>${run.status}</td><td></td>`;
    if (run.status === "running") {
      const stopBtn = document.createElement("button");
      stopBtn.className = "danger-btn";
      stopBtn.textContent = "Zaustavi";
      stopBtn.onclick = async () => {
        await api(`/api/live/${run.id}/stop`, { method: "POST" });
        refreshLiveRuns();
      };
      tr.querySelector("td:last-child").appendChild(stopBtn);
    }
    tbody.appendChild(tr);
  }
  table.style.display = runs.length ? "table" : "none";
}

init();
setInterval(refreshPaperRuns, 30000);
