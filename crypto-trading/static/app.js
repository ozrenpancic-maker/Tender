const STRATEGY_COLORS = {
  buy_hold: "#64748b",
  baseline_2pct: "#dc2626",
  sma_crossover: "#2f5fdb",
  rsi_meanrev: "#059669",
  dip_buy_volume: "#d97706",
  equity_filtered: "#7c3aed",
  multi_macro_filter: "#be185d",
  technical_composite: "#0891b2",
  macro_signal_composite: "#ca8a04",
  derivatives_extremes: "#15803d",
  __cash__: "#94a3b8",
};

function getApiKey() {
  try {
    return localStorage.getItem("dashboardApiKey") || "";
  } catch {
    return "";
  }
}

async function api(path, options = {}) {
  const key = getApiKey();
  const headers = { ...(options.headers || {}) };
  if (key) headers["Authorization"] = `Bearer ${key}`;
  const res = await fetch(path, { ...options, headers });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    document.getElementById("apiKeySection").style.display = "block";
  }
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

document.getElementById("apiKeyInput").value = getApiKey();
document.getElementById("apiKeySave").addEventListener("click", () => {
  const value = document.getElementById("apiKeyInput").value.trim();
  try {
    if (value) localStorage.setItem("dashboardApiKey", value);
    else localStorage.removeItem("dashboardApiKey");
  } catch {
    // localStorage nedostupan (npr. privatni način) - ključ se neće pamtiti između posjeta.
  }
  location.reload();
});

function fmtEur(n) {
  return `${Number(n).toLocaleString("hr-HR", { maximumFractionDigits: 2 })} €`;
}

function fmtPct(n) {
  return `${Number(n).toFixed(1)}%`;
}

// ---------- Tabovi (grupiraju odjeljke u par pregleda, bez mijenjanja postojeće logike) ----------

function setActiveTab(tab) {
  document.querySelectorAll("main > section[data-tab]").forEach((el) => {
    el.classList.toggle("active-tab", el.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tabTarget === tab);
  });
  try {
    localStorage.setItem("dashboardTab", tab);
  } catch {
    // localStorage nedostupan - tab se jednostavno neće pamtiti između posjeta.
  }
}

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => setActiveTab(btn.dataset.tabTarget));
});

let savedTab = "pregled";
try {
  savedTab = localStorage.getItem("dashboardTab") || "pregled";
} catch {
  // localStorage nedostupan - zadano na "pregled".
}
setActiveTab(savedTab);

// ---------- Init ----------

let STRATEGIES = [];
let PAIRS = [];

async function init() {
  const [{ strategies }, { pairs }] = await Promise.all([api("/api/strategies"), api("/api/pairs")]);
  STRATEGIES = strategies;
  PAIRS = pairs;

  fillSelect("btPair", pairs);
  fillSelect("ppPair", pairs.filter((p) => p !== "BTC/EUR" || true));
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
  await renderMacroSyncRows();
  await refreshAll();
  setInterval(refreshAll, AUTO_REFRESH_MS);
}

// ---------- Globalno osvježavanje (bez ručnog klikanja po svakoj sekciji) ----------

const AUTO_REFRESH_MS = 60000; // sve što je dolje je čisto čitanje (GET), bez mrežnih troškova/sync-a

async function refreshAll() {
  // Promise.allSettled (ne Promise.all) - jedna sekcija koja ne uspije (npr. API ključ istekao)
  // ne smije spriječiti da se ostale ažuriraju niti srušiti periodični setInterval poziv.
  await Promise.allSettled([refreshPredictions(), refreshSignals(), refreshPaperRuns(), refreshAutoTraderRuns(), refreshWhaleMirrorRuns()]);
  const el = document.getElementById("lastRefreshedAt");
  if (el) el.textContent = `Zadnje osvježeno: ${new Date().toLocaleTimeString("hr-HR")}`;
}

document.getElementById("refreshAllBtn").addEventListener("click", () => {
  refreshAll().catch((err) => alert("Greška pri osvježavanju: " + err.message));
});

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
  // Gotovina (bez trgovanja) kao eksplicitna usporedna točka - "je li se ovo uopće isplatilo
  // naspram da sam ništa nije radio" (ChatGPT savjet, točka 3). Ravna linija na polaznom iznosu.
  if (results.length) {
    const anyCurve = results.find((r) => r.equity_curve && r.equity_curve.length)?.equity_curve;
    if (anyCurve) {
      results.push({
        strategy: "__cash__",
        final_balance: starting_balance,
        trades: 0,
        winning_trades: 0,
        max_drawdown_pct: 0,
        equity_curve: [
          { at: anyCurve[0].at, equity: starting_balance },
          { at: anyCurve[anyCurve.length - 1].at, equity: starting_balance },
        ],
      });
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
  const slRaw = document.getElementById("btStopLoss").value.trim();
  const riskRaw = document.getElementById("btRiskPct").value.trim();
  const stop_loss_pct = slRaw ? Number(slRaw) / 100 : null;
  const risk_pct = riskRaw ? Number(riskRaw) / 100 : null;
  const r = await api("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy, pair, start_date, end_date, starting_balance, params, stop_loss_pct, risk_pct }),
  });
  renderBacktestTable([r], starting_balance);
  renderBacktestChart([r]);
});

document.getElementById("btCostSensitivity").addEventListener("click", async () => {
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
  const results = await api("/api/backtest/cost-sensitivity", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy, pair, start_date, end_date, starting_balance, params }),
  });
  const table = document.getElementById("costSensTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const [key, r] of Object.entries(results)) {
    const tr = document.createElement("tr");
    if (r.error) {
      tr.innerHTML = `<td>${r.label}</td><td colspan="4" class="muted">${r.error}</td>`;
    } else {
      tr.innerHTML = `
        <td>${r.label}</td>
        <td>${(r.fee * 100).toFixed(2)}%</td>
        <td>${(r.slippage * 100).toFixed(2)}%</td>
        <td>${fmtEur(r.final_balance)}</td>
        <td>${fmtPct(r.max_drawdown_pct)}</td>
      `;
    }
    tbody.appendChild(tr);
  }
  table.style.display = "table";
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
    const label = r.strategy === "__cash__" ? "Gotovina (bez trgovanja)" : (STRATEGIES.find((s) => s.key === r.strategy) || {}).label || r.strategy;
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
    const label = r.strategy === "__cash__" ? "Gotovina" : (STRATEGIES.find((s) => s.key === r.strategy) || {}).label || r.strategy;
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

// ---------- Makro / sentiment / regulativa ----------

const SOURCE_TITLES = {
  fred: "FRED (makro)",
  defillama: "DeFiLlama (TVL)",
  coingecko: "CoinGecko (ponuda tokena)",
  google_trends: "Google Trends",
  reddit: "Reddit sentiment",
  etf_flow: "ETF tokovi",
  regulatory: "Regulativa (SEC/CFTC)",
  binance_futures: "Binance futures (funding rate)",
  github: "GitHub aktivnost",
  cryptopanic: "CryptoPanic vijesti",
};

async function renderMacroSyncRows() {
  const { sources } = await api("/api/macro/labels");
  const container = document.getElementById("macroSyncRows");
  container.innerHTML = "";

  for (const [source, labels] of Object.entries(sources)) {
    const row = document.createElement("div");
    row.className = "row";
    row.style.marginBottom = "6px";
    const title = document.createElement("strong");
    title.textContent = SOURCE_TITLES[source] || source;
    title.style.minWidth = "180px";
    row.appendChild(title);

    for (const label of labels) {
      const btn = document.createElement("button");
      btn.className = "secondary";
      btn.textContent = `Sinkroniziraj ${label}`;
      btn.onclick = async () => {
        const resultEl = document.getElementById("macroResult");
        resultEl.textContent = `Sinkroniziram ${label}…`;
        try {
          const r = await api(`/api/macro/sync/${source}/${label}`, { method: "POST" });
          resultEl.innerHTML = `<p><span class="pill ok">${label}</span> ${r.rows} redaka sinkronizirano.</p>`;
        } catch (err) {
          resultEl.innerHTML = `<p><span class="pill fail">${label}</span> ${err.message}</p>`;
        }
      };
      row.appendChild(btn);
    }
    container.appendChild(row);
  }
}

document.getElementById("macroTest").addEventListener("click", async () => {
  const el = document.getElementById("macroResult");
  el.textContent = "Testiram sve veze…";
  try {
    const r = await api("/api/macro/test-connection");
    const lines = [];
    for (const [source, labels] of Object.entries(r)) {
      lines.push(`<p><strong>${SOURCE_TITLES[source] || source}</strong></p>`);
      for (const [label, s] of Object.entries(labels)) {
        lines.push(`<p style="margin-left:12px"><span class="pill ${s.ok ? "ok" : "fail"}">${label}</span> ${s.message}</p>`);
      }
    }
    el.innerHTML = lines.join("");
  } catch (err) {
    el.textContent = "Greška: " + err.message;
  }
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
    el.innerHTML = `<p><span class="pill ${r.public_feed.ok ? "ok" : "fail"}">Javni feed</span> ${r.public_feed.message}</p>`;
  } catch (err) {
    el.textContent = "Greška: " + err.message;
  }
});

// ---------- Paper trading ----------

async function downloadCsv(url, filename) {
  const key = getApiKey();
  const headers = key ? { Authorization: `Bearer ${key}` } : {};
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

document.getElementById("ppExportCsv").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await downloadCsv("/api/paper/export-csv", "paper_trading_dnevnik_SIMULACIJA.csv");
  } catch (err) {
    alert("Greška pri izvozu: " + err.message);
  }
});

document.getElementById("ppStart").addEventListener("click", async () => {
  const strategy = document.getElementById("ppStrategy").value;
  const pair = document.getElementById("ppPair").value;
  const starting_balance = Number(document.getElementById("ppBalance").value);
  const interval_min = Number(document.getElementById("ppInterval").value);
  const execution_mode = document.getElementById("ppExecutionMode").value;
  const dailyLossLimitRaw = document.getElementById("ppDailyLossLimit").value.trim();
  const daily_loss_limit_pct = dailyLossLimitRaw ? Number(dailyLossLimitRaw) / 100 : null;
  try {
    await api("/api/paper/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, pair, starting_balance, interval_min, execution_mode, daily_loss_limit_pct }),
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
    const intervalLabel = run.interval_min === 60 ? "satno" : "dnevno";
    const execLabel = run.execution_mode === "maker_post_only" ? "maker" : "taker";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${run.id}</td><td>${label}</td><td>${run.pair}</td><td>${intervalLabel}</td><td>${execLabel}</td><td>${run.status}</td>
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
  const pendingLine = run.pending_side
    ? `<p><span class="pill">Nalog na čekanju</span> ${run.pending_side === "buy" ? "kupnja" : "prodaja"} @ ${fmtEur(run.pending_limit_price)} - čeka ispunjenje (maker)</p>`
    : "";
  const haltedLine = run.daily_halted
    ? `<p><span class="pill fail">Pauziran do sutra</span> dnevni limit gubitka (${(run.daily_loss_limit_pct * 100).toFixed(1)}%) probijen - pozicija prisilno zatvorena, novi ulasci blokirani do novog dana.</p>`
    : "";
  el.innerHTML = `<h3>Run #${run.id} — ${run.pair}</h3>
    <p class="muted">Pokrenut ${new Date(run.started_at * 1000).toLocaleString("hr-HR")}. ${trades.length} trgovina.</p>
    ${pendingLine}${haltedLine}`;
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

// ---------- Automatizirani paper trading (AI bira coin) ----------

document.getElementById("atTradeMode").addEventListener("change", (e) => {
  const isSwing = e.target.value === "swing";
  document.getElementById("atSwingFields").style.display = isSwing ? "flex" : "none";
  document.getElementById("atSwingNote").style.display = isSwing ? "block" : "none";
});

document.getElementById("atExportCsv").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await downloadCsv("/api/auto-trader/export-csv", "auto_trader_SVI_RUNOVI_SIMULACIJA.csv");
  } catch (err) {
    alert("Greška pri izvozu: " + err.message);
  }
});

document.getElementById("atStart").addEventListener("click", async () => {
  const horizon = document.getElementById("atHorizon").value;
  const starting_balance = Number(document.getElementById("atBalance").value);
  const max_position_pct = Number(document.getElementById("atMaxPct").value) / 100;
  const trade_mode = document.getElementById("atTradeMode").value;
  const min_hold_periods = Number(document.getElementById("atMinHold").value) || 1;
  const tpRaw = document.getElementById("atTakeProfit").value.trim();
  const slRaw = document.getElementById("atStopLoss").value.trim();
  const take_profit_pct = tpRaw ? Number(tpRaw) / 100 : null;
  const stop_loss_pct = slRaw ? Number(slRaw) / 100 : null;
  try {
    await api("/api/auto-trader/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        horizon, starting_balance, max_position_pct, trade_mode, min_hold_periods, take_profit_pct, stop_loss_pct,
      }),
    });
    refreshAutoTraderRuns();
  } catch (err) {
    alert(err.message);
  }
});

async function refreshAutoTraderRuns() {
  const { runs } = await api("/api/auto-trader/runs");
  const table = document.getElementById("atTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const run of runs) {
    const modeLabel = run.trade_mode === "swing" ? "swing" : "scalp";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${run.id}</td><td>${run.horizon}</td><td>${modeLabel}</td><td>${run.status}</td>
      <td>${fmtEur(run.current_equity_eur)}</td><td>${run.open_positions}</td><td></td>`;
    const actionCell = tr.querySelector("td:last-child");
    const viewBtn = document.createElement("button");
    viewBtn.className = "secondary";
    viewBtn.textContent = "Detalji";
    viewBtn.onclick = () => showAutoTraderDetail(run.id);
    actionCell.appendChild(viewBtn);
    if (run.status === "running") {
      const stopBtn = document.createElement("button");
      stopBtn.className = "danger-btn";
      stopBtn.textContent = "Zaustavi";
      stopBtn.style.marginLeft = "6px";
      stopBtn.onclick = async () => {
        await api(`/api/auto-trader/${run.id}/stop`, { method: "POST" });
        refreshAutoTraderRuns();
      };
      actionCell.appendChild(stopBtn);
    }
    tbody.appendChild(tr);
  }
  table.style.display = runs.length ? "table" : "none";
}

async function showAutoTraderDetail(runId) {
  const { run, trades, positions } = await api(`/api/auto-trader/${runId}`);
  const universe = JSON.parse(run.universe_json);
  const el = document.getElementById("atDetail");
  const modeLine =
    run.trade_mode === "swing"
      ? `Način rada: <strong>swing</strong> (min. ${run.min_hold_periods} perioda, profit cilj ${run.take_profit_pct ? fmtPct(run.take_profit_pct * 100) : "isključen"}, stop-loss ${run.stop_loss_pct ? fmtPct(run.stop_loss_pct * 100) : "isključen"}).`
      : "Način rada: <strong>scalp</strong>.";
  el.innerHTML = `<h3>Run #${run.id} — ${run.horizon}</h3>
    <p class="muted">Pokrenut ${new Date(run.started_at * 1000).toLocaleString("hr-HR")}. Univerzum: ${universe.join(", ")}.
    Gotovina: ${fmtEur(run.cash_eur)}. ${trades.length} trgovina. ${modeLine}</p>`;
  if (positions.filter((p) => !p.closed_at).length) {
    const list = document.createElement("table");
    list.innerHTML = `<thead><tr><th>Par</th><th>Ušao</th><th>Ulog</th></tr></thead><tbody>${positions
      .filter((p) => !p.closed_at)
      .map((p) => `<tr><td>${p.pair}</td><td>${fmtEur(p.entry_price)}</td><td>${fmtEur(p.entry_eur)}</td></tr>`)
      .join("")}</tbody>`;
    el.appendChild(list);
  }
  if (trades.length) {
    const list = document.createElement("table");
    list.innerHTML = `<thead><tr><th>Kad</th><th>Par</th><th>Strana</th><th>Cijena</th><th>AI Score</th><th>Odluka</th></tr></thead><tbody>${trades
      .slice()
      .reverse()
      .map(
        (t) =>
          `<tr><td>${new Date(t.executed_at * 1000).toLocaleString("hr-HR")}</td><td>${t.pair}</td><td>${t.side}</td><td>${fmtEur(t.price)}</td><td>${t.ai_score ?? "-"}</td><td>${t.decision ?? "-"}</td></tr>`,
      )
      .join("")}</tbody>`;
    el.appendChild(list);
  }
}

// ---------- Whale mirror (zrcali javni on-chain novčanik, uživo) ----------

function fmtUsd(n) {
  return `$${Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

document.getElementById("wmExportCsv").addEventListener("click", async (e) => {
  e.preventDefault();
  try {
    await downloadCsv("/api/whale-mirror/export-csv", "whale_mirror_SVI_RUNOVI_SIMULACIJA.csv");
  } catch (err) {
    alert("Greška pri izvozu: " + err.message);
  }
});

document.getElementById("wmStart").addEventListener("click", async () => {
  const label = document.getElementById("wmLabel").value.trim() || "(bez oznake)";
  const address = document.getElementById("wmAddress").value.trim();
  const starting_balance = Number(document.getElementById("wmBalance").value);
  const threshold_pct = Number(document.getElementById("wmThreshold").value) / 100;
  try {
    await api("/api/whale-mirror/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, address, pair: "ETH/USDT", starting_balance, threshold_pct }),
    });
    refreshWhaleMirrorRuns();
  } catch (err) {
    alert(err.message);
  }
});

async function refreshWhaleMirrorRuns() {
  const { runs } = await api("/api/whale-mirror/runs");
  const table = document.getElementById("wmTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const run of runs) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${run.id}</td><td>${run.label}</td><td>${run.status}</td>
      <td>${fmtUsd(run.current_equity)}</td><td>${run.in_position ? "da" : "ne"}</td><td></td>`;
    const actionCell = tr.querySelector("td:last-child");
    const viewBtn = document.createElement("button");
    viewBtn.className = "secondary";
    viewBtn.textContent = "Detalji";
    viewBtn.onclick = () => showWhaleMirrorDetail(run.id);
    actionCell.appendChild(viewBtn);
    if (run.status === "running") {
      const stopBtn = document.createElement("button");
      stopBtn.className = "danger-btn";
      stopBtn.textContent = "Zaustavi";
      stopBtn.style.marginLeft = "6px";
      stopBtn.onclick = async () => {
        await api(`/api/whale-mirror/${run.id}/stop`, { method: "POST" });
        refreshWhaleMirrorRuns();
      };
      actionCell.appendChild(stopBtn);
    }
    tbody.appendChild(tr);
  }
  table.style.display = runs.length ? "table" : "none";
}

async function showWhaleMirrorDetail(runId) {
  const { run, trades } = await api(`/api/whale-mirror/${runId}`);
  const el = document.getElementById("wmDetail");
  el.innerHTML = `<h3>Run #${run.id} — ${run.label}</h3>
    <p class="muted">Adresa: <code>${run.address}</code>. Pokrenut ${new Date(run.started_at * 1000).toLocaleString("hr-HR")}.
    Prag: ${fmtPct(run.threshold_pct * 100)}. Gotovina: ${fmtUsd(run.cash)}. ${trades.length} trgovina.</p>`;
  if (trades.length) {
    const list = document.createElement("table");
    list.innerHTML = `<thead><tr><th>Kad</th><th>Strana</th><th>Cijena</th><th>Iznos</th><th>Whale stanje (ETH)</th><th>Promjena</th></tr></thead><tbody>${trades
      .slice()
      .reverse()
      .map(
        (t) =>
          `<tr><td>${new Date(t.executed_at * 1000).toLocaleString("hr-HR")}</td><td>${t.side}</td><td>${fmtUsd(t.price)}</td><td>${fmtUsd(t.amount_usd)}</td><td>${t.whale_balance_eth.toLocaleString("hr-HR", { maximumFractionDigits: 2 })}</td><td>${t.whale_delta_pct >= 0 ? "+" : ""}${fmtPct(t.whale_delta_pct * 100)}</td></tr>`,
      )
      .join("")}</tbody>`;
    el.appendChild(list);
  }
}

// ---------- Tvoj portfolio (Binance povijest proizvoljnih parova) ----------

document.getElementById("bhTest").addEventListener("click", async () => {
  const el = document.getElementById("bhResult");
  el.textContent = "Testiram…";
  try {
    const r = await api("/api/binance-history/test-connection");
    el.innerHTML = Object.entries(r)
      .map(([pair, s]) => `<p><span class="pill ${s.ok ? "ok" : "fail"}">${pair}</span> ${s.message}</p>`)
      .join("");
  } catch (err) {
    el.textContent = "Greška: " + err.message;
  }
});

async function syncBinancePair(pair, interval) {
  return api("/api/binance-history/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pair, interval }),
  });
}

document.getElementById("bhSyncAll").addEventListener("click", async () => {
  const el = document.getElementById("bhResult");
  const interval = document.getElementById("bhInterval").value;
  el.textContent = "Sinkroniziram…";
  const { pairs } = await api("/api/binance-history/pairs");
  const lines = [];
  for (const pair of pairs) {
    try {
      const r = await syncBinancePair(pair, interval);
      lines.push(`<p><span class="pill ok">${pair}</span> ${r.rows} svijeća (${interval}) sinkronizirano.</p>`);
    } catch (err) {
      lines.push(`<p><span class="pill fail">${pair}</span> ${err.message}</p>`);
    }
    el.innerHTML = lines.join("");
  }
  await refreshPairSelectors();
});

document.getElementById("bhSyncManual").addEventListener("click", async () => {
  const pair = document.getElementById("bhManualPair").value.trim();
  if (!pair) return;
  const interval = document.getElementById("bhInterval").value;
  const el = document.getElementById("bhResult");
  el.textContent = `Sinkroniziram ${pair}…`;
  try {
    const r = await syncBinancePair(pair, interval);
    el.innerHTML = `<p><span class="pill ok">${pair}</span> ${r.rows} svijeća (${interval}) sinkronizirano.</p>`;
    await refreshPairSelectors();
  } catch (err) {
    el.innerHTML = `<p><span class="pill fail">${pair}</span> ${err.message}</p>`;
  }
});

async function refreshPairSelectors() {
  const { pairs } = await api("/api/pairs");
  PAIRS = pairs;
  fillSelect("btPair", pairs);
  fillSelect("ppPair", pairs);
  fillSelect("lvPair", pairs);
  fillSelect("optPair", pairs);
}

// ---------- Signali kupi/prodaj ----------

const ACTION_CLASS = {
  PRODAJ: "fail",
  KUPI: "ok",
  DRŽI: "",
  ČEKAJ: "",
};

function actionBadge(action) {
  const cls = ACTION_CLASS[action];
  return cls ? `<span class="pill ${cls}">${action}</span>` : action;
}

async function refreshSignals() {
  const statusEl = document.getElementById("sigStatus");
  const table = document.getElementById("sigTable");
  statusEl.textContent = "Dohvaćam signale uživo…";

  try {
    const { signals } = await api("/api/signals");
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";

    for (const [pair, byHorizon] of Object.entries(signals)) {
      const short = byHorizon.short;
      const long = byHorizon.long;
      const price = (short && short.price) || (long && long.price);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${pair}</strong></td>
        <td>${price != null ? price.toLocaleString("hr-HR", { maximumFractionDigits: 6 }) : "—"}</td>
        <td>${short && !short.error ? actionBadge(short.holding_action) : `<span class="muted">${short?.error || "nema podataka"}</span>`}</td>
        <td>${short && !short.error ? actionBadge(short.entry_action) : "—"}</td>
        <td>${long && !long.error ? actionBadge(long.holding_action) : `<span class="muted">${long?.error || "nema podataka"}</span>`}</td>
        <td>${long && !long.error ? actionBadge(long.entry_action) : "—"}</td>
      `;
      tbody.appendChild(tr);
    }

    table.style.display = "table";
    statusEl.textContent = `Ažurirano ${new Date().toLocaleTimeString("hr-HR")}. Prije prvog pokretanja sinkroniziraj povijest (odjeljak 3) za coinove koje želiš vidjeti ovdje.`;
  } catch (err) {
    statusEl.textContent = "Greška: " + err.message;
  }
}

document.getElementById("sigRefresh").addEventListener("click", refreshSignals);

// ---------- AI Prediction Engine (ML) ----------

const DECISION_CLASS = {
  "STRONG SELL": "fail",
  SELL: "fail",
  WAIT: "",
  BUY: "ok",
  "STRONG BUY": "ok",
  "NEMA DOVOLJNO POUZDANIH PODATAKA": "",
};

function decisionBadge(decision) {
  const cls = DECISION_CLASS[decision] || "";
  return cls ? `<span class="pill ${cls}">${decision}</span>` : decision;
}

async function refreshPredictions() {
  const statusEl = document.getElementById("predStatus");
  const table = document.getElementById("predTable");
  statusEl.textContent = "Dohvaćam AI predikcije…";

  try {
    const { predictions } = await api("/api/predictions");
    const tbody = table.querySelector("tbody");
    tbody.innerHTML = "";

    for (const [pair, byHorizon] of Object.entries(predictions)) {
      for (const [horizon, pred] of Object.entries(byHorizon)) {
        if (pred.error) continue;
        const tr = document.createElement("tr");
        const probs =
          pred.p_up != null
            ? `${fmtPct(pred.p_up * 100)} / ${fmtPct(pred.p_down * 100)} / ${fmtPct(pred.p_sideways * 100)}`
            : "—";
        const reasons = [...(pred.reasons_for || []), ...(pred.reasons_against || [])].slice(0, 2).join(" ");
        tr.innerHTML = `
          <td><strong>${pair}</strong></td>
          <td>${pred.horizon_label || horizon}</td>
          <td>${decisionBadge(pred.decision)}</td>
          <td>${pred.ai_score != null ? pred.ai_score : "—"}</td>
          <td>${probs}</td>
          <td class="muted" style="font-size:12px">${reasons}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    table.style.display = "table";
    statusEl.textContent = `Ažurirano ${new Date().toLocaleTimeString("hr-HR")}.`;
  } catch (err) {
    statusEl.textContent = "Greška: " + err.message;
  }
}

document.getElementById("predRefresh").addEventListener("click", refreshPredictions);

async function refreshRetrainLog() {
  const { log } = await api("/api/predictions/retrain-log");
  const table = document.getElementById("retrainLogTable");
  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";
  for (const entry of log) {
    for (const [horizon, d] of Object.entries(entry.decisions || {})) {
      const tr = document.createElement("tr");
      const badge = d.promoted ? '<span class="pill ok">promoviran</span>' : '<span class="pill">zadržan stari</span>';
      tr.innerHTML = `<td>${entry.at_human}</td><td>${horizon}</td><td>${badge}</td><td class="muted" style="font-size:12px">${d.reason}</td>`;
      tbody.appendChild(tr);
    }
  }
  table.style.display = log.length ? "table" : "none";
}

document.getElementById("retrainNowBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("retrainStatus");
  statusEl.textContent = "Treniram... ovo može potrajati par minuta, ne zatvaraj stranicu.";
  try {
    await api("/api/predictions/retrain-now", { method: "POST" });
    statusEl.textContent = "Gotovo.";
    await refreshRetrainLog();
  } catch (err) {
    statusEl.textContent = "Greška: " + err.message;
  }
});

refreshRetrainLog();

init();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((err) => console.warn("Service worker nije uspio:", err));
  });
}
