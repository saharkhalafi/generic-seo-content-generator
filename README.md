# Generic Persian SEO Content Generator

Production pipeline for Persian SEO articles and category pages on any website. You describe the website in one to three sentences, enter a topic, and the same engine plans, writes, validates, scores, and optionally revises the page.

This is an SEO strategy, semantic map, search-intent, dynamic heading, Persian content, scored validation, and revision system. It is not a one-prompt article generator, and it is not tied to one industry.

## Architecture

```mermaid
flowchart TB
    UI[Streamlit UI] --> ORCH[ProductionSeoOrchestrator]
    ORCH --> PIPE[SeoBoxPipeline protected]
    ORCH --> OBS[RunObservability]
    ORCH --> STORE[CompositeRunStore]
    STORE --> SQLITE[(SQLite fallback)]
    STORE --> PG[(PostgreSQL)]
    PIPE --> LLM[Gemini API or Vertex]
    PIPE --> VAL[Local validation + scoring]
    BENCH[Benchmark module] --> BASE[Baseline single-prompt]
    BENCH --> PIPE
    IMG[Feature image stage] --> PG
    BENCH --> PG
```

**Protected core:** `src/pipeline.py` runs the planning bundle, content generation, local validation, and revision loop. Do not bypass it for production SEO.

The planning call also fills `WebsiteContext` from the short website description. That does not add a separate Gemini call.

**Production layer around the core:**

| Layer | Path | Role |
|---|---|---|
| Orchestration | `src/orchestration/` | Run IDs, stages, persistence coordination |
| Persistence | `src/persistence/` | PostgreSQL plus SQLite fallback |
| Observability | `src/observability/` | Stage timing, model calls, run metrics |
| Benchmark | `src/benchmark/` | Baseline vs pipeline comparison |
| Image | `src/image/` | Optional feature image generation with isolated failures |
| Domain | `src/domain/` | Hashing and error classification |
| Website context | `src/schemas.py`, `src/product.py` | Name, description, and inferred business context |

## Setup

```powershell
cd "E:\cursor projects\seo-content-generator"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Put your own Gemini API key in `.env`:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The key stays in `.env`. The Streamlit UI does not ask for it and does not display it.

Verify Gemini access:

```powershell
python scripts\verify_vertex.py
```

Vertex AI application-default credentials are an optional fallback when `GEMINI_API_KEY` is empty and `GOOGLE_CLOUD_PROJECT` is set. A local user does not need a Google Cloud project.

### SQLite

If `DATABASE_URL` is empty, runs are stored in SQLite at `data/seo_content.sqlite`. That file is created automatically. SQLite is the local fallback, not the production database.

### PostgreSQL

PostgreSQL is the primary database when `DATABASE_URL` is set. The connection uses a pool, `pool_pre_ping`, and connect, statement, and lock timeouts. Schema changes go through Alembic. Startup runs `upgrade` only and does not drop existing rows.

Create the database, then apply migrations:

```powershell
python scripts\init_db.py
# or
alembic upgrade head
```

Example URL, with your own password:

```env
DATABASE_URL=postgresql+psycopg://postgres:your_password_here@localhost:5432/content_generator
```

Each stored run is attached to a project named from the website name, or from the website description when the name is empty. Queries use SQLAlchemy parameters. A failed PostgreSQL write is logged and does not discard a completed SEO result; SQLite still stores the local copy.

## Running

Start the UI:

```powershell
streamlit run app.py
```

The production entry, including `/health` and `/ready`, is:

```powershell
streamlit run serve.py
```

Or, in a container, `python -m src.entrypoint`. That listens on `PORT` (default `8080`).

On the input screen enter:

1. **Website name** — optional.
2. **What this website is about** — required, one to three sentences.
3. **Article / category topic** — required.
4. **Content type** — Full or Simple.

Then choose **تولید محتوای سئو**.

The engine infers business type, audience, products or services, and domain language from the description. It does not assume an industry. Mention products or services only when they fit the topic, and do not invent any that the description does not support.

More options stay available in the expander: primary keyword override, page URL, target length, secondary keywords, industries, search intent, audience, and existing page content.

Additional Streamlit pages:

- **Benchmark**: baseline vs pipeline comparison and human evaluation.
- **Observability**: KPIs, errors, model calls, and score distribution.
- **Run History**: searchable run history with detailed inspection.
- **Regression**: compare current output against the saved baseline.

## Pipeline Flow

```text
INPUT -> local existing summary -> cannibalization check ->
PlanningBundle (1 LLM, including website context) -> content (1 LLM) ->
local validation -> up to 1 revision -> Final SEO Box
```

Supported content modes:

- **Full**: about 700-1500 words with FAQ support.
- **Simple**: about 350-800 words with a shorter structure.

Target model calls stay at one planning call, one content call, and zero or one revision call.

## Reproducibility

Every production run stores:

- `run_id`, timestamps, and `PIPELINE_VERSION`.
- Prompt versions such as `SEO_PLANNER_V2` and `CONTENT_GENERATOR_V2`.
- `input_hash`, `output_hash`, and `validation_version`.
- Website name and website description inside the stored input.
- Model, latency, revision count, and validation checks.

## Benchmarking

Gold dataset files live in `data/gold_set/*.json` and should use real category characteristics, not invented search volume.

The benchmark compares:

- **Baseline:** a single Gemini call using `BASELINE_SEO_V1`.
- **Pipeline:** the full staged system.

Tracked metrics include SEO score, category scores, latency, model calls, token usage when available, and regression flag (`REGRESSION`, `IMPROVEMENT`, or `NO_SIGNIFICANT_CHANGE`).

```powershell
pytest tests/test_production.py -q
python scripts\save_baseline.py
```

Saved regression baseline:

```text
data/baselines/clip_story_full.json
```

## Observability

Tracked stages include `input_validation`, `semantic_analysis`, `seo_planning`, `heading_planning`, `content_generation`, `validation`, `revision`, `finalization`, and `feature_image_generation`.

Model calls record provider, model, operation, duration, tokens when available, and status. Cost is stored as `NULL` when it cannot be calculated.

## Languages

The generator writes Persian SEO pages (`lang="fa"`, `dir="rtl"`). Planning and content prompts stay in Persian. Common English search terms are kept only when they are useful in the Persian page. There is no separate English article mode.

## Rate and cost limits

Defaults are intentionally small so a public or shared deployment cannot fan out unlimited Gemini calls:

| Limit | Default |
|---|---|
| Model attempts per call | 2 (one retry, transient errors only) |
| Models tried per stage | 1 |
| Content revisions | 1 |
| Concurrent generations | 2 |
| Requests per minute per client | 6 |
| Daily generations per client | 20 |
| Daily generations for the process | 40 |

Excess requests are rejected. Invalid or permanent API errors are not retried. In-memory rate limits apply per process. The global daily cap also counts rows written to PostgreSQL that day. Image generation is optional and a failed image does not fail the SEO result.

## Health checks

`/health` returns process status `ok`. `/ready` runs `SELECT 1` against PostgreSQL when `DATABASE_URL` is set, and returns 503 when that database is unreachable. With no `DATABASE_URL`, readiness reports the SQLite fallback. The container health check calls `/health`. Point a Cloud Run readiness probe at `/ready` and the liveness probe at `/health`.

## Docker

```powershell
docker build -t seo-content-generator:prod .
```

The image runs as a non-root user, does not copy `.env`, and exposes port 8080. For local Docker against the PostgreSQL already running on the host:

```powershell
docker compose up --build
```

Compose sets `POSTGRES_HOST_OVERRIDE=host.docker.internal` so the container can reach the host database without changing `.env`.

## Production deployment

A single container plus managed PostgreSQL is enough. Set `DATABASE_URL`, `GEMINI_API_KEY`, and `PORT`. Run `alembic upgrade head` before or during startup (`RUN_MIGRATIONS=1` in the container entrypoint). Do not commit secrets. Cloud Run can use the container health paths above. Kubernetes, Redis, and a separate worker queue are not required.

## Testing

```powershell
pytest tests -q -m "not integration"
pytest tests -q -m integration
pytest tests -q
```

The PostgreSQL integration tests require `DATABASE_URL` and a migrated `content_generator` database. Gemini is mocked in unit tests, so the suite does not need a live API key. Context tests cover a furniture store, a SaaS company, a restaurant, and an educational website.

## CI

GitHub Actions installs dependencies, runs Ruff, runs the non-integration tests, applies Alembic migrations to a PostgreSQL service, runs the integration tests, scans source for obvious secrets, runs `pip-audit`, and builds the Docker image. A failed test or image build fails the workflow.

## Security

User text is length-limited before a model call. Generated HTML and Markdown exports strip scripts, iframes, and `javascript:` URLs. Responses sent to the browser use `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`. Database access stays on parameterized SQLAlchemy statements. Logs redact API keys, bearer tokens, and database URLs. `.env` is gitignored and listed in `.dockerignore`.

## Configuration

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API key for local generation |
| `GOOGLE_API_KEY` | Alternate name for the same key |
| `GEMINI_MODEL` | Default Gemini model |
| `GEMINI_ANALYSIS_MODEL` | Optional analysis-stage model fallback list |
| `GEMINI_CONTENT_MODEL` | Optional content-stage model fallback list |
| `GEMINI_VALIDATION_MODEL` | Optional validation-stage model fallback list |
| `GEMINI_IMAGE_MODEL` | Optional feature-image model |
| `DATABASE_URL` | PostgreSQL URL. Empty falls back to SQLite |
| `SQLITE_PATH` | SQLite path when PostgreSQL is not configured |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_SECONDS`, `DB_POOL_RECYCLE_SECONDS` | Connection pool |
| `DB_CONNECT_TIMEOUT_SECONDS`, `DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS`, `DB_MAX_ATTEMPTS` | Database timeouts and transient retries |
| `POSTGRES_HOST_OVERRIDE` | Rewrite only the database host, used by Docker Compose |
| `GEMINI_TIMEOUT_SECONDS`, `GEMINI_MAX_ATTEMPTS`, `GEMINI_RETRY_MIN_SECONDS`, `GEMINI_RETRY_MAX_SECONDS`, `GEMINI_MAX_MODELS` | Gemini timeout, retry, and model cap |
| `MAX_TOPIC_LENGTH`, `MAX_WEBSITE_DESCRIPTION_LENGTH`, `MAX_EXISTING_CONTENT_LENGTH`, `MAX_REQUEST_CHARS`, `MAX_LIST_ITEMS` | Input size limits |
| `FULL_MIN_WORDS`, `FULL_MAX_WORDS`, `SIMPLE_MIN_WORDS`, `SIMPLE_MAX_WORDS` | Target length bounds |
| `MAX_CONCURRENT_GENERATIONS`, `MAX_REQUESTS_PER_MINUTE`, `DAILY_LIMIT_PER_CLIENT`, `DAILY_LIMIT_GLOBAL` | Rate and cost caps |
| `LOG_FORMAT` | `text` or `json` |
| `PORT` | HTTP port for the container entrypoint |
| `RUN_MIGRATIONS` | `1` runs `alembic upgrade head` before serving |
| `GOOGLE_CLOUD_PROJECT` | Optional Vertex AI project |
| `GOOGLE_CLOUD_LOCATION` | Optional Vertex AI region |
| `PIPELINE_VERSION` | Version stored with each run |

Never commit `.env`, service accounts, or API keys.

## Scoring

SEO scores are calculated on a 0-100 scale:

- Technical: 15%
- Keyword: 20%
- Intent: 20%
- Content: 20%
- Headings: 10%
- Persian quality: 5%
- Product fit: 5%
- Trust: 5%

Score bands:

- 90+ Excellent
- 80-89 Good
- 70-79 Needs Improvement
- Below 70 Revision Required

Product-fit checks use the website you described. Unsupported absolute claims are flagged. A fixed product catalog is not assumed.

## Exports

The app can export JSON, Markdown, and HTML. HTML output uses Persian page metadata with `lang="fa"` and `dir="rtl"`, and keeps the generated H1/H2/H3, paragraphs, lists, and FAQ markup so it can be copied into a CMS.

## Feature Images

Feature image generation is optional and lives in `src/image/feature_image.py`. The prompt is built from the website context, the article topic, and the article text. The image should show the topic, not an advertisement for the website. Image failures do not invalidate a successful SEO run.

## Layout

```text
app.py                  Streamlit UI
serve.py                Production ASGI entry with /health and /ready
Dockerfile
src/pipeline.py         Protected SEO engine
src/orchestration/
src/persistence/        PostgreSQL pool, Alembic, SQLite fallback
src/limits.py           Rate, daily, and concurrency gates
src/health.py
pages/                  Benchmark, Observability, Run History, Regression
alembic/versions/
tests/
```
