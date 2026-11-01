from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# Auth Schemas
class UserLoginRequest(BaseModel):
    email: str
    password: str
    rememberMe: Optional[bool] = False

class UserResponse(BaseModel):
    email: str
    name: str
    role: str
    department: str
    avatar: Optional[str] = "PL"

class AuthResponse(BaseModel):
    user: UserResponse
    token: str
    mode: str = "backend"

# Document Schemas
class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_size: int
    total_pages: int
    total_words: int
    upload_date: str
    status: str
    processing_stage: Optional[str] = "completed"
    processing_progress: Optional[int] = 100
    error_message: Optional[str] = None
    has_explanation: bool = False

class DocumentStatusResponse(BaseModel):
    id: str
    filename: str
    status: str  # "processing", "completed", "ready", "failed", "scanned_ocr_required"
    processing_stage: str
    processing_progress: int  # 0 to 100
    total_pages: int = 0
    total_words: int = 0
    total_clauses: int = 0
    error_message: Optional[str] = None
    has_explanation: bool = False
    is_ready_for_chat: bool = False

class DocumentUploadResponse(BaseModel):
    message: str
    document: DocumentResponse

class PageText(BaseModel):
    page: int
    word_count: int
    text: str

class DocumentTextResponse(BaseModel):
    document_id: str
    filename: str
    total_pages: int
    total_words: int
    pages: List[PageText]

# Citation Schemas
class SourceCitation(BaseModel):
    page: int
    section: Optional[str] = "General Policy Terms"
    clause_number: Optional[str] = None
    category: Optional[str] = "Coverage"
    relevance_score: float = Field(default=0.85, ge=0.0, le=1.0)
    text: str

# QA & RAG Schemas
class QuestionRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    use_baseline: Optional[bool] = False

class AnswerResponse(BaseModel):
    answer: str
    conversation_id: str
    topic: str
    status: str = "answered"  # "answered" | "insufficient_evidence" | "error"
    sources: List[SourceCitation] = []
    completeness_score: Optional[float] = 1.0
    retrieved_categories: List[str] = []
    pipeline_type: str = "PolicyLens_Hybrid_RAG"

class ChatMessageSchema(BaseModel):
    id: int
    role: str  # "user" | "assistant"
    content: str
    topic: Optional[str] = None
    status: Optional[str] = "ready"
    sources: Optional[List[SourceCitation]] = []
    timestamp: str

class ConversationHistoryResponse(BaseModel):
    conversation_id: str
    document_id: str
    filename: str
    title: str
    messages: List[ChatMessageSchema]

class ConversationSummary(BaseModel):
    conversation_id: str
    document_id: str
    filename: str
    title: str
    message_count: int
    last_updated: str

# Policy Explanation Schemas
class PolicyExplanationSection(BaseModel):
    key: str
    title: str
    summary: str
    key_points: List[str] = []
    sources: List[SourceCitation] = []
    limitations: Optional[str] = None
    status: str = "found"  # "found" | "not_found" | "partial"

class PolicyExplanationResponse(BaseModel):
    document_id: str
    filename: str
    total_pages: int
    generated_at: str
    overview: str
    sections: List[PolicyExplanationSection]
