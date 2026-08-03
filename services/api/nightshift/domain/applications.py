"""Application tracking: the stage machine, and (from Task 3) its writes.

The machine does not block. PRODUCT-SPEC §10.2 requires that the user can
always set and correct a stage, and ``saved -> offer`` is a real thing that
happens to real people with referrals. So every transition is permitted and
every transition is *classified*, and the classification lands on the event.

What is enforced instead is invariant I5: only a user moves a stage. That rule
lives in three places on purpose — this module raises, the API requires it, and
the database refuses it with a check constraint.
"""

from __future__ import annotations

from nightshift.db.base import ApplicationStage, TransitionClass

#: The default forward order. Terminal stages are deliberately absent: they are
#: outcomes rather than steps, reachable from anywhere.
STAGE_ORDER: tuple[ApplicationStage, ...] = (
    ApplicationStage.DISCOVERED,
    ApplicationStage.SAVED,
    ApplicationStage.PREPARING,
    ApplicationStage.APPLIED,
    ApplicationStage.ASSESSMENT,
    ApplicationStage.INTERVIEW,
    ApplicationStage.OFFER,
)

TERMINAL_STAGES: frozenset[ApplicationStage] = frozenset(
    {
        ApplicationStage.REJECTED,
        ApplicationStage.WITHDRAWN,
        ApplicationStage.CLOSED,
    }
)

_POSITION = {stage: index for index, stage in enumerate(STAGE_ORDER)}


class SameStageError(ValueError):
    """Raised when asked to classify a stage change that changes nothing."""


def classify_transition(
    from_stage: ApplicationStage, to_stage: ApplicationStage
) -> TransitionClass:
    """Classify a stage change. Never refuses one; only describes it.

    ``reopen`` beats every other rule: leaving a terminal stage is the fact
    worth recording, whatever the destination.
    """
    if from_stage is to_stage:
        raise SameStageError(f"{from_stage.value} is already the current stage")

    if from_stage in TERMINAL_STAGES:
        return TransitionClass.REOPEN

    if to_stage in TERMINAL_STAGES:
        # An outcome is the natural end of any stage, not a skipped step.
        return TransitionClass.ADVANCE

    if _POSITION[to_stage] == _POSITION[from_stage] + 1:
        return TransitionClass.ADVANCE

    # Backward, or forward past a stage that never happened. Both are the user
    # correcting the record, which is exactly what §10.2 asks us to allow.
    return TransitionClass.CORRECTION
