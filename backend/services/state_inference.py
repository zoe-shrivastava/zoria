"""Infer session state (emotional/engagement) from test response behavior.

Uses latency, idle time, edits, hints, confidence, navigation, and correctness
to assign one label per test: engaged, struggling, frustrated, rushing, confident.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Thresholds (tunable)
LOW_LATENCY_MS = 5000       # Very fast = possible rushing
HIGH_LATENCY_MS = 120000    # Very slow = possible struggle
HIGH_IDLE_RATIO = 0.4       # Idle time / total time
HIGH_HINTS = 2              # More than this many hints
LOW_SCORE_PCT = 40          # Score % below this = weak
HIGH_SKIP_FLAG = 2          # Many skip/flag actions


def infer_session_state(test_with_questions: Dict[str, Any]) -> Tuple[str, float]:
    """Infer one session state label from test responses.
    
    Args:
        test_with_questions: Result of get_test_with_questions (has 'questions' list).
            Each question may have: score, is_correct, response_metadata (latency_ms,
            idle_time_ms, edit_count, hints_accessed, confidence_score, navigation_actions).
    
    Returns:
        (inferred_state, confidence) where state is one of:
        engaged, struggling, frustrated, rushing, confident
        and confidence is 0.0-1.0.
    """
    questions = test_with_questions.get("questions") or []
    if not questions:
        logger.debug("Session state: no questions, defaulting to engaged")
        return "engaged", 0.0
    
    n = len(questions)
    total_score = 0.0
    max_score = 0.0
    correct_count = 0
    latencies = []
    idle_times = []
    total_latency = 0
    total_idle = 0
    total_edits = 0
    total_hints = 0
    total_skips = 0
    confidence_sum = 0
    confidence_count = 0
    
    for q in questions:
        meta = q.get("response_metadata") or {}
        if isinstance(meta, str):
            try:
                import json
                meta = json.loads(meta)
            except Exception:
                meta = {}
        
        score = q.get("score")
        if score is not None:
            total_score += float(score)
        max_score += float(q.get("max_score") or 1.0)
        if q.get("is_correct"):
            correct_count += 1
        
        lat = meta.get("latency_ms")
        if lat is not None:
            latencies.append(int(lat))
            total_latency += int(lat)
        idle = meta.get("idle_time_ms")
        if idle is not None:
            idle_times.append(int(idle))
            total_idle += int(idle)
        total_edits += int(meta.get("edit_count") or 0)
        total_hints += int(meta.get("hints_accessed") or 0)
        conf = meta.get("confidence_score")
        if conf is not None and 1 <= conf <= 5:
            confidence_sum += int(conf)
            confidence_count += 1
        
        nav = meta.get("navigation_actions")
        if isinstance(nav, list):
            for a in nav:
                if isinstance(a, str) and a.lower() in ("skip", "flag"):
                    total_skips += 1
    
    score_pct = (total_score / max_score * 100) if max_score > 0 else 0
    avg_latency = (total_latency / len(latencies)) if latencies else 0
    avg_idle = (total_idle / len(idle_times)) if idle_times else 0
    total_time = total_latency + total_idle
    idle_ratio = (total_idle / total_time) if total_time > 0 else 0
    avg_confidence = (confidence_sum / confidence_count) if confidence_count else None

    logger.debug(
        "Session state inputs: n=%s score_pct=%.1f avg_latency_ms=%.0f total_idle_ms=%s idle_ratio=%.2f total_edits=%s total_hints=%s total_skips=%s avg_confidence=%s",
        n, score_pct, avg_latency, total_idle, idle_ratio, total_edits, total_hints, total_skips, avg_confidence
    )

    # Rules (order matters: more specific first)
    if n >= 2 and total_hints >= HIGH_HINTS and score_pct < LOW_SCORE_PCT and (idle_ratio >= HIGH_IDLE_RATIO or total_skips >= HIGH_SKIP_FLAG):
        inferred_state, confidence = "frustrated", 0.8
        logger.info("Inferred session state: %s (confidence %.2f)", inferred_state, confidence)
        return inferred_state, confidence
    if latencies and avg_latency < LOW_LATENCY_MS and score_pct < LOW_SCORE_PCT and total_skips >= 1:
        inferred_state, confidence = "rushing", 0.75
        logger.info("Inferred session state: %s (confidence %.2f)", inferred_state, confidence)
        return inferred_state, confidence
    if score_pct >= 80 and total_hints <= 1 and (avg_confidence is None or avg_confidence >= 4):
        inferred_state, confidence = "confident", 0.8
        logger.info("Inferred session state: %s (confidence %.2f)", inferred_state, confidence)
        return inferred_state, confidence
    if n >= 2 and (total_hints >= 1 or total_edits > n) and score_pct < 70:
        inferred_state, confidence = "struggling", 0.7
        logger.info("Inferred session state: %s (confidence %.2f)", inferred_state, confidence)
        return inferred_state, confidence
    # Default
    inferred_state, confidence = "engaged", 0.6
    logger.info("Inferred session state: %s (confidence %.2f)", inferred_state, confidence)
    return inferred_state, confidence
