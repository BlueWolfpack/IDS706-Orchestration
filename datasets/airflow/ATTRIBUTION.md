# Airflow merge fixtures — attribution

**Source archive:** Financial Transaction Intelligence Dataset 2026 (Kaggle)  
**Slug:** `roshaaann30/financial-transaction-intelligence-dataset-2026`  
**URL:** https://www.kaggle.com/datasets/roshaaann30/financial-transaction-intelligence-dataset-2026  
**License:** CC BY-NC-SA 4.0 (synthetic / educational)  
**Vendored from:** local download `archive (2).zip`

## Files used by the teaching DAGs

| File | Role |
| --- | --- |
| `customers.csv` | Customer dimension (`customer_id`) |
| `transactions.csv` | Transaction fact + target `is_fraud` |

Other tables (`cards.csv`, `devices.csv`, `merchants.csv`) are included for stretch demos; DAG v1 merges **customers ⨝ transactions** only.

## Classroom join story

Airflow merges `transactions` ⟕ `customers` on `customer_id` → `merged.csv`.  
Baseline trains on that file; the simple research loop uses the **same** `merged.csv`.
