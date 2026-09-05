from pydantic import BaseModel, Field

from app.models.enums import RecoveryActionType


class AgentDecisionOutput(BaseModel):
    diagnosis: str = Field(min_length=1)
    recommended_action: RecoveryActionType
    confidence: str = Field(pattern="^(LOW|MEDIUM|HIGH)$")
    reasoning: str = Field(min_length=1)
