from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Domain = Literal["book", "electronics", "fashion", "general"]


class EventIngestRequest(BaseModel):
    event_type: str = Field(max_length=100)
    customer_id: int | None = None
    session_id: str = Field(default="", max_length=128)
    product_id: int | None = None
    domain: Domain | None = None
    occurred_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def extract_payload_fields(self):
        if self.product_id is None and self.payload.get("product_id") is not None:
            self.product_id = int(self.payload["product_id"])
        if self.domain is None and self.payload.get("domain"):
            self.domain = self.payload["domain"]
        return self


class BehaviorScoreRequest(BaseModel):
    customer_id: int


class RecommendationRequest(BaseModel):
    customer_id: int
    product_id: int | None = None
    domain: Domain | None = None
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=4, ge=1, le=20)


class GraphRecommendationRequest(BaseModel):
    customer_id: int | None = None
    domain: Domain | None = None
    limit: int = Field(default=5, ge=1, le=20)


class ChatAdviceRequest(BaseModel):
    message: str = Field(max_length=1000)
    customer_id: int | None = None
    domain: Domain | None = None


class KBDocumentInput(BaseModel):
    title: str = Field(max_length=200)
    content: str
    source: str = Field(default="manual", max_length=120)
    topic: str = Field(default="general", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class KBReindexRequest(BaseModel):
    documents: list[KBDocumentInput] = Field(default_factory=list)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
