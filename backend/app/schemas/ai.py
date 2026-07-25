"""
AI schemas for S2PNexus.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Chat request schema."""

    model_config = ConfigDict(from_attributes=True)

    message: str = Field(..., min_length=1, description="User message")
    system_prompt: Optional[str] = Field(None, description="System prompt")
    context: Optional[list[dict]] = Field(default=None, description="Conversation context")
    model: Optional[str] = Field(None, description="Model to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature")


class ChatResponse(BaseModel):
    """Chat response schema."""

    model_config = ConfigDict(from_attributes=True)

    response: str = Field(..., description="AI response")
    model: str = Field(..., description="Model used")


class DocumentAnalysisRequest(BaseModel):
    """Document analysis request schema."""

    model_config = ConfigDict(from_attributes=True)

    document_text: str = Field(..., min_length=1, description="Document text to analyze")
    analysis_type: str = Field(default="summary", description="Type of analysis")
    model: Optional[str] = Field(None, description="Model to use")


class DocumentAnalysisResponse(BaseModel):
    """Document analysis response schema."""

    model_config = ConfigDict(from_attributes=True)

    analysis: str = Field(..., description="Analysis result")
    analysis_type: str = Field(..., description="Type of analysis performed")


class EmbeddingRequest(BaseModel):
    """Embedding request schema."""

    model_config = ConfigDict(from_attributes=True)

    texts: list[str] = Field(..., min_length=1, description="Texts to embed")
    model: Optional[str] = Field(None, description="Embedding model")


class EmbeddingResponse(BaseModel):
    """Embedding response schema."""

    model_config = ConfigDict(from_attributes=True)

    embeddings: list[list[float]] = Field(..., description="Generated embeddings")
    model: str = Field(..., description="Model used")
    dimensions: int = Field(..., description="Embedding dimensions")


class RAGQueryRequest(BaseModel):
    """RAG query request schema."""

    model_config = ConfigDict(from_attributes=True)

    query: str = Field(..., min_length=1, description="Query text")
    collection_name: str = Field(default="default", description="Collection name")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")
    model: Optional[str] = Field(None, description="Model to use")


class RAGQueryResponse(BaseModel):
    """RAG query response schema."""

    model_config = ConfigDict(from_attributes=True)

    answer: str = Field(..., description="Generated answer")
    sources: list[dict] = Field(default=[], description="Source documents")
    model: str = Field(..., description="Model used")