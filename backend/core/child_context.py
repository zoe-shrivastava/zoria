"""Child context for cultural/context flexibility in prompts.

Provides get_child_context() to load a child's preferences (language, tone, examples, etc.)
and build a short prompt block for injection into study guide, coach, and other LLM prompts.
"""

import logging
from typing import Optional, Dict, Any

from core.database import get_db

logger = logging.getLogger(__name__)


async def get_child_context(
    child_id: Optional[str] = None,
    language_override: Optional[str] = None
) -> Dict[str, Any]:
    """Load child preferences for prompt injection.
    
    Args:
        child_id: Child UUID. If None, returns defaults only.
        language_override: If provided, overrides child's preferred_language (e.g. from frontend).
    
    Returns:
        Dict with keys: language, interaction_tone, example_preferences, interests,
        sensitive_topics_to_avoid, prefer_indirect_guidance, prompt_block.
        prompt_block is a string to append to system prompts (only non-empty instructions).
    """
    defaults = {
        "language": "English",
        "interaction_tone": None,
        "example_preferences": None,
        "interests": None,
        "sensitive_topics_to_avoid": None,
        "prefer_indirect_guidance": False,
    }
    
    if not child_id:
        language = (language_override or defaults["language"]).strip() or defaults["language"]
        defaults["language"] = language
        defaults["prompt_block"] = _build_prompt_block(defaults)
        return defaults
    
    try:
        db = get_db()
        if db.pool is None:
            await db.connect()
        row = await db.fetchrow(
            """
            SELECT preferred_language, interaction_tone, example_preferences, interests,
                   sensitive_topics_to_avoid, prefer_indirect_guidance
            FROM children
            WHERE id = $1 AND is_active = TRUE
            """,
            child_id
        )
    except Exception as e:
        logger.warning("get_child_context: could not load child %s: %s", child_id, e)
        language = (language_override or defaults["language"]).strip() or defaults["language"]
        defaults["language"] = language
        defaults["prompt_block"] = _build_prompt_block(defaults)
        return defaults
    
    if not row:
        language = (language_override or defaults["language"]).strip() or defaults["language"]
        defaults["language"] = language
        defaults["prompt_block"] = _build_prompt_block(defaults)
        return defaults
    
    ctx = {
        "language": (language_override or row.get("preferred_language") or defaults["language"]).strip() or defaults["language"],
        "interaction_tone": row.get("interaction_tone"),
        "example_preferences": row.get("example_preferences"),
        "interests": row.get("interests"),
        "sensitive_topics_to_avoid": row.get("sensitive_topics_to_avoid"),
        "prefer_indirect_guidance": bool(row.get("prefer_indirect_guidance")),
    }
    ctx["prompt_block"] = _build_prompt_block(ctx)
    return ctx


def _build_prompt_block(ctx: Dict[str, Any]) -> str:
    """Build a short prompt block from context (language + cultural preferences)."""
    parts = []
    
    lang = (ctx.get("language") or "English").strip()
    parts.append(f"Preferred language: {lang}. All generated text (explanations, examples, hints) must be in {lang}.")
    
    tone = ctx.get("interaction_tone")
    if tone:
        parts.append(f"Tone: {tone} (e.g. {'warm and playful' if tone == 'playful' else 'clear and encouraging' if tone == 'encouraging' else 'direct and concise' if tone == 'direct' else 'gentle and supportive'}).")
    
    ex = ctx.get("example_preferences")
    if ex:
        parts.append(f"When giving examples, prefer: {ex}.")
    
    interests = ctx.get("interests")
    if interests and str(interests).strip():
        parts.append(f"Use the child's interests where relevant for examples: {interests.strip()}.")
    
    avoid = ctx.get("sensitive_topics_to_avoid")
    if avoid and str(avoid).strip():
        parts.append(f"Avoid these topics or references: {avoid.strip()}.")
    
    if ctx.get("prefer_indirect_guidance"):
        parts.append("For emotional or sensitive topics, use indirect, supportive phrasing rather than direct or clinical language.")
    
    if len(parts) <= 1:
        return parts[0] if parts else ""
    return " ".join(parts)
