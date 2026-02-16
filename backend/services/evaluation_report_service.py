"""Service for generating detailed evaluation reports."""

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
            SELECT id, title, completed_at, total_score, max_score, concept_id
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
                        'expected_answer': expected
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
        
        # Calculate areas of focus (concepts with <60% performance)
        areas_of_focus = []
        logger.info(f"Evaluating {len(concept_performance)} concepts for focus areas")
        for concept, perf in concept_performance.items():
            if perf['total_questions'] >= 2:
                accuracy = (perf['correct'] / perf['total_questions']) * 100
                score_percentage = (perf['total_score'] / perf['max_score']) * 100 if perf['max_score'] > 0 else 0
                avg_performance = (accuracy + score_percentage) / 2
                
                logger.debug(f"Concept '{concept}': accuracy={accuracy:.1f}%, score={score_percentage:.1f}%, avg={avg_performance:.1f}%, questions={perf['total_questions']}")
                
                if avg_performance < 60:
                    logger.info(f"Found focus area: {concept} (avg_performance={avg_performance:.1f}%)")
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
                    # Derive subject from concept name once (e.g. biology_General -> biology) so study guide always gets correct subject
                    area_subject = (concept.split('_')[0].strip() or None) if (concept and '_' in concept) else (concept.strip() or None)
                    areas_of_focus.append({
                        'concept': concept,
                        'subject': area_subject,
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
        
        # Generate study guides for focus areas
        study_guide_links = []
        if generate_study_guides and areas_of_focus:
            logger.info(f"✅ Starting study guide generation for {len(areas_of_focus)} focus areas")
            try:
                from services.study_guide_service import StudyGuideService
                study_guide_service = StudyGuideService(self.db)
                
                # Get child info for grade level
                child = await self.db.fetchrow(
                    "SELECT grade FROM children WHERE id = $1",
                    child_id
                )
                grade_level = child['grade'] if child else None
                logger.info(f"Child grade level: {grade_level}")
                
                # Subject will be derived per area from the area's concept (e.g. biology_General -> biology)
                for idx, area in enumerate(areas_of_focus[:5], 1):  # Generate guides for top 5 focus areas
                    try:
                        concept_name = area.get('concept', '') or ''
                        # Use subject stored on area (derived from concept when building areas); fallback to deriving from concept_name
                        subject = area.get('subject')
                        if not subject:
                            subject = (concept_name.split('_')[0].strip() or None) if concept_name and '_' in concept_name else (concept_name.strip() or None)
                        if not subject and tests:
                            test_with_questions = await self.test_repo.get_test_with_questions(tests[0]['id'])
                            if test_with_questions and test_with_questions.get('questions'):
                                first_q = test_with_questions['questions'][0]
                                if first_q.get('metadata'):
                                    subject = first_q['metadata'].get('subject')
                        logger.info(f"📚 [{idx}/{min(5, len(areas_of_focus))}] Generating study guide for: '{area['concept']}' (subject={subject})")
                        logger.info(f"   Performance: {area.get('score_percentage', 'N/A')}%, Questions: {area.get('questions_count', 0)}")
                        logger.info(f"   Common errors: {len(area.get('common_errors', []))}, Misconceptions: {len(area.get('misconceptions', []))}")
                        
                        # Debug: Log error_details availability
                        error_details = area.get('error_details', {})
                        logger.info(f"   Error details available for {len(error_details)} error types: {list(error_details.keys())}")
                        for err_type, details in error_details.items():
                            logger.info(f"     - {err_type}: {len(details)} explanations")
                            if details:
                                logger.info(f"       First explanation: {details[0].get('explanation', 'N/A')[:100]}...")
                        
                        # Extract common errors with detailed explanations
                        common_errors_list = []
                        if area.get('common_errors'):
                            for e in area['common_errors']:
                                if isinstance(e, dict):
                                    error_type = e.get('type', str(e))
                                    explanations = e.get('explanations', [])
                                    count = e.get('count', 1)
                                    # Create enriched error description
                                    if explanations and len(explanations) > 0:
                                        # Combine error type with all unique explanations
                                        # Use the first (most common) explanation as primary
                                        error_desc = f"{error_type}: {explanations[0]}"
                                        # If there are additional unique explanations, include them
                                        if len(explanations) > 1:
                                            additional = explanations[1:3]  # Include up to 2 more examples
                                            if len(additional) == 1:
                                                error_desc += f" | Also seen: {additional[0]}"
                                            else:
                                                error_desc += f" | Other examples: {' | '.join(additional)}"
                                        common_errors_list.append(error_desc)
                                    else:
                                        # No detailed explanations available - try to get from error_details directly
                                        # This handles cases where explanations weren't properly extracted
                                        error_details = area.get('error_details', {})
                                        logger.debug(f"   No explanations in enriched_errors for '{error_type}', checking error_details directly...")
                                        logger.debug(f"   Available error_details keys: {list(error_details.keys())}")
                                        if error_type in error_details and error_details[error_type]:
                                            # Get explanations directly from error_details
                                            direct_explanations = []
                                            logger.debug(f"   Found {len(error_details[error_type])} entries in error_details['{error_type}']")
                                            for detail in error_details[error_type][:5]:  # Get up to 5
                                                if isinstance(detail, dict):
                                                    exp = detail.get('explanation', '')
                                                    logger.debug(f"     Explanation from dict: {exp[:100] if exp else 'EMPTY'}...")
                                                else:
                                                    exp = str(detail) if detail else ''
                                                    logger.debug(f"     Explanation from string: {exp[:100] if exp else 'EMPTY'}...")
                                                if exp and exp.strip():
                                                    direct_explanations.append(exp)
                                            if direct_explanations:
                                                logger.info(f"   ✅ Found {len(direct_explanations)} explanations in error_details for '{error_type}'")
                                                error_desc = f"{error_type}: {direct_explanations[0]}"
                                                if len(direct_explanations) > 1:
                                                    additional = direct_explanations[1:3]  # Include up to 2 more
                                                    if len(additional) == 1:
                                                        error_desc += f" | Also seen: {additional[0]}"
                                                    else:
                                                        error_desc += f" | Other examples: {' | '.join(additional)}"
                                                common_errors_list.append(error_desc)
                                                continue
                                            else:
                                                logger.warning(f"   ⚠️ error_details['{error_type}'] exists but has no valid explanations")
                                        else:
                                            logger.warning(f"   ⚠️ No error_details found for error_type '{error_type}' (available: {list(error_details.keys())})")
                                        
                                        # Fallback: provide helpful message based on error type
                                        # Skip "None" as an error type - it's not meaningful
                                        if error_type and error_type.lower() in ['none', 'null', '']:
                                            continue  # Skip invalid error types
                                        
                                        if error_type == 'No_Answer':
                                            error_desc = f"{error_type}: Questions were not answered. Make sure to attempt all questions, even if unsure. Partial credit may be given for showing work."
                                        elif error_type == 'Arithmetic':
                                            error_desc = f"{error_type}: Calculation errors occurred {count} time(s). Double-check your arithmetic, especially when working with decimals or fractions."
                                        elif error_type == 'Conceptual':
                                            error_desc = f"{error_type}: Conceptual misunderstanding occurred {count} time(s). Review the fundamental concepts and definitions."
                                        elif error_type == 'Procedural':
                                            error_desc = f"{error_type}: Procedural errors occurred {count} time(s). Review the step-by-step problem-solving method."
                                        elif error_type == 'Unit_Mismatch':
                                            error_desc = f"{error_type}: Unit errors occurred {count} time(s). Pay attention to units in calculations and final answers."
                                        elif error_type == 'Partial_Credit':
                                            error_desc = f"{error_type}: Answers were partially correct {count} time(s). Review the solution steps and ensure all parts of answers are complete and accurate."
                                        elif error_type == 'Incorrect':
                                            error_desc = f"{error_type}: Answers were incorrect {count} time(s). Review the concept and practice similar problems."
                                        else:
                                            error_desc = f"{error_type}: This error occurred {count} time(s). Review the concept and practice similar problems."
                                        common_errors_list.append(error_desc)
                                else:
                                    # If it's already a string, check if it needs enrichment
                                    error_str = str(e)
                                    if ':' not in error_str and error_str not in ['None', '']:
                                        # It's just an error type, add helpful message
                                        if error_str == 'No_Answer':
                                            common_errors_list.append(f"{error_str}: Questions were not answered. Make sure to attempt all questions, even if unsure.")
                                        else:
                                            common_errors_list.append(f"{error_str}: Review this error type and practice similar problems.")
                                    else:
                                        common_errors_list.append(error_str)
                        
                        # Filter out None, empty strings, and invalid error names
                        common_errors_list = [e for e in common_errors_list if e and e.strip() and e.lower() not in ['none', 'null', '']]
                        
                        if not common_errors_list:
                            logger.warning(f"No valid common errors extracted for {area['concept']}, area['common_errors']={area.get('common_errors')}")
                        
                        logger.info(f"   Calling study_guide_service.generate_study_guide()...")
                        logger.info(f"   Passing {len(common_errors_list)} common errors: {common_errors_list[:2]}...")
                        # Debug: Log what we're actually passing
                        for i, err in enumerate(common_errors_list[:3], 1):
                            logger.info(f"     Error {i}: {err[:150]}...")
                        guide = await study_guide_service.generate_study_guide(
                            child_id=child_id,
                            concept_name=area['concept'],
                            focus_area=f"Performance: {area['score_percentage']}%",
                            grade_level=grade_level,
                            subject=subject,
                            common_errors=common_errors_list if common_errors_list else None,
                            misconceptions=area.get('misconceptions', []),
                            sample_questions=area.get('sample_questions', []),
                            language=language,
                        )
                        
                        logger.info(f"✅ Successfully generated study guide for '{area['concept']}'")
                        logger.info(f"   Guide ID: {guide.get('id')}, is_new: {guide.get('is_new', 'unknown')}")
                        
                        study_guide_links.append({
                            'concept': area['concept'],
                            'guide_id': guide['id'],
                            'focus_area': area['score_percentage']
                        })
                    except Exception as e:
                        logger.error(f"❌ Failed to generate study guide for '{area['concept']}': {e}", exc_info=True)
                        import traceback
                        logger.error(f"   Full traceback: {traceback.format_exc()}")
            except Exception as e:
                logger.error(f"Error initializing study guide service: {e}", exc_info=True)
        else:
            if not generate_study_guides:
                logger.info("Study guide generation is disabled")
            if not areas_of_focus:
                logger.info("No areas of focus found, skipping study guide generation")
        
        logger.info(f"Generated {len(study_guide_links)} study guides")
        
        return {
            'child_id': child_id,
            'generated_at': datetime.utcnow().isoformat(),
            'period_days': days_back,
            'tests_analyzed': len(tests),
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
