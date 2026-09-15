import logging
from typing import Dict, Optional

from .models import ANSWER_PASS_THRESHOLD, DecisionOutcome

logger = logging.getLogger(__name__)


class AdaptiveInterviewController:
    def __init__(self, candidate_level: str):
        self.candidate_level = candidate_level
        self.history = []
        self.level_rank = {"Intern": 0, "Junior": 1, "Mid-Level": 2, "Senior": 3}

    def next_level(self, current_difficulty: str, weighted_total: float) -> str:
        current_rank = self.level_rank.get(current_difficulty, 2)
        if weighted_total >= 85:
            target_rank = min(current_rank + 1, 3)
        elif weighted_total >= ANSWER_PASS_THRESHOLD:
            target_rank = current_rank
        else:
            target_rank = max(current_rank - 1, 0)

        next_level = [level for level, rank in self.level_rank.items() if rank == target_rank][0]
        self.history.append((current_difficulty, next_level, weighted_total))
        logger.info("Adaptive decision: %s -> %s with score %.1f", current_difficulty, next_level, weighted_total)
        return next_level


def decide_next_step(
    current_difficulty: str,
    previous_question_type: str,
    answer_evaluation: Dict[str, float],
    controller: Optional[AdaptiveInterviewController] = None,
) -> DecisionOutcome:
    """Decide next difficulty and question type based on answer quality."""
    if controller is None:
        controller = AdaptiveInterviewController(candidate_level=current_difficulty)

    weighted_total = float(answer_evaluation.get("weighted_total", 60))
    next_difficulty = controller.next_level(current_difficulty, weighted_total)

    question_types = ["Role-specific", "Technology", "Project", "Architecture", "Problem-solving"]
    current_index = question_types.index(previous_question_type) if previous_question_type in question_types else 0
    if weighted_total >= 85:
        next_question_type = question_types[min(current_index + 1, len(question_types) - 1)]
        follow_up_required = "No"
        reason = "Strong performance enabled a deeper challenge."
    elif weighted_total >= ANSWER_PASS_THRESHOLD:
        next_question_type = question_types[current_index]
        follow_up_required = "No"
        reason = "Candidate is performing within expected range; maintain the current track."
    else:
        next_question_type = question_types[max(current_index - 1, 0)]
        follow_up_required = "Yes"
        reason = "Lower confidence indicates a simpler or clarifying follow-up is appropriate."

    return DecisionOutcome(
        next_difficulty=next_difficulty,
        next_question_type=next_question_type,
        follow_up_required=follow_up_required,
        reason=reason,
    )
