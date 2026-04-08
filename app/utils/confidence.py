"""
VSM AI Agent – Confidence Utility (PRD 3 §8)

Utility functions for confidence tier evaluation and scoring.
"""

from app.config import get_agent_settings

settings = get_agent_settings()


def classify_confidence(score: float) -> str:
    """
    Classify a confidence score into a tier label.

    Returns:
        "AUTO_EXECUTE"    — score ≥ auto_execute_threshold (> 0.85)
        "ASK_USER"        — score ≥ ask_user_threshold (0.60–0.85)
        "REJECT"          — score < ask_user_threshold (< 0.60)
    """
    if score >= settings.auto_execute_threshold:
        return "AUTO_EXECUTE"
    elif score >= settings.ask_user_threshold:
        return "ASK_USER"
    else:
        return "REJECT"


def should_auto_execute(score: float) -> bool:
    return score >= settings.auto_execute_threshold


def should_ask_user(score: float) -> bool:
    return settings.ask_user_threshold <= score < settings.auto_execute_threshold


def should_reject(score: float) -> bool:
    return score < settings.ask_user_threshold


def weighted_average_confidence(scores: list[float], weights: list[float] | None = None) -> float:
    """
    Computes a weighted average confidence score.
    If weights is None, uses uniform weighting.
    """
    if not scores:
        return 0.0
    if weights is None:
        return sum(scores) / len(scores)
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(s * w for s, w in zip(scores, weights)) / total_weight
