# Agent loop evaluation (2026-11-11T23:48:28+00:00)

Data source: **postgres** · target `is_fraud` · cycles 3 · stop reason `no_signal`

Dropped for leakage: fraud_probability

Best spec: `{"experiment_id": "exp-2", "model_family": "random_forest", "hyperparameters": {"n_estimators": 300, "max_depth": 10}, "drop_columns": ["customer_id", "customer_since", "fraud_probability", "merchant_id", "timestamp", "transaction_id"], "rationale": "Increasing n_estimators to 300 and max_depth to 10 systematically checks higher capacity while respecting the established drop list, allowing observation of F1/PR-AUC trends before considering family switches or regularization adjustments."}`

Baselines are scored on the validation split; the agent model on the sealed holdout.

| metric | majority-class baseline | flag-everything baseline | best agent model (holdout) |
| --- | --- | --- | --- |
| accuracy | 0.970 | 0.030 | 0.030 |
| balanced_accuracy | 0.500 | 0.500 | 0.500 |
| precision | 0.000 | 0.030 | 0.030 |
| recall | 0.000 | 1.000 | 1.000 |
| f1 | 0.000 | 0.059 | 0.059 |
| roc_auc | 0.500 | 0.500 | 0.494 |
| pr_auc | 0.030 | 0.030 | 0.030 |

| cycle | model family | val F1 | val PR-AUC | judge |
| --- | --- | --- | --- | --- |
| 1 | random_forest | 0.0592 | 0.026 | revise |
| 2 | random_forest | 0.0593 | 0.027 | revise |
| 3 | random_forest | 0.0592 | 0.026 | stop |
