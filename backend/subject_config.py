"""Centralized subject profile configuration loader.

Loads subject profiles from subject_profiles.json and provides
access to subject metadata for classification and question generation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_SUBJECT_PROFILES: Dict[str, Dict[str, Any]] | None = None
_SUBJECT_IDS: List[str] | None = None


def _load_subject_profiles() -> Dict[str, Dict[str, Any]]:
    """Load subject profiles from JSON file and index by subject_id."""
    global _SUBJECT_PROFILES
    if _SUBJECT_PROFILES is None:
        # Try multiple possible locations (works in both local and Docker)
        possible_paths = [
            # Option 1: Same directory as this file (backend/subject_profiles.json) - PRIMARY LOCATION
            Path(__file__).resolve().parent / "subject_profiles.json",
            # Option 2: If in Docker, at /app/subject_profiles.json
            Path("/app") / "subject_profiles.json",
            # Option 3: Relative to this file (zoria/backend/subject_config.py -> zoria/subject_profiles.json) - LEGACY
            Path(__file__).resolve().parent.parent / "subject_profiles.json",
            # Option 4: If running from zoria/ directory
            Path("subject_profiles.json"),
            # Option 5: Current working directory
            Path.cwd() / "subject_profiles.json",
            # Option 6: Root mount (Docker volume mount scenario) - LEGACY
            Path("/subject_profiles.json"),
        ]
        
        config_path = None
        for path in possible_paths:
            try:
                if path.exists():
                    config_path = path
                    logger.debug(f"Found subject_profiles.json at {config_path}")
                    break
            except Exception:
                continue
        
        if not config_path:
            # Log all attempted paths for debugging
            logger.error(f"subject_profiles.json not found. Tried: {[str(p) for p in possible_paths]}")
            logger.error(f"Current working directory: {Path.cwd()}")
            logger.error(f"__file__ location: {Path(__file__).resolve()}")
            _SUBJECT_PROFILES = {}
            return _SUBJECT_PROFILES
        
        try:
            with config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Index by subject_id for fast lookup
            _SUBJECT_PROFILES = {}
            for subject in data.get("subjects", []):
                subject_id = subject.get("subject_id")
                if subject_id:
                    _SUBJECT_PROFILES[subject_id] = subject
                else:
                    logger.warning(f"Subject missing subject_id: {subject}")
            
            logger.info(f"Loaded {len(_SUBJECT_PROFILES)} subject profiles from {config_path}")
            
        except Exception as e:
            logger.error(f"Failed to load subject_profiles.json from {config_path}: {e}", exc_info=True)
            _SUBJECT_PROFILES = {}
    
    return _SUBJECT_PROFILES


def get_subject_profile(subject_id: str) -> Optional[Dict[str, Any]]:
    """Get profile for a specific subject.
    
    Args:
        subject_id: Subject ID (e.g., 'mathematics', 'physics', 'other')
        
    Returns:
        Subject profile dict or None if not found
    """
    profiles = _load_subject_profiles()
    return profiles.get(subject_id)


def get_all_subject_ids() -> List[str]:
    """Get list of all subject IDs from profiles.
    
    Returns:
        List of subject IDs (e.g., ['mathematics', 'physics', 'other'])
    """
    global _SUBJECT_IDS
    if _SUBJECT_IDS is None:
        profiles = _load_subject_profiles()
        _SUBJECT_IDS = sorted(profiles.keys())
    return _SUBJECT_IDS


def get_subject_display_name(subject_id: str) -> str:
    """Get display name for a subject.
    
    Args:
        subject_id: Subject ID
        
    Returns:
        Display name or subject_id if not found
    """
    profile = get_subject_profile(subject_id)
    if profile:
        return profile.get("display_name", subject_id)
    return subject_id


def get_subject_for_classification() -> List[str]:
    """Get subject IDs for LLM classification (all subjects + 'other').
    
    Returns:
        List of subject IDs including 'other'
    """
    ids = get_all_subject_ids()
    # Ensure 'other' is always included
    if "other" not in ids:
        ids.append("other")
    return ids


def get_question_generation_config(subject_id: str) -> Dict[str, Any]:
    """Get question generation configuration for a subject.
    
    Args:
        subject_id: Subject ID
        
    Returns:
        Question generation config dict (with defaults if subject not found)
    """
    profile = get_subject_profile(subject_id)
    if profile:
        return profile.get("question_generation", {})
    
    # Default fallback
    logger.warning(f"No profile found for {subject_id}, using defaults")
    return {
        "preferred_question_types": ["multiple_choice", "short_answer"],
        "difficulty_levels": ["easy", "medium", "hard"],
        "cognitive_levels": ["recall", "comprehension"],
        "steps_required_for_hard": False,
        "allow_real_world_context": True,
        "requires_unit_handling": False
    }


def get_validation_rules(subject_id: str) -> Dict[str, Any]:
    """Get validation rules for a subject.
    
    Args:
        subject_id: Subject ID
        
    Returns:
        Validation rules dict
    """
    profile = get_subject_profile(subject_id)
    if profile:
        return profile.get("validation_rules", {})
    
    return {
        "must_have_single_correct_answer": True,
        "no_ambiguous_wording": True
    }


def get_llm_prompt_template(subject_id: str) -> Dict[str, str]:
    """Get LLM prompt template for a subject.
    
    Args:
        subject_id: Subject ID
        
    Returns:
        Dict with 'system_instructions' and 'format_rules'
    """
    profile = get_subject_profile(subject_id)
    if profile:
        return profile.get("llm_prompt_template", {})
    
    return {
        "system_instructions": "Generate clear, unambiguous assessment questions.",
        "format_rules": "Keep wording simple and age-appropriate."
    }


def normalize_subject_name(subject_name: str) -> str:
    """Normalize a subject name to subject_id.
    
    Args:
        subject_name: Subject name (e.g., "Mathematics", "Physics")
        
    Returns:
        Normalized subject_id (e.g., "mathematics", "physics")
    """
    if not subject_name:
        return "other"
    
    # Normalize: "Mathematics" -> "mathematics", "Physics" -> "physics"
    normalized = subject_name.lower().strip().replace(" ", "_")
    
    # Check if normalized name matches a known subject_id
    if normalized in get_all_subject_ids():
        return normalized
    
    # Try matching by display name
    for sid in get_all_subject_ids():
        profile = get_subject_profile(sid)
        if profile:
            display_name = profile.get("display_name", "").lower().strip()
            if display_name == subject_name.lower().strip() or display_name.replace(" ", "_") == normalized:
                return sid
    
    # If no match and not "uncategorized", return normalized
    if normalized != "uncategorized":
        return normalized
    
    return "other"
