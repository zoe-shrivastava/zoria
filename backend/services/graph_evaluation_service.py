"""Service for evaluating graph/diagram drawings submitted by students."""

import logging
import json
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class GraphEvaluationService:
    """Service for evaluating student-drawn graphs against expected graphs."""
    
    def __init__(self, llm_service=None):
        """Initialize graph evaluation service.
        
        Args:
            llm_service: Optional LLM service for AI-based evaluation
        """
        self.llm_service = llm_service
    
    def is_drawing_answer(self, answer: str) -> bool:
        """Check if an answer is a drawing (JSON format from Fabric.js).
        
        Args:
            answer: Student answer string
            
        Returns:
            True if answer appears to be drawing data
        """
        if not answer or not isinstance(answer, str):
            return False
        
        try:
            data = json.loads(answer)
            # Fabric.js canvas data has 'objects' array
            if isinstance(data, dict) and 'objects' in data:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
        
        return False
    
    async def evaluate_drawing(
        self,
        user_drawing_data: Dict[str, Any],
        expected_graph_info: Optional[Dict[str, Any]] = None,
        question_text: Optional[str] = None,
        max_score: float = 1.0
    ) -> Tuple[bool, float, Optional[str]]:
        """Evaluate a student's drawn graph.
        
        Args:
            user_drawing_data: Drawing data from Fabric.js (JSON)
            expected_graph_info: Expected graph information (from question metadata)
            question_text: Question text for context
            max_score: Maximum score for this question
            
        Returns:
            Tuple of (is_correct, score, feedback)
        """
        try:
            # Extract drawing features
            drawing_features = self._extract_drawing_features(user_drawing_data)
            
            # If we have expected graph info, compare directly
            if expected_graph_info:
                is_correct, score, feedback = self._compare_with_expected(
                    drawing_features, expected_graph_info, max_score
                )
                return is_correct, score, feedback
            
            # Otherwise, use LLM-based evaluation if available
            if self.llm_service and question_text:
                return await self._evaluate_with_llm(
                    drawing_features, question_text, max_score
                )
            
            # Fallback: basic check - if drawing has paths, give partial credit
            if drawing_features.get('has_paths', False):
                return False, max_score * 0.5, "Drawing detected but cannot verify correctness without expected graph"
            
            return False, 0.0, "No drawing detected"
            
        except Exception as e:
            logger.error(f"Error evaluating drawing: {e}", exc_info=True)
            return False, 0.0, f"Error evaluating drawing: {str(e)}"
    
    def _extract_drawing_features(
        self, 
        drawing_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract features from drawing data.
        
        Args:
            drawing_data: Fabric.js canvas JSON data
            
        Returns:
            Dictionary of extracted features
        """
        features = {
            'has_paths': False,
            'path_count': 0,
            'total_path_length': 0,
            'bounding_box': None,
            'center_point': None,
        }
        
        objects = drawing_data.get('objects', [])
        
        # Filter out grid lines and axes (they have selectable: false)
        drawing_objects = [
            obj for obj in objects
            if obj.get('selectable') is not False or obj.get('evented') is not False
        ]
        
        if not drawing_objects:
            return features
        
        features['has_paths'] = True
        features['path_count'] = len(drawing_objects)
        
        # Calculate bounding box
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for obj in drawing_objects:
            # Get object bounds
            left = obj.get('left', 0)
            top = obj.get('top', 0)
            width = obj.get('width', 0)
            height = obj.get('height', 0)
            
            # For paths, use path coordinates
            if obj.get('type') == 'path':
                path = obj.get('path', [])
                if path:
                    for point in path:
                        if isinstance(point, list) and len(point) >= 2:
                            x, y = point[1], point[2] if len(point) > 2 else point[0]
                            min_x = min(min_x, x)
                            min_y = min(min_y, y)
                            max_x = max(max_x, x)
                            max_y = max(max_y, y)
            else:
                # For other objects, use bounding box
                min_x = min(min_x, left)
                min_y = min(min_y, top)
                max_x = max(max_x, left + width)
                max_y = max(max_y, top + height)
        
        if min_x != float('inf'):
            features['bounding_box'] = {
                'min_x': min_x,
                'min_y': min_y,
                'max_x': max_x,
                'max_y': max_y,
                'width': max_x - min_x,
                'height': max_y - min_y,
            }
            features['center_point'] = {
                'x': (min_x + max_x) / 2,
                'y': (min_y + max_y) / 2,
            }
        
        return features
    
    def _compare_with_expected(
        self,
        drawing_features: Dict[str, Any],
        expected_graph_info: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str]]:
        """Compare drawing features with expected graph.
        
        Args:
            drawing_features: Extracted features from student drawing
            expected_graph_info: Expected graph information
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score, feedback)
        """
        # Basic validation: check if drawing exists
        if not drawing_features.get('has_paths', False):
            return False, 0.0, "No drawing detected"
        
        # For now, give partial credit if drawing exists
        # TODO: Implement more sophisticated comparison
        # - Compare key points (vertex, intercepts)
        # - Compare shape characteristics
        # - Use coordinate-based matching
        
        return False, max_score * 0.7, "Drawing detected. Manual review recommended for accurate grading."
    
    async def _evaluate_with_llm(
        self,
        drawing_features: Dict[str, Any],
        question_text: str,
        max_score: float
    ) -> Tuple[bool, float, Optional[str]]:
        """Evaluate drawing using LLM.
        
        Args:
            drawing_features: Extracted features from student drawing
            question_text: Question text for context
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score, feedback)
        """
        if not self.llm_service:
            return False, 0.0, "LLM service not available"
        
        try:
            # Create prompt for LLM evaluation
            prompt = f"""You are evaluating a student's graph drawing for the following question:

Question: {question_text}

Drawing Features:
- Has drawing: {drawing_features.get('has_paths', False)}
- Number of paths: {drawing_features.get('path_count', 0)}
- Bounding box: {drawing_features.get('bounding_box')}
- Center point: {drawing_features.get('center_point')}

Based on the question and the drawing features, evaluate whether the student's drawing is correct.
Consider:
1. Does the drawing show the expected graph shape?
2. Are key features (vertex, intercepts, direction) present?
3. Is the graph positioned correctly?

Respond with:
- correct: true/false
- score: 0.0 to {max_score}
- feedback: Brief explanation

Format as JSON: {{"correct": true/false, "score": number, "feedback": "string"}}"""

            response = await self.llm_service.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            
            # Parse LLM response
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                result = json.loads(json_match.group())
                is_correct = result.get('correct', False)
                score = min(max_score, max(0.0, float(result.get('score', 0.0))))
                feedback = result.get('feedback', '')
                return is_correct, score, feedback
            
            # Fallback if JSON not found
            return False, max_score * 0.5, "Could not evaluate drawing automatically. Manual review recommended."
            
        except Exception as e:
            logger.error(f"Error in LLM evaluation: {e}", exc_info=True)
            return False, max_score * 0.5, f"Error evaluating drawing: {str(e)}"
