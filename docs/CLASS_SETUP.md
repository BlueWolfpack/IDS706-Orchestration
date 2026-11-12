# AutoML Research Lab: Student Setup

Classroom demo in two parts. Start in **`lab/`**; peek at **`solution/`** when revealed; ignore **`advanced/`** until later.

```
lab/          student stubs (Airflow DAGs + LangGraph)
solution/     filled reference (Airflow DAGs + LangGraph)
advanced/     full multi-agent stack (gateway services, orchestrator, …)
frontend/     UI — opens on /guide
```

1. **Airflow** — merge CSVs, train a baseline, publish a dataset (Docker only)
2. **LangGraph solution loop** — run the mini research loop in the UI (no Airflow required)

You can run the sections independently, or run Airflow first so `/solution-loop` can use `merged_latest.csv`.

---

## Prerequisites

| Tool | macOS | Windows |
| --- | --- | --- |
| Docker Desktop | Install from [docker.com](https://www.docker.com/products/docker-desktop/); leave it running | Same; use the WSL2 backend (recommended) |
| Python 3.12+ | Homebrew / python.org | python.org installer; check **Add python.exe to PATH** |
| Node.js 20+ | Homebrew / nodejs.org | nodejs.org LTS installer |
| Make | Xcode CLT (`xcode-select --install`) or Homebrew | [Git for Windows](https://git-scm.com/download/win) (Git Bash includes `make`) or `choco install make` |
| Git | Xcode CLT / Homebrew | [Git for Windows](https://git-scm.com/download/win) |
| Terminal | Terminal.app / iTerm | **Git Bash** for `make start-windows` / `make down-windows` |

Do not install Airflow on the host. It runs only in Docker.

---

## One-time: clone and env

```bash
git clone https://github.com/Kedar-V/automl-research-lab.git
cd automl-research-lab
```

```bash
cp .env.example .env          # macOS / Git Bash
# Copy-Item .env.example .env # Windows PowerShell
```

`make start-mac` / `make start-windows` / `make airflow` will create `.env` from `.env.example` if it is missing.

Edit `.env` as needed:

| Variable | Used by | Required? |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Lab/solution loop LLM agents | Recommended (without it, nodes use fallbacks) |
| `OPENROUTER_MODEL` | Lab/solution loop | Optional (default: `nvidia/nemotron-3.5-lightning:free`) |
| `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` | Airflow UI | Optional (default: `admin` / `admin`) |
| `CURSOR_API_KEY` | Lab/solution loop when Model = Cursor SDK; also full multi-agent stack | Optional |
| `WANDB_*` | Full multi-agent stack only | Optional |

Keep secrets in `.env`. Never commit real keys.

---

## Quick start — web app (one command)

Docker Desktop must be running. From the **repo root**, pick your OS:

| | macOS | Windows |
| --- | --- | --- |
| **Start** (Docker + UI) | `make start-mac` | `make start-windows` *(Git Bash)* |
| **Stop** (Vite + Docker) | `make down-mac` | `make down-windows` *(Git Bash)* |

```bash
# macOS
make start-mac
make down-mac

# Windows (Git Bash)
make start-windows
make down-windows
```

`make start` / `make down` alone print this reminder and exit — always use the `-mac` or `-windows` target.

That will:

1. Ensure `.env` exists
2. Build/start the Docker stack (gateway + services)
3. Wait until `http://127.0.0.1:8000/healthz` is up
4. `npm install` + start Vite

Then open **[http://127.0.0.1:5173](http://127.0.0.1:5173)**

Useful routes once the UI is up:

| Route | What |
| --- | --- |
| [/guide](http://127.0.0.1:5173/guide) | Student guide (Airflow + LangGraph copyable steps) — default landing |
| [/lab-loop](http://127.0.0.1:5173/lab-loop) | Lab loop (student skeleton) |
| [/solution-loop](http://127.0.0.1:5173/solution-loop) | Solution loop (filled reference) |
| [/advanced](http://127.0.0.1:5173/advanced) | Full multi-agent Control Center |

`down-mac` frees `:5173` with `lsof`. `down-windows` frees `:5173` with PowerShell, then both run `docker compose … down`.

---

## Section 1: Set up Airflow

Goal: start Airflow in Docker, confirm the UI + DAGs, run prep, publish a subset CSV for later use.

### Steps (macOS / Make)

1. Make sure **Docker Desktop** is running.
2. From the **repo root**, ensure `.env` exists (`cp .env.example .env` if needed).
3. Start the Airflow profile:

```bash
make airflow
```

Equivalent:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow up --build -d
```

4. **Wait 1–2 minutes** (longer on first build). Confirm containers:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow ps
```

`airflow-webserver` should be healthy / running before you open the UI.

5. Open [http://localhost:8088](http://localhost:8088) and log in with `admin` / `admin` (unless `.env` overrides).
6. Confirm the DAG list has:
   - `lab_baseline_prep` — student lab (empty Graph until wired)
   - `solution_baseline_prep` — instructor / filled reference
   - `solution_baseline_and_trigger` — later reveal (stub)

Docker only. Do not install Airflow on your host.

**Run prep (UI):** unpause `solution_baseline_prep` → Trigger → Graph tab (tasks turn green).

![Airflow DAG graph for solution_baseline_prep](docs/images/airflow-dag.jpg)

**CLI alternative (still Docker):**

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow run --rm airflow-prep-once
```

**Confirm publish**

```bash
ls -la datasets/airflow/merged_latest.csv
ls -la artifacts/airflow/runs/
```

**Stop Airflow** (also stops the main stack + Vite if it was up):

```bash
make down-mac          # macOS
# make down-windows    # Windows (Git Bash)
```

### Windows — Airflow

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow up --build -d
```

Wait 1–2 minutes, then:

```powershell
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow ps
```

**UI:** [http://localhost:8088](http://localhost:8088) — `admin` / `admin`  
Same DAGs as above.

**Run prep (UI):** unpause `solution_baseline_prep` → Trigger → Graph.

**CLI alternative:**

```powershell
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow run --rm airflow-prep-once
```

**Confirm publish**

```powershell
Get-Item datasets\airflow\merged_latest.csv
Get-ChildItem artifacts\airflow\runs\
```

**Stop**

```powershell
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow down
```

What the prep DAG does:

`customers.csv` ⨝ `transactions.csv` → subset (~2000 rows) → train baseline → publish

More detail: [`lab/airflow/README.md`](lab/airflow/README.md) · data: [`datasets/airflow/ATTRIBUTION.md`](datasets/airflow/ATTRIBUTION.md)

---

## Section 2: LangGraph solution loop

Goal: run the mini LangGraph loop at `/solution-loop`.

**macOS:** `make start-mac` (see Quick start) is enough — backend + UI.  
**Windows:** `make start-windows` from Git Bash.

Then open [http://127.0.0.1:5173/solution-loop](http://127.0.0.1:5173/solution-loop)

- After Section 1: dataset `merged_latest.csv`, target `is_fraud`
- Without Airflow: e.g. `Titanic-Dataset.csv`, target `Survived`

![Simple research loop UI with merged_latest.csv and live agent graph](docs/images/solution-loop.jpg)

**Optional checks**

```bash
make health
curl -s http://127.0.0.1:8000/solution-loop/info | python3 -m json.tool
```

**Backend only** (no Vite): `make up` then `make health`  
**Frontend only** (stack already up): `make frontend`

**Stop:** `make down-mac` or `make down-windows` (Vite + Docker).

**CLI only (optional)** — needs local install once: `make install`

```bash
.venv/bin/python solution/langgraph/run_cli.py \
  --dataset datasets/Titanic-Dataset.csv \
  --target Survived \
  --max-cycles 3
```

### Windows — simple loop

`make start-windows` from Git Bash (see Quick start), then open `/solution-loop`.

```powershell
foreach ($port in 8000,8011,8002,8003,8004,8005,8006) {
  Write-Host -NoNewline "localhost:$port -> "
  try {
    Invoke-RestMethod "http://127.0.0.1:$port/healthz" | Out-Null
    Write-Host "ok"
  } catch {
    Write-Host "FAIL"
  }
}
```

**Stop**

```powershell
docker compose -f infra/docker-compose.yml --env-file .env down
```

**CLI only (optional)**

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\python solution\langgraph\run_cli.py `
  --dataset datasets\Titanic-Dataset.csv `
  --target Survived `
  --max-cycles 3
```

---

## Suggested classroom order

| Order | What | Outcome |
| --- | --- | --- |
| 1 | Airflow **student** DAG `lab_baseline_prep` | Fill [`lab/airflow/dags/lab_baseline_prep.py`](lab/airflow/dags/lab_baseline_prep.py), wire deps → Graph fills → run |
| 2 | (Optional reveal) instructor DAG | Baseline + `merged_latest.csv` via `solution_baseline_prep` |
| 3 | LangGraph **Lab Loop** | Fill [`lab/langgraph/graph.py`](lab/langgraph/graph.py) → `/lab-loop` empty until ready → Run |
| 4 | (Optional reveal) `/solution-loop` | Solution loop on the same CSV |
| 5 | (Later) `solution_baseline_and_trigger` | Reveal how Airflow could call the loop |

Guide UI: [http://127.0.0.1:5173/guide](http://127.0.0.1:5173/guide) after `make start-mac` / `make start-windows`.

### Lab Loop (student LangGraph)

With the web app running:

1. Follow [`lab/langgraph/COPY_GUIDE.md`](lab/langgraph/COPY_GUIDE.md) — paste into [`lab/langgraph/graph.py`](lab/langgraph/graph.py) one step at a time
2. Open [http://127.0.0.1:5173/lab-loop](http://127.0.0.1:5173/lab-loop)
3. **Refresh graph**, then **Run loop**

**macOS status check:** `python -m lab.langgraph.run_cli --status` (after `make install`)  
**Windows status check:** `.\.venv\Scripts\python -m lab.langgraph.run_cli --status`

### Airflow student DAG

After Airflow is up, open the UI and find `lab_baseline_prep`. The Graph tab stays empty until the wiring block in [`lab/airflow/dags/lab_baseline_prep.py`](lab/airflow/dags/lab_baseline_prep.py) is uncommented. Copy steps: [`lab/airflow/COPY_GUIDE.md`](lab/airflow/COPY_GUIDE.md) or the in-app guide.

---

## Useful ports

| What | URL |
| --- | --- |
| Frontend | http://127.0.0.1:5173 |
| Gateway API | http://127.0.0.1:8000 |
| Airflow UI | http://localhost:8088 |
| MLflow (full stack) | http://127.0.0.1:5050 |

## Make targets

| Target | OS | What |
| --- | --- | --- |
| `make start-mac` | macOS | Ensure `.env`, Docker stack, wait for gateway, Vite UI |
| `make start-windows` | Windows (Git Bash) | Same as `start-mac` |
| `make down-mac` | macOS | Stop Vite (`lsof` :5173) + Docker (incl. Airflow) |
| `make down-windows` | Windows (Git Bash) | Stop Vite (PowerShell :5173) + Docker (incl. Airflow) |
| `make airflow` | both | Start Airflow profile (UI on :8088) |
| `make up` | both | Docker stack only |
| `make health` | both | Curl service `/healthz` ports |
| `make frontend` | both | Vite only (stack already up) |
| `make install` | both | Local `.venv` + editable install (CLI / tests) |

---

## Full multi-agent lab (not required for the two demos above)

### macOS

```bash
cp .env.example .env   # set MOCK_*=false for live research
make start-mac
```

### Windows (Git Bash)

```bash
cp .env.example .env   # then edit MOCK_*=false for live research
make start-windows
```

Upload `datasets/churn_sample.csv`, target `churned`.  
Design canvas: [`AutoML_Research_Lab_demo_canvas.pdf`](AutoML_Research_Lab_demo_canvas.pdf) · mock script: [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md)
