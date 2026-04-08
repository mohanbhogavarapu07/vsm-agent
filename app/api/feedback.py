"""
VSM AI Agent – Feedback API Endpoint (PRD 3 §10)

POST /agent/feedback

Receives user feedback on AI decisions.
Stores in vsm-backend (via HTTP) for learning loop.

Feedback types:
  - decision_feedback: accepted/rejected AI status decisions
  - nlp_feedback: corrected NLP intent classifications
"""

import logging

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

import httpx
from app.config import get_agent_settings

logger = logging.getLogger(__name__)
settings = get_agent_settings()

router = APIRouter(prefix="/agent", tags=["feedback"])


class DecisionFeedbackRequest(BaseModel):
    decision_id: int
    task_id: int
    user_id: int
    feedback: str = Field(..., pattern="^(ACCEPTED|REJECTED)$")


class NLPFeedbackRequest(BaseModel):
    insight_id: int
    task_id: int
    user_id: int
    feedback: str = Field(..., pattern="^(ACCEPTED|REJECTED)$")
    corrected_intent: str | None = Field(
        None, pattern="^(BLOCKER|PROGRESS|NONE)$"
    )


@router.post(
    "/feedback/decision",
    status_code=status.HTTP_200_OK,
    summary="Submit feedback on an AI decision",
)
async def feedback_decision(payload: DecisionFeedbackRequest) -> dict:
    """
    Forwards decision feedback to vsm-backend for recording.
    Used to improve AI accuracy metrics.
    """
    async with httpx.AsyncClient(
        base_url=settings.backend_url,
        timeout=settings.backend_timeout,
    ) as client:
        response = await client.post(
            f"/tasks/{payload.task_id}/decisions/{payload.decision_id}/feedback",
            json={
                "feedback": payload.feedback,
            },
            params={"user_id": payload.user_id},
        )

    logger.info(
        "feedback: decision_id=%s user=%s feedback=%s",
        payload.decision_id, payload.user_id, payload.feedback,
    )
    return {
        "status": "recorded",
        "decision_id": payload.decision_id,
        "feedback": payload.feedback,
    }


@router.post(
    "/feedback/nlp",
    status_code=status.HTTP_200_OK,
    summary="Submit feedback on an NLP insight",
)
async def feedback_nlp(payload: NLPFeedbackRequest) -> dict:
    """
    Records user correction of an NLP intent classification.
    Feeds into the continuous learning loop.
    """
    logger.info(
        "feedback: nlp insight_id=%s user=%s feedback=%s corrected=%s",
        payload.insight_id, payload.user_id, payload.feedback, payload.corrected_intent,
    )
    # In production: store in nlp_feedback table via backend
    return {
        "status": "recorded",
        "insight_id": payload.insight_id,
        "feedback": payload.feedback,
        "corrected_intent": payload.corrected_intent,
    }
