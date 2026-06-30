from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Serve the personal read-only paper-trading dashboard."""
    return DASHBOARD_HTML


DASHBOARD_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TradeSentinel Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f172a;
      --panel: #111827;
      --panel-soft: #1f2937;
      --border: #334155;
      --text: #e5e7eb;
      --muted: #94a3b8;
      --accent: #22c55e;
      --warning: #f59e0b;
      --danger: #ef4444;
      --cash: #38bdf8;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at top left, rgba(34, 197, 94, 0.16), transparent 28rem),
        radial-gradient(circle at bottom right, rgba(56, 189, 248, 0.12), transparent 24rem),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 48px;
    }

    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 28px;
    }

    h1 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.2rem);
      letter-spacing: -0.05em;
    }

    h2 {
      margin: 0 0 16px;
      font-size: 1rem;
      letter-spacing: 0.02em;
      color: var(--muted);
      text-transform: uppercase;
    }

    p { color: var(--muted); line-height: 1.55; }

    .subtitle {
      margin: 10px 0 0;
      max-width: 720px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      white-space: nowrap;
      border: 1px solid rgba(34, 197, 94, 0.45);
      background: rgba(34, 197, 94, 0.1);
      color: #bbf7d0;
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 0.9rem;
    }

    .dot {
      width: 9px;
      height: 9px;
      border-radius: 999px;
      background: var(--accent);
      box-shadow: 0 0 18px var(--accent);
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }

    .card, .panel {
      border: 1px solid rgba(148, 163, 184, 0.18);
      background: rgba(17, 24, 39, 0.78);
      box-shadow: 0 20px 70px rgba(0, 0, 0, 0.24);
      backdrop-filter: blur(14px);
      border-radius: 22px;
    }

    .card { padding: 18px; }
    .panel { padding: 22px; margin-top: 16px; }

    .metric-label {
      margin: 0 0 10px;
      color: var(--muted);
      font-size: 0.86rem;
    }

    .metric-value {
      margin: 0;
      font-size: 2rem;
      font-weight: 750;
      letter-spacing: -0.04em;
    }

    .metric-note {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 0.82rem;
    }

    .latest {
      display: grid;
      grid-template-columns: 220px 1fr;
      gap: 18px;
      align-items: stretch;
    }

    .signal-badge {
      display: grid;
      place-items: center;
      min-height: 160px;
      border-radius: 18px;
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.18), rgba(34, 197, 94, 0.1));
      border: 1px solid rgba(148, 163, 184, 0.16);
    }

    .signal-badge strong {
      font-size: 2.6rem;
      letter-spacing: -0.06em;
    }

    .muted { color: var(--muted); }

    .table-wrap {
      overflow-x: auto;
      border-radius: 16px;
      border: 1px solid rgba(148, 163, 184, 0.16);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 820px;
      background: rgba(15, 23, 42, 0.48);
    }

    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.12);
      text-align: left;
      font-size: 0.92rem;
    }

    th {
      color: var(--muted);
      font-weight: 600;
      background: rgba(15, 23, 42, 0.72);
    }

    tr:last-child td { border-bottom: 0; }

    .tag {
      display: inline-flex;
      border-radius: 999px;
      padding: 4px 9px;
      font-weight: 700;
      font-size: 0.78rem;
      letter-spacing: 0.02em;
    }

    .tag-buy, .tag-hold, .tag-gain { background: rgba(34, 197, 94, 0.16); color: #86efac; }
    .tag-cash { background: rgba(56, 189, 248, 0.16); color: #7dd3fc; }
    .tag-loss { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
    .tag-flat, .tag-pending { background: rgba(148, 163, 184, 0.16); color: #cbd5e1; }

    .charts {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 26px;
    }

    .chart h3 {
      margin: 0 0 14px;
      font-size: 0.95rem;
      font-weight: 650;
      color: var(--text);
    }

    .chart-row {
      display: grid;
      grid-template-columns: 78px 1fr 36px;
      align-items: center;
      gap: 10px;
      margin-bottom: 11px;
    }

    .chart-label { font-size: 0.85rem; color: var(--muted); }

    .chart-track {
      background: rgba(148, 163, 184, 0.12);
      border-radius: 999px;
      height: 14px;
      overflow: hidden;
    }

    .chart-fill {
      display: block;
      height: 100%;
      border-radius: 999px;
      min-width: 2px;
      transition: width 0.4s ease;
    }

    .chart-count {
      font-size: 0.85rem;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }

    .fill-buy, .fill-hold, .fill-gain { background: var(--accent); }
    .fill-cash { background: var(--cash); }
    .fill-loss { background: var(--danger); }
    .fill-flat, .fill-pending { background: var(--muted); }
    .fill-day { background: var(--accent); }
    .fill-day.zero { background: rgba(148, 163, 184, 0.25); }

    @media (max-width: 700px) { .charts { grid-template-columns: 1fr; } }

    .footer-note {
      margin-top: 18px;
      font-size: 0.85rem;
      color: var(--muted);
    }

    .error {
      border-color: rgba(239, 68, 68, 0.4);
      color: #fecaca;
    }

    @media (max-width: 900px) {
      header, .latest { grid-template-columns: 1fr; display: grid; }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }

    @media (max-width: 560px) {
      .grid { grid-template-columns: 1fr; }
      main { width: min(100% - 20px, 1180px); padding-top: 20px; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>TradeSentinel</h1>
        <p class="subtitle">
          Dashboard personal de paper trading. Lee señales y resultados guardados;
          no ejecuta operaciones ni modifica la estrategia.
        </p>
      </div>
      <div class="status-pill"><span class="dot"></span><span id="status">Cargando...</span></div>
    </header>

    <section class="grid" aria-label="Métricas principales">
      <article class="card">
        <p class="metric-label">Señales guardadas</p>
        <p class="metric-value" id="totalSignals">--</p>
        <p class="metric-note">BTC/USDT determinista</p>
      </article>
      <article class="card">
        <p class="metric-label">Evaluadas</p>
        <p class="metric-value" id="evaluatedSignals">--</p>
        <p class="metric-note">Horizonte forward</p>
      </article>
      <article class="card">
        <p class="metric-label">Pendientes</p>
        <p class="metric-value" id="pendingSignals">--</p>
        <p class="metric-note">Esperando vela cerrada</p>
      </article>
      <article class="card">
        <p class="metric-label">Retorno promedio</p>
        <p class="metric-value" id="avgReturn">--</p>
        <p class="metric-note">Por señal evaluada</p>
      </article>
    </section>

    <section class="panel">
      <h2>Distribución</h2>
      <div class="charts">
        <div class="chart">
          <h3>Señales por acción</h3>
          <div id="actionChart"><p class="muted">Cargando...</p></div>
        </div>
        <div class="chart">
          <h3>Resultados de tracking</h3>
          <div id="outcomeChart"><p class="muted">Cargando...</p></div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Captura por día (últimos 14 días)</h2>
      <div id="dailyChart"><p class="muted">Cargando...</p></div>
      <p class="footer-note">
        Vela cada 4 h => ~6 señales/día cuando la captura corre parejo. Días con menos
        indican que el job no se ejecutó (apagón o salto del cron).
      </p>
    </section>

    <section class="panel">
      <h2>Última señal</h2>
      <div class="latest">
        <div class="signal-badge">
          <div>
            <strong id="latestAction">--</strong>
            <p class="muted" id="latestConfidence">Confianza --/100</p>
          </div>
        </div>
        <div>
          <p><strong>Par:</strong> <span id="latestPair">--</span></p>
          <p><strong>Vela de señal:</strong> <span id="latestTimestamp">--</span></p>
          <p><strong>Régimen:</strong> <span id="latestRegime">--</span></p>
          <p class="muted" id="latestReasoning">Esperando datos...</p>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Historial reciente</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Fecha señal</th>
              <th>Par</th>
              <th>Acción</th>
              <th>Confianza</th>
              <th>Resultado</th>
              <th>Retorno observado</th>
            </tr>
          </thead>
          <tbody id="signalsTable">
            <tr><td colspan="7" class="muted">Cargando señales...</td></tr>
          </tbody>
        </table>
      </div>
      <p class="footer-note">
        Métricas educativas de paper trading; no son rendimiento de cartera ni garantía.
      </p>
    </section>
  </main>

  <script>
    const formatDate = (value) => {
      if (!value) return "--";
      return new Intl.DateTimeFormat("es-CO", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "UTC",
      }).format(new Date(value)) + " UTC";
    };

    const pct = (value) => {
      if (value === null || value === undefined) return "sin datos";
      const number = Number(value);
      return `${number >= 0 ? "+" : ""}${number.toFixed(4)}%`;
    };

    const tag = (value) => {
      const normalized = String(value || "pending").toLowerCase();
      return `<span class="tag tag-${normalized}">${String(value || "pending").toUpperCase()}</span>`;
    };

    const renderBars = (containerId, items) => {
      const max = Math.max(1, ...items.map((item) => item.count));
      document.getElementById(containerId).innerHTML = items.map((item) => `
        <div class="chart-row">
          <span class="chart-label">${item.label}</span>
          <span class="chart-track"><span class="chart-fill fill-${item.cls}" style="width:${(item.count / max) * 100}%"></span></span>
          <span class="chart-count">${item.count}</span>
        </div>
      `).join("");
    };

    async function loadDashboard() {
      const [statsRes, signalsRes, resultsRes] = await Promise.all([
        fetch("/stats"),
        fetch("/signals?pair=BTC%2FUSDT&limit=500"),
        fetch("/tracking/results?limit=500"),
      ]);

      if (!statsRes.ok || !signalsRes.ok || !resultsRes.ok) {
        throw new Error("No se pudieron cargar los datos del dashboard.");
      }

      const stats = await statsRes.json();
      const signals = await signalsRes.json();
      const results = await resultsRes.json();
      const resultBySignalId = new Map(results.map((result) => [result.signal_id, result]));

      document.getElementById("totalSignals").textContent = stats.total_signals;
      document.getElementById("evaluatedSignals").textContent = stats.evaluated_signals;
      document.getElementById("pendingSignals").textContent = stats.pending_signals;
      document.getElementById("avgReturn").textContent = pct(stats.average_signal_return_pct);

      if (signals.length) {
        const latest = signals[0];
        document.getElementById("latestAction").textContent = latest.action;
        document.getElementById("latestConfidence").textContent = `Confianza ${latest.confidence}/100`;
        document.getElementById("latestPair").textContent = latest.pair;
        document.getElementById("latestTimestamp").textContent = formatDate(latest.signal_timestamp);
        document.getElementById("latestRegime").textContent = latest.regime_on ? "activo" : "inactivo";
        document.getElementById("latestReasoning").textContent = latest.reasoning;
      }

      const actions = { BUY: 0, HOLD: 0, CASH: 0 };
      signals.forEach((signal) => { actions[signal.action] = (actions[signal.action] || 0) + 1; });
      renderBars("actionChart", [
        { label: "BUY", count: actions.BUY, cls: "buy" },
        { label: "HOLD", count: actions.HOLD, cls: "hold" },
        { label: "CASH", count: actions.CASH, cls: "cash" },
      ]);

      const outcomes = { gain: 0, loss: 0, flat: 0, cash: 0, pending: 0 };
      signals.forEach((signal) => {
        const result = resultBySignalId.get(signal.id);
        outcomes[result ? result.outcome : "pending"] += 1;
      });
      renderBars("outcomeChart", [
        { label: "Gain", count: outcomes.gain, cls: "gain" },
        { label: "Loss", count: outcomes.loss, cls: "loss" },
        { label: "Flat", count: outcomes.flat, cls: "flat" },
        { label: "Cash", count: outcomes.cash, cls: "cash" },
        { label: "Pendiente", count: outcomes.pending, cls: "pending" },
      ]);

      const dayCounts = new Map();
      signals.forEach((signal) => {
        const key = new Date(signal.signal_timestamp).toISOString().slice(0, 10);
        dayCounts.set(key, (dayCounts.get(key) || 0) + 1);
      });
      const now = new Date();
      const days = [];
      for (let i = 0; i < 14; i += 1) {
        const day = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - i));
        const key = day.toISOString().slice(0, 10);
        const count = dayCounts.get(key) || 0;
        days.push({ label: key.slice(5), count, cls: count ? "day" : "day zero" });
      }
      renderBars("dailyChart", days);

      const rows = signals.slice(0, 25).map((signal) => {
        const result = resultBySignalId.get(signal.id);
        return `
          <tr>
            <td>#${signal.id}</td>
            <td>${formatDate(signal.signal_timestamp)}</td>
            <td>${signal.pair}</td>
            <td>${tag(signal.action)}</td>
            <td>${signal.confidence}/100</td>
            <td>${tag(result ? result.outcome : "pending")}</td>
            <td>${result ? pct(result.pnl_pct) : "pendiente"}</td>
          </tr>
        `;
      }).join("");

      document.getElementById("signalsTable").innerHTML =
        rows || '<tr><td colspan="7" class="muted">Todavía no hay señales guardadas.</td></tr>';
      document.getElementById("status").textContent = "API conectada";
    }

    loadDashboard().catch((error) => {
      console.error(error);
      document.getElementById("status").textContent = "Error";
      document.querySelector(".status-pill").classList.add("error");
      document.getElementById("signalsTable").innerHTML =
        '<tr><td colspan="7">No se pudieron cargar los datos. Revisa que el backend esté activo.</td></tr>';
    });
  </script>
</body>
</html>
"""
