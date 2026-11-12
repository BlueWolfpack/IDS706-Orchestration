/** Hand-set positions — keep ≥160px node width with padding; no overlaps. */

export const NODE_WIDTH = 180
export const LEAD_HEIGHT = 78
export const SUB_HEIGHT = 70

export const GRAPH_POSITIONS: Record<string, { x: number; y: number }> = {
  meta_supervisor: { x: 420, y: 0 },

  data_scientist: { x: 40, y: 140 },
  data_profiler: { x: 0, y: 250 },
  leakage_auditor: { x: 40, y: 340 },
  feature_analyst: { x: 80, y: 430 },

  hypothesis_generator: { x: 280, y: 140 },
  memory_retriever: { x: 260, y: 250 },
  hypothesis_drafter: { x: 280, y: 340 },
  novelty_checker: { x: 300, y: 430 },

  ml_engineer: { x: 520, y: 140 },
  config_validator: { x: 500, y: 250 },
  experiment_runner: { x: 520, y: 340 },
  error_repair: { x: 540, y: 430 },

  judge: { x: 760, y: 140 },
  metric_analyst: { x: 740, y: 250 },
  overfitting_checker: { x: 760, y: 340 },
  independent_reviewer: { x: 780, y: 430 },

  // Planned parallel row (amber)
  parallel_a: { x: 200, y: 560 },
  parallel_b: { x: 420, y: 560 },
  parallel_c: { x: 640, y: 560 },
  fan_in: { x: 420, y: 660 },
}
