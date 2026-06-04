# Logistics Analytics Dashboard

An AI-powered logistics analytics dashboard that combines a real-time metrics dashboard with a natural-language query interface. Ask any question about the dataset in plain English — the system interprets it, queries the database safely, and streams back an answer with a chart.

---

## Setup

### Prerequisites

- Python 3.11
- Node.js 18+
- PostgreSQL 14+
- Anthropic API key

### Local Setup

**1. Clone and configure environment**

```bash
git clone <repo-url>
cd logistics-dashboard
```

Create a `.env` file at the **repo root** (pydantic-settings resolves it relative to the working directory):

```env
DATABASE_URL=postgresql+asyncpg://postgres:secret@localhost:5432/logistics
ANTHROPIC_API_KEY=sk-ant-...
CORS_ORIGINS=http://localhost:5173
CSV_PATH=./data/mock_logistics_data.csv
```

**2. Backend**

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt
```

**3. Database — create and seed**

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE logistics;"

# Seed from CSV (run from repo root)
python -m backend.db.loader
```

**4. Start backend** (from repo root)

```bash
source backend/.venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**5. Frontend**

```bash
cd frontend
npm install

# Create frontend/.env.local
echo "VITE_API_URL=http://localhost:8000" > .env.local

npm run dev
```

The app is available at `http://localhost:5173`. API calls are proxied to `http://localhost:8000` via Vite's dev proxy.

---

### Environment Variables

#### Backend (`.env` at repo root)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string. Must use `postgresql+asyncpg://` scheme for async SQLAlchemy. |
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key. The backend refuses to start without it. |
| `CORS_ORIGINS` | No | Comma-separated list of allowed CORS origins. Defaults to `http://localhost:5173`. |
| `CSV_PATH` | No | Path to the logistics CSV file used for seeding. Defaults to `./data/mock_logistics_data.csv`. |

#### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `VITE_API_URL` | No | Backend base URL. Empty string in local dev (Vite proxy handles routing). Set to the Railway backend URL in production. |

---

## Architecture

### System Overview

```
┌─────────────────────────────┐     ┌──────────────────────────────────┐
│  React 18 Frontend (Vercel) │────▶│  FastAPI Backend (Railway)       │
│                             │     │                                  │
│  Dashboard Page             │     │  GET  /api/kpi                   │
│  ├─ KPI cards               │     │  GET  /api/charts/*              │
│  ├─ Filter bar              │     │                                  │
│  └─ 4 Recharts charts       │     │  POST /api/query/ask  (SSE)      │
│                             │     │  └─ LangGraph Agent              │
│  AI Query Page              │     │     ├─ interpret_node (Claude)   │
│  ├─ Streaming answer        │     │     ├─ route_node                │
│  ├─ Dynamic chart           │     │     ├─ execute_query_node        │
│  ├─ Explainability panel    │     │     │   └─ run_query_open()      │
│  └─ Query history           │     │     ├─ execute_forecast_node     │
│                             │     │     │   └─ forecast_open()       │
└─────────────────────────────┘     │     └─ summarize_node (Claude)   │
                                    │                                  │
                                    │  POST /api/forecast              │
                                    │                                  │
                                    │  PostgreSQL (Railway)            │
                                    │  └─ orders table (400 rows)      │
                                    └──────────────────────────────────┘
```

### Key Design Decisions

**Claude never writes SQL.** The AI interprets intent and extracts structured parameters (metric, dimension, filters). A separate, auditable layer maps those parameters to safe, parameterized SQL. All user-supplied values reach the database only as bind parameters — never interpolated into query strings.

**Two-step LLM for open-ended queries.** Both the analytics and forecast paths use two Claude calls: one to extract structured parameters from the question (validated against allowlists), and one to summarize or forecast using the fetched data. This keeps the database access layer deterministic and safe while allowing the question interface to be fully free-form.

**LangGraph for explicit agent control.** The agent graph (`interpret → route → execute → summarize`) is defined explicitly rather than using an autonomous agent loop. Every node has a single responsibility; routing logic is pure Python with no LLM involvement. This makes the system auditable — the `node_trace` in every response shows exactly which path was taken.

**Chart spec built in execute nodes, not by the summarizer.** The `execute_query_node` and `execute_forecast_node` build the `chart_spec` directly from the fetched data, using known key names that the frontend `ChartWrapper` expects. The summarizer Claude call produces only the text answer. This prevents hallucinated or structurally incorrect chart specs.

**Graph rebuilt per request.** `build_agent_graph(db)` is called once per `/api/query/ask` request rather than at startup. This is required because `execute_query_node` and `execute_forecast_node` use `functools.partial` to bind the async database session, which is request-scoped.

**Dashboard uses static query templates.** The four dashboard charts use pre-defined `QUERY_TEMPLATES` keyed by `(metric, group_by)` for fast, predictable rendering without an LLM call. Only the AI Query page uses the open-ended LLM path.

### Data Flow

**Dashboard page load:**
```
Browser → GET /api/kpi + /api/charts/* (parallel)
       ← PostgreSQL aggregate queries via QUERY_TEMPLATES
       ← JSON responses rendered into KPI cards + Recharts
```

**AI query (e.g. "delay rate by warehouse last month"):**
```
Browser → POST /api/query/ask
        → interpret_node:  Claude classifies intent → "analytics_query"
        → route_node:      pure Python routing
        → execute_query_node:
            └─ _extract_query_params(): Claude extracts {metric, group_by, filters}
            └─ Validate against allowlists
            └─ Build parameterized SQL → PostgreSQL
            └─ Build chart_spec from result
        → summarize_node:  Claude writes plain-English answer
        ← SSE stream: token events → complete event (answer + chart + explainability)
Browser renders streaming text, then chart and explainability panel
```

**Forecast query (e.g. "predict DHL delay rate next 3 months"):**
```
Browser → POST /api/query/ask
        → interpret_node:  Claude classifies intent → "forecast"
        → execute_forecast_node:
            └─ _extract_params(): Claude extracts {metric, filter, periods, period_unit}
            └─ Validate against allowlists
            └─ Fetch historical time series from PostgreSQL
            └─ _llm_forecast(): Claude projects future periods with CI bounds
            └─ Build chart_spec (historical + forecast + ci_band)
        → summarize_node:  Claude writes recommendation
        ← SSE stream: same structure as analytics query
```

---

## AI Approach

### How Questions Are Interpreted

Every question goes through `interpret_node`, which makes a single Claude call with a minimal prompt: classify the intent as `analytics_query`, `forecast`, or `clarify`, and pass the original question through verbatim as `tool_params.question`. No structured parameter extraction happens here — the `interpret_node` only decides which execution branch to take.

The heavy interpretation happens inside the execute nodes:

- **Analytics queries** — `_extract_query_params()` asks Claude to map the question to a `{metric, group_by, filters, chart_type, title}` structure. Claude's output is validated against strict allowlists (8 allowed metrics, 8 allowed dimensions) before any SQL is built.
- **Forecast queries** — `_extract_params()` asks Claude to map the question to `{metric, filter_col, filter_val, periods, period_unit, title}`, again validated before SQL.

If intent is `clarify`, the graph skips execution entirely and the summarizer returns a helpful clarification prompt.

### How Tools Are Selected

Tool selection is implicit in the intent classification:

| Intent | Execution path | What Claude does |
|---|---|---|
| `analytics_query` | `execute_query_node` → `run_query_open()` | Extracts metric + dimension, fetches aggregate from DB, writes text answer |
| `forecast` | `execute_forecast_node` → `forecast_open()` | Extracts metric + filter + periods, fetches time series, projects future values |
| `clarify` | Skips execution | Writes a clarification message |

Both tools share the same schema (`question: str`) in `TOOL_SCHEMAS`. The routing decision is made entirely by the `interpret_node` Claude call, not by tool-use API features.

---

## Assumptions

- **Static dataset.** The 400-row logistics CSV covers 2025-01-01 to 2025-12-30 and is loaded once at deploy time. There is no live data ingestion.
- **Single-digit concurrency.** The system is designed for 1–5 simultaneous users (portfolio/demo scale). No connection pooling tuning, rate limiting, or horizontal scaling has been applied.
- **English only.** All questions are assumed to be in English. Non-English input is not tested and may produce unpredictable routing.
- **LLM forecasting is indicative.** Forecasts are produced by Claude analyzing the historical series, not by a statistical model. Results are non-deterministic and suitable for demo purposes, not production inventory planning.
- **No authentication on the backend.** The API endpoints are publicly accessible. The Vercel frontend is protected by Basic Auth middleware, but the Railway backend URL is unprotected.
- **In-browser query history only.** Query history is stored in React state — it resets on page refresh and is not persisted server-side.
- **15% safety stock is fixed.** The safety buffer on forecast recommendations is hardcoded at 15% and is not configurable by the user.

---

## Limitations

- **Metrics are allowlisted.** The open-ended query path supports 8 metrics (`order_count`, `delay_rate`, `on_time_rate`, `avg_delivery_days`, `total_order_value`, `total_quantity`, `avg_order_value`, `canceled_rate`) and 8 dimensions (`carrier`, `region`, `product_category`, `sku`, `warehouse`, `status`, `month`, `week`). Questions that require a metric or dimension outside this set will fall back to the closest match or return a clarification.
- **No multi-metric queries.** Questions like "compare delay rate and order volume by carrier" require a single metric per query. Multi-axis charts are not supported.
- **No cross-filtering from charts.** Clicking a bar on a chart does not filter the dashboard. All filtering is done via the filter bar with explicit controls.
- **Forecast quality degrades with sparse data.** SKU-level forecasts with fewer than 6 data points produce unreliable results. Category and carrier-level forecasts are more reliable.
- **No real-time data.** The dashboard always reflects the loaded CSV snapshot. There is no polling, websocket, or live refresh.
- **Session memory.** Each AI query is answered independently. Follow-up questions ("what about last year?") do not carry context from previous queries.
- **No table export.** Data is view-only. There is no CSV download or chart image export.

---

## Future Improvements

**Multi-turn conversation memory.** Persist a conversation thread per session so follow-up questions carry context ("now filter that by DHL" after an initial query).

**Live data ingestion.** Replace the static CSV with a streaming pipeline (Kafka or webhook) so the dashboard reflects real-time shipment updates rather than a yearly snapshot.

**Expanded metric coverage.** Add support for multi-metric queries and compound questions (e.g., "carriers with both high delay rate and low order value"), likely requiring a query planner that can join multiple aggregations.

**Semantic caching.** Cache LLM responses for semantically similar questions to reduce API latency and cost. A vector similarity check against recent queries could serve cached answers for repeat patterns.

**User-level personalization.** Add authentication and per-user saved queries, custom dashboard layouts, and alert thresholds (e.g., "notify me if DHL delay rate exceeds 20%").

**Statistical forecasting fallback.** Optionally re-introduce Holt-Winters exponential smoothing for categories with sufficient history, with LLM forecasting reserved for sparse or novel queries.

**Dashboard drill-down.** Make chart segments clickable to automatically apply the corresponding filter, enabling exploration without the AI query interface.

**Test coverage.** Add integration tests using `httpx.AsyncClient` against a real PostgreSQL test database, covering the LangGraph agent paths, parameterized SQL safety, and SSE streaming correctness.
