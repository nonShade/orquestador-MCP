# orchestrator/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

class UserType(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty" 
    ADMIN = "admin"
    EXTERNAL = "external"

class DecisionType(str, Enum):
    IDENTIFIED = "identified"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"

class ServiceType(str, Enum):
    PP1 = "pp1"
    PP2 = "pp2"

class User(BaseModel):
    id: str = Field(..., description="User ID (hash or UUID)")
    type: UserType = Field(..., description="User type")
    role: str = Field(default="basic", description="User role")

class Identity(BaseModel):
    name: str = Field(..., description="Identified person name")
    score: float = Field(..., ge=0, le=1, description="Confidence score")

class Candidate(BaseModel):
    name: str = Field(..., description="Candidate name")
    score: float = Field(..., ge=0, le=1, description="Confidence score")

class Citation(BaseModel):
    doc: str = Field(..., description="Document name")
    page: Optional[str] = Field(None, description="Page reference")
    section: Optional[str] = Field(None, description="Section reference") 
    url: Optional[str] = Field(None, description="Document URL")

class NormativaAnswer(BaseModel):
    text: str = Field(..., description="Answer text")
    citations: List[Citation] = Field(default_factory=list, description="Source citations")

class IdentifyAndAnswerRequest(BaseModel):
    question: Optional[str] = Field(None, description="Optional question about UFRO normativa")

class IdentifyAndAnswerResponse(BaseModel):
    decision: DecisionType = Field(..., description="Identity decision")
    identity: Optional[Identity] = Field(None, description="Identified person if decision is 'identified'")
    candidates: List[Candidate] = Field(default_factory=list, description="All candidates with scores")
    normativa_answer: Optional[NormativaAnswer] = Field(None, description="Answer if question provided")
    timing_ms: float = Field(..., description="Total processing time in milliseconds")
    request_id: str = Field(..., description="Request ID for tracking")

class AccessLog(BaseModel):
    request_id: str
    ts: datetime
    route: str
    user: User
    input: Dict[str, Any]
    decision: DecisionType
    identity: Optional[Identity]
    timing_ms: float
    status_code: int
    errors: Optional[List[str]]
    pp2_summary: Dict[str, int]
    pp1_used: bool
    ip: Optional[str]

class ServiceLog(BaseModel):
    request_id: str
    ts: datetime
    service_type: ServiceType
    service_name: str
    endpoint: str
    latency_ms: float
    status_code: Optional[int]
    payload_size_bytes: Optional[int]
    result: Optional[Dict[str, Any]]
    timeout: bool
    error: Optional[str]

class PP2Service(BaseModel):
    name: str = Field(..., description="Service name (person name)")
    endpoint_verify: str = Field(..., description="PP2 verify endpoint URL")
    threshold: float = Field(default=0.75, ge=0, le=1, description="Confidence threshold")
    active: bool = Field(default=True, description="Whether service is active")

class PP2Registry(BaseModel):
    pp2_services: List[PP2Service]

class MetricsSummary(BaseModel):
    total_requests: int
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    period_days: int

class UserTypeMetrics(BaseModel):
    user_type: str
    total_requests: int
    avg_latency_ms: float
    success_rate: float

class DecisionMetrics(BaseModel):
    decision: str
    count: int
    percentage: float

class ServiceMetrics(BaseModel):
    service_name: str
    avg_latency_ms: float
    timeout_count: int
    error_count: int
    total_calls: int

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    mongodb_connected: bool = Field(..., description="MongoDB connection status")
    pp2_services_count: int = Field(..., description="Number of active PP2 services")
    pp1_available: bool = Field(..., description="PP1 service availability")