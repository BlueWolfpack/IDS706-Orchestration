# Student copy guide — Airflow baseline prep

Paste into [`lab_baseline_prep.py`](lab_baseline_prep.py) **one task at a time**.  
Filled reference (same code + comments): [`../../solution/airflow/dags/solution_baseline_prep.py`](../../solution/airflow/dags/solution_baseline_prep.py).

For each `@task`, keep the `@task` / `def` lines. Replace the stub **docstring + `raise NotImplementedError`** with the matching block (same as `/guide` → Airflow).

In-app Copy buttons (Python-highlighted): `/guide` → Airflow tab.

---

## Reference comments already in the skeleton (do not delete)

```python
# ---------------------------------------------------------------------------
# Paths inside the Airflow containers (/repo is the mounted project root)
# ---------------------------------------------------------------------------

# @dag turns the function below into an Airflow DAG (a named pipeline).
# - dag_id: unique name you see in the Airflow UI
# - start_date: earliest logical date Airflow will consider (required)
# - schedule=None: manual Trigger only (no cron) — perfect for class
# - catchup=False: do not backfill old dates when the DAG is unpaused
# - tags: filters in the UI
#
# Calling lab_baseline_prep() at the bottom REGISTERS this DAG
# with the scheduler. Without that call, Airflow never sees it.

# @task turns a normal Python function into one node on the Graph.
# - Airflow runs each task in its own worker process
# - Whatever you return is stored in XCom (Airflow's small data bus)
# - Downstream tasks receive that return value as a normal argument
# - If the function raises, the task fails (red) in the UI

# Actually register the DAG with Airflow (decorators alone are not enough).
```

---

## Step 1 — `validate_customers`

```python
"""Check the customers CSV exists and has the join key."""
if not CUSTOMERS.is_file():
    raise FileNotFoundError(CUSTOMERS)
# nrows=0 → headers only (fast)
cols = list(pd.read_csv(CUSTOMERS, nrows=0).columns)
if JOIN_KEY not in cols:
    raise ValueError(f"missing {JOIN_KEY}")
# Returned dict becomes XCom → next task's left_meta
return {"path": str(CUSTOMERS)}
```

---

## Step 2 — `validate_transactions`

```python
"""Check the transactions CSV exists and has join key + target label."""
if not TRANSACTIONS.is_file():
    raise FileNotFoundError(TRANSACTIONS)
cols = list(pd.read_csv(TRANSACTIONS, nrows=0).columns)
for need in (JOIN_KEY, TARGET):
    if need not in cols:
        raise ValueError(f"missing {need}")
return {"path": str(TRANSACTIONS)}
```

---

## Step 3 — `merge_csvs`

```python
"""Join transactions ⟕ customers. One output row per transaction.

left_meta / right_meta come from upstream @task return values (XCom).
**context is Airflow runtime info — we use ts_nodash as a unique run folder.
"""
run_id = context["ts_nodash"]  # e.g. 20261104T145012
out = RUNS / run_id / "merged.csv"
out.parent.mkdir(parents=True, exist_ok=True)

left = pd.read_csv(left_meta["path"])
right = pd.read_csv(right_meta["path"])
# fact table on the left of the merge → keep one row per transaction
merged = right.merge(left, on=JOIN_KEY, how="left", suffixes=("", "_customer"))
merged.to_csv(out, index=False)
return {"merged_path": str(out), "n_merged": len(merged)}
```

---

## Step 4 — `make_subset`

```python
"""Downsample so baseline + the later lab/solution-loop demo stay fast in class."""
run_id = context["ts_nodash"]
out = RUNS / run_id / "subset.csv"
df = pd.read_csv(merge_meta["merged_path"])
n = min(SUBSET_ROWS, len(df))
subset = df.sample(n=n, random_state=42) if n < len(df) else df
subset.to_csv(out, index=False)
# Keep key name merged_path so later tasks stay uniform
return {"merged_path": str(out), "n_subset": len(subset)}
```

---

## Step 5 — `profile_light`

```python
"""List columns that look leaky / id-like so training can drop them."""
df = pd.read_csv(subset_meta["merged_path"])
drops = [
    c
    for c in df.columns
    if c != TARGET
    and (c.endswith("_id") or c in {"timestamp", "fraud_probability", "fraud_history"})
]
return {"recommended_drops": drops, "n_rows": len(df)}
```

---

## Step 6 — `train_baseline`

```python
"""Tiny numeric-only LogisticRegression — a classroom A-baseline, not production ML."""
df = pd.read_csv(subset_meta["merged_path"])
drops = list(profile_meta.get("recommended_drops") or [])
y = df[TARGET]
X = (
    df.drop(columns=[TARGET, *drops], errors="ignore")
    .select_dtypes("number")
    .fillna(0)
)
X_train, X_val, y_train, y_val = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y if y.nunique() > 1 else None,
)
clf = LogisticRegression(max_iter=500, class_weight="balanced")
clf.fit(X_train, y_train)
f1 = float(f1_score(y_val, clf.predict(X_val), zero_division=0))
return {"f1": f1, "n_train": len(X_train), "n_val": len(X_val)}
```

---

## Step 7 — `publish_merged`

```python
"""Copy the subset to a stable path the lab/solution-loop UI can pick up."""
PUBLISH.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(subset_meta["merged_path"], PUBLISH)
return {
    "published_latest": str(PUBLISH),
    "merged_dataset_path": subset_meta["merged_path"],
    "baseline_val_f1": baseline["f1"],
    "target_column": TARGET,
}
```

---

## Step 8 — Wiring (fills the Graph tab)

Delete the commented TODO wiring block and paste (never leave a bare `raise` here — Airflow executes this function at import):

```python
# -----------------------------------------------------------------------
# WIRING = the dependency graph
#
# Calling a @task function here does NOT run the Python immediately.
# It creates a node and an edge: "this task needs that task's XCom output".
# Airflow's Graph tab is literally this block drawn as boxes + arrows.
#
#   validate_customers ─┐
#                       ├─→ merge_csvs → make_subset → profile_light ─┐
#   validate_transactions ┘                    └──────────────────────┼─→ train → publish
# -----------------------------------------------------------------------
left = validate_customers()
right = validate_transactions()
merged = merge_csvs(left, right)  # waits for BOTH validates
demo = make_subset(merged)
prof = profile_light(demo)
base = train_baseline(demo, prof)  # needs subset path + drop list
publish_merged(demo, base)
```

---

## Step 9 — Run (terminal, from repo root)

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow exec airflow-scheduler \
  airflow dags unpause lab_baseline_prep

docker compose -f infra/docker-compose.yml --env-file .env --profile airflow exec airflow-scheduler \
  airflow dags trigger lab_baseline_prep

docker compose -f infra/docker-compose.yml --env-file .env --profile airflow exec airflow-scheduler \
  airflow dags list-runs -d lab_baseline_prep --state success --limit 5

ls -la datasets/airflow/merged_latest.csv
ls -la artifacts/airflow/runs/
ls -la artifacts/airflow/runs/$(ls -t artifacts/airflow/runs | head -1)/
```

Or UI: http://localhost:8088 → unpause → Trigger → Graph all green.
