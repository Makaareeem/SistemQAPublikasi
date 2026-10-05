from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.config import DEFAULT_MODEL_KEY, DEFAULT_RESPONSE_STYLE, RETRIEVAL_K


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=1500, strict=True)
    model_key: str = DEFAULT_MODEL_KEY
    use_rag: Literal[True] = True
    top_k: int = Field(default=RETRIEVAL_K, ge=1, le=5, strict=True)
    response_style: Literal["ringkas", "detail"] = DEFAULT_RESPONSE_STYLE


class EvaluationRequest(AskRequest):
    use_rag: bool = Field(default=True, strict=True)
    strict_expansion: bool = True
