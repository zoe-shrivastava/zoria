"""Service for generating detailed evaluation reports."""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal

from database.repositories.test_repository import TestRepository
from core.database import Database

logger = logging.getLogger(__name__)


def _to_float(value, default=0.0):
    """Convert value to float, handling Decimal types from database.
    
    Args:
        value: Value to convert (can be Decimal, float, int, or None)
        default: Default value if value is None
        
    Returns:
        float value
    """
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


class EvaluationReportService:
    """Service for generating student evaluation reports."""
    
    def __init__(self, db: Database):
        """Initialize evaluation report service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.test_repo = TestRepository(db)
    
    async def generate_report(
        self,
        child_id: str,
        days_back: int = 30,
        min_tests: int = 1,
        generate_study_guides: bool = True,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive evaluation report.
        
        Args:
            child_id: Child UUID
            days_back: Number of days to look back for tests
            min_tests: Minimum number of tests required for report
            generate_study_guides: Whether to generate study guides for focus areas
            language: Language for study guides and revision cards (e.g. 'English', 'Hindi'). None = English.
            
        Returns:
            Dictionary with report data
        """
        # Get all completed tests for the child
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        tests = await self.db.fetch(
            """
            SELECT id, title, completed_at, total_score, max_score, concept_id, metadata
            FROM tests
            WHERE child_id = $1 
                AND status = 'completed'
                AND completed_at >= $2
            ORDER BY completed_at DESC
            """,
            child_id, cutoff_date
        )
        
        if len(tests) < min_tests:
            return {
                'error': f'Insufficient data: Need at least {min_tests} completed test(s)',
                'tests_count': len(tests)
            }
        
        # Analyze all test responses
        all_questions = []
        concept_performance = defaultdict(lambda: {
            'total_questions': 0,
            'correct': 0,
            'total_score': 0.0,
            'max_score': 0.0,
            'error_types': defaultdict(int),
            'error_details': defaultdict(list),  # Store detailed feedback for each error type
            'misconceptions': [],
            'questions': []
        })
        
        # Track subject-level performance
        subject_performance = defaultdict(lambda: {
            'total_questions': 0,
            'correct': 0,
            'total_score': 0.0,
            'max_score': 0.0,
            'error_types': defaultdict(int),
            'concepts': set()  # Track unique concepts per subject
        })
        
        error_patterns = defaultdict(int)
        question_type_performance = defaultdict(lambda: {
            'total': 0,
            'correct': 0,
            'total_score': 0.0,
            'max_score': 0.0
        })
        
        for test in tests:
            test_with_questions = await self.test_repo.get_test_with_questions(test['id'])
            if not test_with_questions:
                continue
                
            for question in test_with_questions.get('questions', []):
                # Include all questions (answered and unanswered)
                # Unanswered questions are treated as incorrect
                has_answer = bool(question.get('answer'))
                is_correct = question.get('is_correct', False) if has_answer else False
                question_score = _to_float(question.get('score'), 0.0) if has_answer else 0.0
                
                all_questions.append(question)
                
                # Extract subject
                subject = None
                if question.get('metadata'):
                    subject = question['metadata'].get('subject')
                    blueprint = question['metadata'].get('blueprint', {})
                    if not subject and isinstance(blueprint, dict):
                        subject = blueprint.get('subject')
                    elif not subject and isinstance(blueprint, str):
                        try:
                            import json
                            blueprint_dict = json.loads(blueprint)
                            if isinstance(blueprint_dict, dict):
                                subject = blueprint_dict.get('subject')
                        except:
                            pass
                
                # Extract concept tags
                concept_tags = []
                if question.get('metadata'):
                    blueprint = question['metadata'].get('blueprint', {})
                    if isinstance(blueprint, dict):
                        concept_tags = blueprint.get('concept_tags', [])
                    elif isinstance(blueprint, str):
                        try:
                            import json
                            blueprint_dict = json.loads(blueprint)
                            if isinstance(blueprint_dict, dict):
                                concept_tags = blueprint_dict.get('concept_tags', [])
                        except:
                            pass
                    
                    # Fallback: try to get concept from metadata directly
                    if not concept_tags:
                        concept_name = question['metadata'].get('concept_name')
                        if concept_name:
                            concept_tags = [concept_name]
                
                # Fallback: topic-based tests store concept name in blueprint.metadata
                if not concept_tags and question.get('metadata'):
                    blueprint = question['metadata'].get('blueprint', {})
                    if isinstance(blueprint, dict):
                        concept_name = (blueprint.get('metadata') or {}).get('concept_name')
                        if concept_name:
                            concept_tags = [concept_name]
                    elif isinstance(blueprint, str):
                        try:
                            import json
                            blueprint_dict = json.loads(blueprint)
                            if isinstance(blueprint_dict, dict):
                                concept_name = (blueprint_dict.get('metadata') or {}).get('concept_name')
                                if concept_name:
                                    concept_tags = [concept_name]
                        except Exception:
                            pass
                
                # If still no concepts, use subject as a fallback concept
                if not concept_tags and subject:
                    concept_tags = [f"{subject}_General"]
                
                # Track subject performance
                if subject:
                    subj_perf = subject_performance[subject]
                    subj_perf['total_questions'] += 1
                    subj_perf['max_score'] += _to_float(question.get('max_score'), 1.0)
                    subj_perf['total_score'] += question_score
                    
                    if is_correct:
                        subj_perf['correct'] += 1
                    else:
                        # Track error type for unanswered or incorrect
                        if not has_answer:
                            subj_perf['error_types']['No_Answer'] += 1
                            error_patterns['No_Answer'] += 1
                        else:
                            error_type = question.get('error_type')
                            if error_type:
                                subj_perf['error_types'][error_type] += 1
                                error_patterns[error_type] += 1
                    
                    # Track concepts for this subject
                    for concept in concept_tags:
                        subj_perf['concepts'].add(concept)
                
                # Track concept performance
                for concept in concept_tags:
                    perf = concept_performance[concept]
                    perf['total_questions'] += 1
                    perf['max_score'] += _to_float(question.get('max_score'), 1.0)
                    perf['total_score'] += question_score
                    
                    if is_correct:
                        perf['correct'] += 1
                    else:
                        # Track error types for unanswered or incorrect
                        if not has_answer:
                            perf['error_types']['No_Answer'] += 1
                            error_patterns['No_Answer'] += 1
                            # Add explanation for No_Answer
                            perf['error_details']['No_Answer'].append({
                                'explanation': 'Question was not answered. Make sure to attempt all questions, even if unsure.',
                                'detailed_feedback': None
                            })
                        else:
                            error_type = question.get('error_type')
                            detailed_feedback = question.get('detailed_feedback')
                            question_score = _to_float(question.get('score'), 0.0)
                            max_score_q = _to_float(question.get('max_score'), 1.0)
                            is_partial = question_score > 0 and question_score < max_score_q
                            
                            # Debug logging for detailed_feedback collection
                            if detailed_feedback:
                                logger.debug(f"Found detailed_feedback for question: {detailed_feedback[:100]}...")
                            else:
                                logger.debug(f"No detailed_feedback for question (error_type={error_type}, score={question_score}/{max_score_q})")
                            
                            # Normalize error_type - handle string "None" or actual None
                            if error_type and isinstance(error_type, str):
                                error_type = error_type.strip()
                                # Treat "None", "null", empty string as no error type
                                if error_type.lower() in ['none', 'null', '']:
                                    error_type = None
                            
                            # Determine error type - use provided error_type or infer from score
                            if not error_type:
                                # For partially correct answers (score > 0 but < max_score), use a generic error type
                                if is_partial:
                                    error_type = 'Partial_Credit'  # Indicates partial correctness
                                else:
                                    error_type = 'Incorrect'  # Fallback for incorrect answers without specific error type
                            
                            # CRITICAL: Always collect detailed_feedback if available, regardless of error_type
                            # This ensures we capture feedback even when error_type is missing or generic
                            if detailed_feedback and detailed_feedback.strip():
                                # Use error_type for categorization, but always store the detailed feedback
                                if not error_type:
                                    error_type = 'Incorrect'  # Default category for detailed feedback
                                
                                perf['error_types'][error_type] = perf['error_types'].get(error_type, 0) + 1
                                error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
                                
                                perf['error_details'][error_type].append({
                                    'explanation': detailed_feedback,
                                    'question_text': question.get('text', '')[:150] if question.get('text') else None,
                                    'student_answer': question.get('answer', '')[:100] if question.get('answer') else None,
                                    'score': question_score,
                                    'max_score': max_score_q,
                                    'is_partial': is_partial
                                })
                                logger.debug(f"Stored detailed_feedback for error_type '{error_type}' in concept '{concept}': {detailed_feedback[:100]}...")
                            elif error_type:
                                # Only track error_type if we have one, even without detailed feedback
                                perf['error_types'][error_type] = perf['error_types'].get(error_type, 0) + 1
                                error_patterns[error_type] = error_patterns.get(error_type, 0) + 1
                                
                                # Always create an explanation entry, even if detailed_feedback is missing
                                # This ensures we have something to work with in the study guide
                                if is_partial:
                                    # For partial credit without detailed feedback, create a helpful explanation
                                    explanation = f'Answer was partially correct (scored {question_score:.2f} out of {max_score_q:.2f}). Review the solution steps and ensure all parts of the answer are complete and accurate.'
                                else:
                                    # For incorrect answers without detailed feedback, create a generic but helpful explanation
                                    explanation = f'Answer was incorrect. Review the concept and solution method. Check your calculations and ensure you understand the key principles involved.'
                                
                                perf['error_details'][error_type].append({
                                    'explanation': explanation,
                                    'question_text': question.get('text', '')[:150] if question.get('text') else None,
                                    'student_answer': question.get('answer', '')[:100] if question.get('answer') else None,
                                    'score': question_score,
                                    'max_score': max_score_q,
                                    'is_partial': is_partial
                                })
                                logger.debug(f"Created fallback explanation for error_type '{error_type}' in concept '{concept}' (no detailed_feedback available)")
                    
                    # Track misconceptions (only for answered questions)
                    if has_answer:
                        misconception = question.get('misconception')
                        if misconception:
                            perf['misconceptions'].append(misconception)
                    
                    blueprint = (question.get('metadata') or {}).get('blueprint') or {}
                    if isinstance(blueprint, str):
                        try:
                            blueprint = json.loads(blueprint) if blueprint else {}
                        except Exception:
                            blueprint = {}
                    expected = blueprint.get('expected_answer') or blueprint.get('correct_answer') if isinstance(blueprint, dict) else None
                    perf['questions'].append({
                        'question_id': question.get('question_id'),
                        'text': question.get('text', '')[:100] if question.get('text') else '',
                        'score': question_score,
                        'max_score': _to_float(question.get('max_score'), 1.0),
                        'is_correct': is_correct,
                        'has_answer': has_answer,
                        'error_type': question.get('error_type') if has_answer else 'No_Answer',
                        'misconception': question.get('misconception') if has_answer else None,
                        'detailed_feedback': question.get('detailed_feedback'),
                        'answer': question.get('answer'),
                        'expected_answer': expected,
                        '_test_metadata': test.get('metadata'),
                        '_subject': subject,  # per-question subject for topic-based focus area display
                    })
                
                # Track question type performance
                q_type = question.get('type', 'unknown')
                type_perf = question_type_performance[q_type]
                type_perf['total'] += 1
                type_perf['max_score'] += _to_float(question.get('max_score'), 1.0)
                type_perf['total_score'] += question_score
                if is_correct:
                    type_perf['correct'] += 1
        
        # Calculate strengths (concepts with >70% performance)
        strengths = []
        for concept, perf in concept_performance.items():
            if perf['total_questions'] >= 2:  # At least 2 questions
                accuracy = (perf['correct'] / perf['total_questions']) * 100
                score_percentage = (perf['total_score'] / perf['max_score']) * 100 if perf['max_score'] > 0 else 0
                avg_performance = (accuracy + score_percentage) / 2
                
                if avg_performance >= 70:
                    strengths.append({
                        'concept': concept,
                        'accuracy': round(accuracy, 1),
                        'score_percentage': round(score_percentage, 1),
                        'questions_count': perf['total_questions'],
                        'most_common_error': max(perf['error_types'].items(), key=lambda x: x[1])[0] if perf['error_types'] else None
                    })
        
        # Calculate areas of focus (concepts with <90% performance)
        areas_of_focus = []
        logger.info(f"Evaluating {len(concept_performance)} concepts for focus areas")
        for concept, perf in concept_performance.items():
            if perf['total_questions'] >= 2:
                accuracy = (perf['correct'] / perf['total_questions']) * 100
                score_percentage = (perf['total_score'] / perf['max_score']) * 100 if perf['max_score'] > 0 else 0
                avg_performance = (accuracy + score_percentage) / 2
                
                logger.debug(f"Concept '{concept}': accuracy={accuracy:.1f}%, score={score_percentage:.1f}%, avg={avg_performance:.1f}%, questions={perf['total_questions']}")
                
                if avg_performance < 90:
                    logger.info(f"Found focus area: {concept} (avg_performance={avg_performance:.1f}%, threshold <90%)")
                    # Get most common errors and misconceptions
                    common_errors = sorted(
                        perf['error_types'].items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]
                    
                    # Build enriched common errors with detailed feedback
                    enriched_errors = []
                    for error_type, count in common_errors:
                        # Skip invalid error types
                        if not error_type or (isinstance(error_type, str) and error_type.lower() in ['none', 'null', '']):
                            continue
                        
                        error_detail = {
                            'type': error_type,
                            'count': count,
                            'explanations': []
                        }
                        # Get detailed feedback for this error type
                        if error_type in perf['error_details']:
                            error_feedbacks = perf['error_details'][error_type]
                            # Get unique explanations (avoid duplicates)
                            seen_explanations = set()
                            for feedback in error_feedbacks[:5]:  # Increased to 5 to get more examples
                                if isinstance(feedback, dict):
                                    explanation = feedback.get('explanation', '')
                                else:
                                    explanation = str(feedback) if feedback else ''
                                
                                # Only add non-empty, unique explanations
                                if explanation and explanation.strip() and explanation not in seen_explanations:
                                    seen_explanations.add(explanation)
                                    error_detail['explanations'].append(explanation)
                        
                        # Only add error if we have explanations or it's a meaningful error type
                        if error_detail['explanations'] or error_type in ['No_Answer', 'Arithmetic', 'Conceptual', 'Procedural', 'Unit_Mismatch', 'Partial_Credit', 'Incorrect']:
                            enriched_errors.append(error_detail)
                    
                    unique_misconceptions = list(set(perf['misconceptions']))[:5]
                    # Derive subject from concept name (e.g. biology_General -> biology); for topic-based concepts use test metadata
                    area_subject = (concept.split('_')[0].strip() or None) if (concept and '_' in concept) else None
                    if not area_subject and concept:
                        area_subject = concept.strip()  # fallback to concept name
                    # Collect topics from test metadata and subject when topic-based (concept has no underscore)
                    topics_from_test = set()
                    need_subject_from_questions = area_subject == (concept or '').strip()
                    for q in perf['questions']:
                        meta = q.get('_test_metadata') or {}
                        if isinstance(meta, str):
                            try:
                                meta = json.loads(meta) if meta else {}
                            except Exception:
                                meta = {}
                        # For topic-based concepts, get real subject from test metadata or per-question (e.g. Physics, not concept name)
                        if need_subject_from_questions:
                            from_meta = (meta.get('subject') or '').strip()
                            from_question = (q.get('_subject') or '').strip() if isinstance(q.get('_subject'), str) else None
                            def _use_as_subject(val):
                                if not val: return False
                                return val.lower() != (concept or '').strip().lower()
                            if _use_as_subject(from_meta):
                                area_subject = from_meta
                                need_subject_from_questions = False
                            elif _use_as_subject(from_question):
                                area_subject = from_question
                                need_subject_from_questions = False
                        for t in (meta.get('topics') or []):
                            if t and str(t).strip():
                                topics_from_test.add(str(t).strip())
                    primary_topic = (list(topics_from_test)[0]) if topics_from_test else None
                    if not primary_topic and concept and '_' in concept:
                        # e.g. physics_General -> use part after underscore only if not "General"
                        after = concept.split('_', 1)[1].strip() if '_' in concept else ''
                        primary_topic = after if after and after.lower() != 'general' else None
                    if not primary_topic and concept and '_' not in concept:
                        # Topic-based tests: concept from blueprint (e.g. "Speed & Velocity") serves as topic
                        primary_topic = concept.strip()
                        topics_from_test.add(primary_topic)
                    areas_of_focus.append({
                        'concept': concept,
                        'subject': area_subject,
                        'topic': primary_topic,
                        'topics_from_test': list(topics_from_test),
                        'accuracy': round(accuracy, 1),
                        'score_percentage': round(score_percentage, 1),
                        'questions_count': perf['total_questions'],
                        'common_errors': enriched_errors,
                        'misconceptions': unique_misconceptions,
                        'sample_questions': perf['questions'][:3],  # Sample questions
                        'error_details': perf.get('error_details', {})  # Include error_details for direct access
                    })
        
        # Overall statistics
        # Note: all_questions now includes both answered and unanswered questions
        # Unanswered questions are treated as incorrect (is_correct=False, score=0)
        total_questions = len(all_questions)
        correct_count = sum(1 for q in all_questions if q.get('is_correct', False))
        total_score = sum(_to_float(q.get('score'), 0.0) for q in all_questions)
        max_score = sum(_to_float(q.get('max_score'), 1.0) for q in all_questions)
        
        overall_accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
        overall_score = (total_score / max_score * 100) if max_score > 0 else 0
        
        # Calculate subject-level performance
        subject_performance_summary = []
        for subject, perf in subject_performance.items():
            if perf['total_questions'] >= 1:  # At least 1 question
                accuracy = (perf['correct'] / perf['total_questions']) * 100
                score_percentage = (perf['total_score'] / perf['max_score']) * 100 if perf['max_score'] > 0 else 0
                avg_performance = (accuracy + score_percentage) / 2
                
                # Get most common errors
                common_errors = sorted(
                    perf['error_types'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                
                subject_performance_summary.append({
                    'subject': subject,
                    'accuracy': round(accuracy, 1),
                    'score_percentage': round(score_percentage, 1),
                    'avg_performance': round(avg_performance, 1),
                    'total_questions': perf['total_questions'],
                    'correct_count': perf['correct'],
                    'total_score': round(perf['total_score'], 1),
                    'max_score': round(perf['max_score'], 1),
                    'concepts_count': len(perf['concepts']),
                    'common_errors': [{'type': e[0], 'count': e[1]} for e in common_errors]
                })
        
        # Sort subject performance by average performance
        subject_performance_summary.sort(key=lambda x: x['avg_performance'])
        
        # Sort strengths and areas of focus
        strengths.sort(key=lambda x: x['score_percentage'], reverse=True)
        areas_of_focus.sort(key=lambda x: x['score_percentage'])
        
        logger.info(f"📊 Report Summary: {len(strengths)} strengths, {len(areas_of_focus)} areas of focus")
        if areas_of_focus:
            focus_list = [f"{a['concept']} ({a['score_percentage']}%)" for a in areas_of_focus[:5]]
            logger.info(f"   Focus areas: {focus_list}")
        logger.info(f"   generate_study_guides={generate_study_guides}, areas_of_focus count={len(areas_of_focus)}")
        
        # Require topic from test for every focus area when generating study guides (no fallbacks)
        if generate_study_guides and areas_of_focus:
            for area in areas_of_focus[:5]:
                has_topic = area.get('topic') or (area.get('topics_from_test') and len(area.get('topics_from_test', [])) > 0)
                if not has_topic:
                    raise ValueError(
                        f"Focus area concept '{area.get('concept')}' has no topic from test. "
                        "Tests must be created with subject+topics so metadata.topics is set."
                    )
        
        # Remove study guides for concepts no longer in areas of focus (e.g. test deleted/reopened)
        await self._delete_orphan_study_guides(child_id, areas_of_focus)
        
        # Study guides: either return placeholders (generating in background) or fill from DB
        study_guide_links = []
        if generate_study_guides and areas_of_focus:
            # Return report immediately with placeholders; API will run generation in background in parallel
            study_guide_links = [
                {
                    'concept': area['concept'],
                    'subject': area.get('subject'),
                    'guide_id': None,
                    'generating': True,
                    'focus_area': area['score_percentage']
                }
                for area in areas_of_focus[:5]
            ]
            logger.info(f"Returning report with {len(study_guide_links)} study guide placeholders (generating in background)")
        elif not generate_study_guides and areas_of_focus:
            study_guide_links = await self._get_existing_study_guide_links(child_id, areas_of_focus)
            logger.info(f"Filled {len(study_guide_links)} study guide links from DB")
        else:
            if not generate_study_guides:
                logger.info("Study guide generation is disabled")
            if not areas_of_focus:
                logger.info("No areas of focus found, skipping study guide generation")
        
        # Build recent session states (inferred_session_state from test metadata)
        session_states = []
        for test in tests:
            meta = test.get('metadata')
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            state = (meta or {}).get('inferred_session_state')
            if state:
                session_states.append({
                    'test_id': str(test['id']),
                    'title': test.get('title'),
                    'completed_at': test.get('completed_at'),
                    'inferred_session_state': state
                })
        
        # Enrich session_states with per-test stats (questions answered, unanswered, correct/partial/incorrect, time, edits, hints)
        if session_states:
            test_ids = [s['test_id'] for s in session_states]
            try:
                rows = await self.db.fetch(
                    """
                    SELECT
                        tr.test_id,
                        SUM(CASE WHEN tr.answer IS NOT NULL AND TRIM(COALESCE(tr.answer, '')) <> '' THEN 1 ELSE 0 END)::int AS questions_answered,
                        SUM(CASE WHEN tr.is_correct THEN 1 ELSE 0 END)::int AS correct_count,
                        SUM(CASE WHEN tr.is_correct = false AND tr.score > 0 AND tq.max_score > 0 AND tr.score < tq.max_score THEN 1 ELSE 0 END)::int AS partial_count,
                        SUM(CASE WHEN tr.is_correct = false AND (tr.score = 0 OR tr.score IS NULL OR tr.score >= COALESCE(tq.max_score, 1)) THEN 1 ELSE 0 END)::int AS incorrect_count,
                        COALESCE(SUM(tr.time_spent_seconds), 0)::int AS total_time_seconds,
                        COALESCE(SUM(COALESCE((tr.metadata->>'edit_count')::int, 0)), 0)::int AS total_edits,
                        COALESCE(SUM(COALESCE((tr.metadata->>'hints_accessed')::int, 0)), 0)::int AS total_hints
                    FROM test_responses tr
                    LEFT JOIN test_questions tq ON tq.test_id = tr.test_id
                        AND (tq.question_id = tr.question_id OR tq.original_question_id = tr.question_id)
                    WHERE tr.test_id::text = ANY($1)
                    GROUP BY tr.test_id
                    """,
                    test_ids
                )
                stats_by_test = {str(r['test_id']): dict(r) for r in rows}
                total_questions_rows = await self.db.fetch(
                    """
                    SELECT test_id, COUNT(*)::int AS total_questions
                    FROM test_questions
                    WHERE test_id::text = ANY($1)
                    GROUP BY test_id
                    """,
                    test_ids
                )
                total_by_test = {str(r['test_id']): r['total_questions'] for r in total_questions_rows}
                for s in session_states:
                    st = stats_by_test.get(s['test_id']) or {}
                    total_q = total_by_test.get(s['test_id'], 0)
                    answered = st.get('questions_answered', 0)
                    s['questions_answered'] = answered
                    s['unanswered_count'] = max(0, total_q - answered)
                    s['correct_count'] = st.get('correct_count', 0)
                    s['partial_count'] = st.get('partial_count', 0)
                    s['incorrect_count'] = st.get('incorrect_count', 0)
                    s['total_time_seconds'] = st.get('total_time_seconds', 0)
                    s['total_edits'] = st.get('total_edits', 0)
                    s['total_hints'] = st.get('total_hints', 0)
            except Exception as e:
                logger.warning("Could not load per-test stats for session states: %s", e)
        
        return {
            'child_id': child_id,
            'generated_at': datetime.utcnow().isoformat(),
            'period_days': days_back,
            'tests_analyzed': len(tests),
            'session_states': session_states,
            'overall_performance': {
                'total_questions': total_questions,
                'correct_count': correct_count,
                'accuracy_percentage': round(overall_accuracy, 1),
                'score_percentage': round(overall_score, 1),
                'total_score': round(total_score, 1),
                'max_score': round(max_score, 1)
            },
            'subject_performance': subject_performance_summary,
            'strengths': strengths,
            'areas_of_focus': areas_of_focus,
            'error_patterns': dict(error_patterns),
            'question_type_performance': {
                q_type: {
                    'accuracy': round((perf['correct'] / perf['total'] * 100) if perf['total'] > 0 else 0, 1),
                    'score_percentage': round((perf['total_score'] / perf['max_score'] * 100) if perf['max_score'] > 0 else 0, 1),
                    'total_questions': perf['total']
                }
                for q_type, perf in question_type_performance.items()
            },
            'study_guide_links': study_guide_links,
            'recommendations': self._generate_recommendations(strengths, areas_of_focus, error_patterns)
        }

    async def _delete_orphan_study_guides(
        self, child_id: str, areas_of_focus: List[Dict]
    ) -> None:
        """Delete study guides for this child whose concept is no longer in areas of focus.
        E.g. when the only Physics test was deleted or reopened, remove Physics study guide(s).
        """
        try:
            table_check = await self.db.fetchrow(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'study_guides')"
            )
            if not table_check or not table_check['exists']:
                return
        except Exception as e:
            logger.warning("Could not check study_guides table for orphan cleanup: %s", e)
            return
        focus_concepts = [a.get('concept', '') or '' for a in areas_of_focus if (a.get('concept') or '').strip()]
        try:
            if not focus_concepts:
                deleted = await self.db.execute(
                    "DELETE FROM study_guides WHERE child_id = $1",
                    child_id
                )
                if deleted and deleted != "DELETE 0":
                    logger.info("Deleted orphan study guides for child %s (no current focus areas)", child_id)
            else:
                deleted = await self.db.execute(
                    """
                    DELETE FROM study_guides
                    WHERE child_id = $1 AND NOT (concept_name = ANY($2::text[]))
                    """,
                    child_id, focus_concepts
                )
                if deleted and deleted != "DELETE 0":
                    logger.info("Deleted orphan study guides for child %s (concepts no longer in focus)", child_id)
        except Exception as e:
            logger.warning("Failed to delete orphan study guides for child %s: %s", child_id, e)

    async def _get_existing_study_guide_links(
        self, child_id: str, areas_of_focus: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Fill study_guide_links from DB for focus areas (when not generating)."""
        links = []
        for area in areas_of_focus[:5]:
            concept = area.get('concept', '') or ''
            focus_pct = area.get('score_percentage')
            focus_area = f"Performance: {focus_pct}%" if focus_pct is not None else "General"
            row = await self.db.fetchrow(
                """
                SELECT id FROM study_guides
                WHERE child_id = $1 AND concept_name = $2
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                child_id, concept
            )
            if row:
                links.append({
                    'concept': concept,
                    'subject': area.get('subject'),
                    'guide_id': str(row['id']),
                    'focus_area': focus_pct
                })
        return links

    async def _generate_one_study_guide(
        self,
        study_guide_service: Any,
        child_id: str,
        area: Dict[str, Any],
        grade_level: Optional[str],
        language: Optional[str],
        tests: List[Dict],
    ) -> None:
        """Generate a single study guide (for parallel execution). On failure logs and returns."""
        concept_name = area.get('concept', '') or ''
        subject = area.get('subject')
        if not subject:
            subject = (concept_name.split('_')[0].strip() or None) if concept_name and '_' in concept_name else (concept_name.strip() or None)
        if not subject and tests:
            test_with_questions = await self.test_repo.get_test_with_questions(tests[0]['id'])
            if test_with_questions and test_with_questions.get('questions'):
                first_q = test_with_questions['questions'][0]
                if first_q.get('metadata'):
                    subject = first_q['metadata'].get('subject')
        error_details = area.get('error_details', {}) or {}
        common_errors_list = []
        if area.get('common_errors'):
            for e in area['common_errors']:
                if isinstance(e, dict):
                    error_type = e.get('type', str(e))
                    explanations = e.get('explanations', [])
                    count = e.get('count', 1)
                    if explanations:
                        error_desc = f"{error_type}: {explanations[0]}"
                        if len(explanations) > 1:
                            additional = explanations[1:3]
                            error_desc += f" | Other examples: {' | '.join(additional)}" if len(additional) > 1 else f" | Also seen: {additional[0]}"
                        common_errors_list.append(error_desc)
                    elif error_type in error_details and error_details[error_type]:
                        direct_explanations = []
                        for detail in error_details[error_type][:5]:
                            exp = detail.get('explanation', '') if isinstance(detail, dict) else (str(detail) or '')
                            if exp and exp.strip():
                                direct_explanations.append(exp)
                        if direct_explanations:
                            error_desc = f"{error_type}: {direct_explanations[0]}"
                            if len(direct_explanations) > 1:
                                error_desc += f" | Also seen: {direct_explanations[1]}"
                            common_errors_list.append(error_desc)
                            continue
                    if error_type and error_type.lower() in ['none', 'null', '']:
                        continue
                    if error_type == 'No_Answer':
                        error_desc = f"{error_type}: Questions were not answered. Make sure to attempt all questions, even if unsure."
                    elif error_type == 'Arithmetic':
                        error_desc = f"{error_type}: Calculation errors occurred {count} time(s). Double-check your arithmetic."
                    elif error_type == 'Conceptual':
                        error_desc = f"{error_type}: Conceptual misunderstanding occurred {count} time(s). Review the fundamental concepts."
                    elif error_type == 'Procedural':
                        error_desc = f"{error_type}: Procedural errors occurred {count} time(s). Review the step-by-step method."
                    elif error_type == 'Unit_Mismatch':
                        error_desc = f"{error_type}: Unit errors occurred {count} time(s). Pay attention to units."
                    elif error_type == 'Partial_Credit':
                        error_desc = f"{error_type}: Answers were partially correct {count} time(s). Review solution steps."
                    elif error_type == 'Incorrect':
                        error_desc = f"{error_type}: Answers were incorrect {count} time(s). Review the concept and practice."
                    else:
                        error_desc = f"{error_type}: This error occurred {count} time(s). Review and practice."
                    common_errors_list.append(error_desc)
                else:
                    error_str = str(e)
                    if error_str and error_str not in ['None', ''] and ':' not in error_str:
                        msg = (f"{error_str}: Questions were not answered. Make sure to attempt all questions."
                               if error_str == 'No_Answer' else f"{error_str}: Review this error type and practice similar problems.")
                        common_errors_list.append(msg)
                    elif error_str and ':' in error_str:
                        common_errors_list.append(error_str)
        common_errors_list = [x for x in common_errors_list if x and x.strip() and x.lower() not in ['none', 'null', '']]
        try:
            await study_guide_service.generate_study_guide(
                child_id=child_id,
                concept_name=area['concept'],
                focus_area=f"Performance: {area['score_percentage']}%",
                grade_level=grade_level,
                subject=subject,
                common_errors=common_errors_list or None,
                misconceptions=area.get('misconceptions', []),
                sample_questions=area.get('sample_questions', []),
                language=language,
                topic_from_test=area.get('topic'),
                topics_from_test=area.get('topics_from_test'),
            )
            logger.info(f"✅ Background: generated study guide for '{area['concept']}'")
        except Exception as e:
            logger.error(f"❌ Background: failed study guide for '{area['concept']}': {e}", exc_info=True)

    async def generate_study_guides_background(
        self,
        child_id: str,
        areas_of_focus: List[Dict[str, Any]],
        language: Optional[str],
        days_back: int = 30,
    ) -> None:
        """Generate study guides for focus areas in parallel (called from API background task)."""
        if not areas_of_focus:
            return
        try:
            from services.study_guide_service import StudyGuideService
            study_guide_service = StudyGuideService(self.db)
            child = await self.db.fetchrow("SELECT grade FROM children WHERE id = $1", child_id)
            grade_level = child['grade'] if child else None
            cutoff = datetime.utcnow() - timedelta(days=days_back)
            tests = await self.db.fetch(
                """
                SELECT id, title, completed_at, total_score, max_score, concept_id, metadata
                FROM tests
                WHERE child_id = $1 AND status = 'completed' AND completed_at >= $2
                ORDER BY completed_at DESC
                """,
                child_id, cutoff
            )
            tasks = [
                self._generate_one_study_guide(
                    study_guide_service, child_id, area, grade_level, language, list(tests)
                )
                for area in areas_of_focus[:5]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.error(f"Background study guide task {i} failed: {r}", exc_info=True)
            logger.info(f"Background study guide generation completed for {len(areas_of_focus[:5])} areas")
        except Exception as e:
            logger.error(f"Error in generate_study_guides_background: {e}", exc_info=True)
    
    def _generate_recommendations(
        self,
        strengths: List[Dict],
        areas_of_focus: List[Dict],
        error_patterns: Dict[str, int]
    ) -> List[str]:
        """Generate personalized recommendations."""
        recommendations = []
        
        # Recommendations based on areas of focus
        if areas_of_focus:
            top_focus = areas_of_focus[0]
            recommendations.append(
                f"Focus on improving {top_focus['concept']} - "
                f"current performance: {top_focus['score_percentage']}%"
            )
            
            if top_focus['common_errors']:
                top_error = top_focus['common_errors'][0]
                recommendations.append(
                    f"Most common error type: {top_error['type']} "
                    f"({top_error['count']} occurrences)"
                )
        
        # Recommendations based on error patterns
        if error_patterns:
            most_common_error = max(error_patterns.items(), key=lambda x: x[1])
            if most_common_error[1] > 3:
                recommendations.append(
                    f"Practice more on {most_common_error[0].lower()} errors - "
                    f"appeared {most_common_error[1]} times"
                )
        
        # Positive reinforcement
        if strengths:
            recommendations.append(
                f"Great work on {strengths[0]['concept']}! "
                f"Keep practicing to maintain this strength."
            )
        
        return recommendations
