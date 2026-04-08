import structlog
import json
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from app.graph.nodes.ai_reasoning import get_llm
from app.prompts.classification_prompt import CLASSIFICATION_SYSTEM_PROMPT, build_classification_prompt

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])

class ClassifyStageRequest(BaseModel):
    stage_name: str

class ClassifyStageResponse(BaseModel):
    systemCategory: str
    intentTag: str
    confidence: float
    reasoning: str

@router.post(
    "/classify-stage",
    response_model=ClassifyStageResponse,
    status_code=status.HTTP_200_OK,
    summary="Predicts the system category and intent for a given stage name",
)
async def classify_stage(request: ClassifyStageRequest) -> ClassifyStageResponse:
    """
    Classifies a human-readable stage name into a standardized VSM category and intent tag.
    """
    logger.info("classify_stage: start", stage_name=request.stage_name)

    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", CLASSIFICATION_SYSTEM_PROMPT),
            ("user", build_classification_prompt(request.stage_name))
        ])

        llm = get_llm()
        chain = prompt | llm

        response = await chain.ainvoke({})
        
        # Parse output
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
            
        raw_json = json.loads(content)
        parsed = ClassifyStageResponse(**raw_json)
        
        logger.info(
            "classify_stage: success", 
            stage_name=request.stage_name, 
            category=parsed.systemCategory, 
            intent=parsed.intentTag
        )
        return parsed

    except Exception as exc:
        logger.exception("classify_stage: failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Classification failed: {exc}",
        )
