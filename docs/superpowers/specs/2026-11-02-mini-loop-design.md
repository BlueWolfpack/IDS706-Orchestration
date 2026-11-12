# Simple research loop (teaching page)

Matches the “6 · Simple research loop” diagram.

## Goal
Classroom LangGraph: propose → run → judge → file-or-feedback, on Titanic. Separate from the full AutoML Control Center graph.

## Nodes (each = isolated Python script, JSON stdin/stdout)

| Script | Kind | Role |
| --- | --- | --- |
| `data_scientist.py` | LLM (once) | Profile CSV; flag leakage-ish columns |
| `hypothesis_generator.py` | LLM | One ExperimentSpec from profile + brief |
| `ml_engineer.py` | code + optional LLM repair | Validate spec, train/score, bounded repair |
| `judge.py` | LLM | Verdict from validation evidence |
| `memory_writer.py` | code | Append verdict/lesson to memory file |
| `context_builder.py` | code | Build next brief (drop repeats) |
| `holdout_eval.py` | code | Open sealed holdout **once** at end |

**Router** = LangGraph conditional edge (plain code in `graph.py`): accept / revise / stop.

**Planned (not built):** parallel experiment branches (dashed amber).

## Defaults
- Dataset: `datasets/Titanic-Dataset.csv`, target `Survived`
- LLM: OpenRouter `OPENROUTER_MODEL` (default Nemotron free tier)
- Heuristic fallbacks if key missing so the loop still demos

## UI
- Route `/simple-loop`
- Four core loop nodes highlighted + memory/holdout panels
- Run on Titanic (or upload CSV)

## Wiring
- `mini_loop/graph.py` — LangGraph only; subprocess each node script
- Do **not** modify `services/orchestrator/app/graph.py`
- Gateway `POST /simple-loop/run` shells/imports the teaching graph
