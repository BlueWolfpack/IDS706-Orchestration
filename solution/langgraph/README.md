# Solution research loop

Filled LangGraph reference used by `/solution-loop`. Student skeleton: [`../../lab/langgraph/`](../../lab/langgraph/).

```bash
python -m solution.langgraph.run_cli \
  --dataset datasets/Titanic-Dataset.csv \
  --target Survived \
  --max-cycles 3
```

Prep helpers (no Airflow): `python -m solution.langgraph.baseline`.
