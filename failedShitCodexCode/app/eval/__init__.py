"""Evaluation helpers for Phase 1."""

from app.eval.dataset import EvalExample, load_eval_dataset
from app.eval.metrics import compute_hit_at_k, compute_mrr

__all__ = ["EvalExample", "load_eval_dataset", "compute_hit_at_k", "compute_mrr"]
