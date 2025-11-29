# api/app.py
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
import yaml
import hashlib
from datetime import datetime
from time import perf_counter
from uuid import uuid4
from typing import Optional, List, Dict, Any
from PIL import Image
import io

from db.mongo import get_db, check_connection
from db.queries import MetricsQueries
from orchestrator.pp2_client import PP2Client, calculate_image_hash, convert_registry_to_services
from orchestrator.pp1_client import PP1Client, create_pp1_client
from orchestrator.fuse import FusionEngine, load_fusion_config
from orchestrator.schemas import (
    IdentifyAndAnswerResponse, HealthResponse, UserType, DecisionType,
    Identity, Candidate, NormativaAnswer, User, PP2Service
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="UFRO Orquestador MCP",
    description="Orquestador que integra PP2 (verificación de identidad) y PP1 (chatbot normativa UFRO)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global configuration
MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "5"))
ALLOWED_IMAGE_TYPES = os.getenv(
    "ALLOWED_IMAGE_TYPES", "image/jpeg,image/png").split(",")

# Initialize clients
fusion_engine = load_fusion_config()
pp1_client = create_pp1_client()
pp2_client = PP2Client(timeout=float(os.getenv("PP2_TIMEOUT", "8.0")))

# Load PP2 registry


def load_pp2_registry() -> List[PP2Service]:
    """Load PP2 services from YAML configuration"""
    try:
        with open("conf/registry.yaml", "r") as f:
            config = yaml.safe_load(f)
            registry_data = config.get("pp2_services", [])
            return convert_registry_to_services(registry_data)
    except Exception as e:
        logger.error(f"Failed to load PP2 registry: {e}")
        return []


pp2_registry = load_pp2_registry()
logger.info(f"Loaded {len(pp2_registry)} PP2 services")

# Dependency functions


async def get_user_info(
    x_user_id: Optional[str] = Header(None),
    x_user_type: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
) -> User:
    """Extract user information from headers"""

    user_id = x_user_id or f"anonymous-{uuid4().hex[:8]}"

    try:
        user_type = UserType(x_user_type) if x_user_type else UserType.EXTERNAL
    except ValueError:
        user_type = UserType.EXTERNAL

    role = "basic"
    if authorization and "admin" in authorization.lower():
        role = "admin"

    return User(id=user_id, type=user_type, role=role)


def validate_image(image: UploadFile) -> bytes:
    """Validate and process uploaded image"""

    content = image.file.read()
    size_mb = len(content) / (1024 * 1024)

    if size_mb > MAX_IMAGE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large: {
                size_mb:.2f}MB (max: {MAX_IMAGE_SIZE_MB}MB)"
        )

    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type: {
                image.content_type}. Allowed: {ALLOWED_IMAGE_TYPES}"
        )

    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid image file: {str(e)}"
        )

    image.file.seek(0)
    return content


@app.post("/identify-and-answer", response_model=IdentifyAndAnswerResponse)
async def identify_and_answer(
    image: UploadFile = File(...,
                             description="Image file for identity verification"),
    question: Optional[str] = Form(
        None, description="Optional question about UFRO normativa"),
    user: User = Depends(get_user_info)
):
    """
    Main orchestrator endpoint: identify person (PP2) and answer normativa question (PP1)
    """
    request_id = str(uuid4())
    start_time = perf_counter()

    logger.info(f"Processing request {request_id} for user {user.id}")

    try:
        # Validate and process image
        img_bytes = validate_image(image)
        img_hash = calculate_image_hash(img_bytes)

        logger.info(f"Processing image: {
                    len(img_bytes)} bytes, hash: {img_hash[:16]}...")

        # Step 1: Call PP2 services for identity verification
        pp2_results = await pp2_client.verify_all(img_bytes, pp2_registry, request_id)

        # Step 2: Fuse PP2 results
        decision, identity, candidates = fusion_engine.fuse_results(
            pp2_results)

        # Step 3: Query PP1 if question provided
        normativa_answer = None
        pp1_used = False

        if question and question.strip():
            pp1_used = True
            logger.info(f"Querying PP1 for question: {question[:50]}...")
            normativa_answer = await pp1_client.ask_normativa(question.strip(), request_id)

            if not normativa_answer:
                logger.warning("PP1 did not return a valid answer")

        total_timing_ms = round((perf_counter() - start_time) * 1000, 2)

        timeout_count = sum(1 for r in pp2_results
                            if "error" in r and "timeout" in str(r.get("error", "")).lower())

        await log_access(
            request_id=request_id,
            route="/identify-and-answer",
            user=user,
            image_info={
                "has_image": True,
                "has_question": bool(question and question.strip()),
                "image_hash": img_hash,
                "size_bytes": len(img_bytes)
            },
            decision=decision,
            identity=identity,
            timing_ms=total_timing_ms,
            pp2_summary={
                "queried": len(pp2_registry),
                "timeouts": timeout_count
            },
            pp1_used=pp1_used
        )

        response = IdentifyAndAnswerResponse(
            decision=decision,
            identity=identity,
            candidates=candidates,
            normativa_answer=normativa_answer,
            timing_ms=total_timing_ms,
            request_id=request_id
        )

        logger.info(f"Request {request_id} completed in {
                    total_timing_ms}ms - Decision: {decision.value}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing request {
                     request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/healthz", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""

    mongodb_connected = await check_connection()
    pp1_available = await pp1_client.health_check()

    status = "healthy" if mongodb_connected else "unhealthy"

    return HealthResponse(
        status=status,
        timestamp=datetime.utcnow(),
        mongodb_connected=mongodb_connected,
        pp2_services_count=len([s for s in pp2_registry if s.active]),
        pp1_available=pp1_available
    )


@app.get("/")
async def root():
    """Root endpoint with basic info"""
    return {
        "name": "UFRO Orquestador MCP",
        "version": "1.0.0",
        "description": "Integrates PP2 identity verification and PP1 UFRO normativa chatbot",
        "endpoints": {
            "main": "/identify-and-answer",
            "health": "/healthz",
            "metrics": "/metrics/*",
            "docs": "/docs"
        },
        "status": "running"
    }


@app.get("/metrics/summary")
async def get_metrics_summary(days: int = Query(7, ge=1, le=30)):
    """
    Get general summary metrics for the last N days
    """
    try:
        metrics = await MetricsQueries.get_summary_metrics(days)
        return {"success": True, "data": metrics, "period_days": days}
    except Exception as e:
        logger.error(f"Error getting summary metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@app.get("/metrics/by-user-type")
async def get_metrics_by_user_type(days: int = Query(7, ge=1, le=30)):
    """
    Get metrics grouped by user type
    """
    try:
        metrics = await MetricsQueries.get_user_type_metrics(days)
        return {"success": True, "data": metrics, "period_days": days}
    except Exception as e:
        logger.error(f"Error getting user type metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@app.get("/metrics/decisions")
async def get_metrics_decisions(days: int = Query(7, ge=1, le=30)):
    """
    Get decision distribution metrics (identified/ambiguous/unknown)
    """
    try:
        metrics = await MetricsQueries.get_decision_metrics(days)
        return {"success": True, "data": metrics, "period_days": days}
    except Exception as e:
        logger.error(f"Error getting decision metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@app.get("/metrics/services")
async def get_metrics_services(days: int = Query(7, ge=1, le=30)):
    """
    Get PP2/PP1 service performance metrics
    """
    try:
        metrics = await MetricsQueries.get_service_metrics(days)
        return {"success": True, "data": metrics, "period_days": days}
    except Exception as e:
        logger.error(f"Error getting service metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@app.get("/metrics/volume")
async def get_metrics_volume(days: int = Query(7, ge=1, le=30)):
    """
    Get hourly request volume for trend analysis
    """
    try:
        metrics = await MetricsQueries.get_hourly_volume(days)
        return {"success": True, "data": metrics, "period_days": days}
    except Exception as e:
        logger.error(f"Error getting volume metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


@app.get("/metrics/pp2-timeouts")
async def get_pp2_timeout_metrics(days: int = Query(7, ge=1, le=30), limit: int = Query(5, ge=1, le=20)):
    """
    Get PP2 services ranked by timeout count
    """
    try:
        metrics = await MetricsQueries.get_top_pp2_timeouts(days, limit)
        return {"success": True, "data": metrics, "period_days": days, "limit": limit}
    except Exception as e:
        logger.error(f"Error getting PP2 timeout metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get metrics")


async def log_access(
    request_id: str,
    route: str,
    user: User,
    image_info: Dict[str, Any],
    decision: DecisionType,
    identity: Optional[Identity],
    timing_ms: float,
    pp2_summary: Dict[str, int],
    pp1_used: bool,
    status_code: int = 200,
    errors: Optional[List[str]] = None
):
    """Log access to MongoDB"""
    try:
        db = await get_db()

        access_doc = {
            "request_id": request_id,
            "ts": datetime.utcnow(),
            "route": route,
            "user": {
                "id": user.id,
                "type": user.type.value,
                "role": user.role
            },
            "input": image_info,
            "decision": decision.value,
            "identity": {
                "name": identity.name,
                "score": identity.score
            } if identity else None,
            "timing_ms": timing_ms,
            "status_code": status_code,
            "errors": errors,
            "pp2_summary": pp2_summary,
            "pp1_used": pp1_used,
            "ip": "anonymized"
        }

        await db.access_logs.insert_one(access_doc)
        logger.debug(f"Logged access for request {request_id}")

    except Exception as e:
        logger.error(f"Failed to log access: {e}")


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Endpoint not found"}
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info("Starting UFRO Orquestador MCP...")

    # Check MongoDB connection
    mongodb_ok = await check_connection()
    logger.info(f"MongoDB connection: {'✅ OK' if mongodb_ok else '❌ FAILED'}")

    # Check PP1 availability
    pp1_ok = await pp1_client.health_check()
    logger.info(f"PP1 service: {'✅ OK' if pp1_ok else '⚠️  UNAVAILABLE'}")

    # Log PP2 services
    active_pp2 = [s for s in pp2_registry if s.active]
    logger.info(f"PP2 services: {len(active_pp2)} active")
    for service in active_pp2:
        logger.info(f"  - {service.name}: {service.endpoint_verify}")

    logger.info("🚀 UFRO Orquestador MCP is ready!")

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))

    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
