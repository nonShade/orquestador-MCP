# orchestrator/pp1_client.py
import httpx
import logging
from datetime import datetime
from time import perf_counter
from typing import Optional, Dict, Any
from db.mongo import get_db
from orchestrator.schemas import NormativaAnswer, Citation, ServiceType

logger = logging.getLogger(__name__)


class PP1Client:
    """
    Client for PP1 RAG service (UFRO normativa chatbot)
    """

    def __init__(self, pp1_url: str, timeout: float = 15.0):
        """
        Initialize PP1 client

        Args:
            pp1_url: Base URL for PP1 service
            timeout: Request timeout in seconds
        """
        self.pp1_url = pp1_url.rstrip('/')
        self.timeout = timeout

    async def ask_normativa(self, question: str, request_id: str, provider: str = "deepseek", k: int = 5) -> Optional[NormativaAnswer]:
        """
        Ask PP1 service about UFRO normativa using the real /api/chat endpoint

        Args:
            question: User's question about normativa
            request_id: Request ID for logging
            provider: AI provider to use ("deepseek" or "chatgpt")
            k: Number of documents to retrieve (1-10)

        Returns:
            NormativaAnswer object or None if failed
        """
        if not question or not question.strip():
            logger.warning("Empty question provided to PP1")
            return None

        logger.info(f"Querying PP1 with question: {question[:100]}...")

        start_time = perf_counter()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "message": question.strip(),
                    "provider": provider,
                    "k": max(1, min(10, k))  # Ensure k is between 1-10
                }

                logger.debug(f"PP1 payload: {payload}")

                # Make request to PP1 /api/chat endpoint
                response = await client.post(
                    f"{self.pp1_url}/api/chat",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                latency_ms = round((perf_counter() - start_time) * 1000, 2)

                await self._log_service_call(
                    request_id=request_id,
                    question=question,
                    response=response,
                    latency_ms=latency_ms,
                    timeout=False,
                    error=None
                )

                if response.status_code == 200:
                    try:
                        result = response.json()
                        logger.debug(f"PP1 response: {result}")

                        return self._parse_pp1_response(result)

                    except Exception as e:
                        logger.error(f"Failed to parse PP1 JSON response: {e}")
                        return None
                else:
                    logger.warning(f"PP1 returned status {
                                   response.status_code}: {response.text}")
                    return None

        except httpx.TimeoutException:
            latency_ms = round((perf_counter() - start_time) * 1000, 2)
            logger.warning(f"PP1 request timed out after {self.timeout}s")

            await self._log_service_call(
                request_id=request_id,
                question=question,
                response=None,
                latency_ms=latency_ms,
                timeout=True,
                error="Timeout"
            )
            return None

        except Exception as e:
            latency_ms = round((perf_counter() - start_time) * 1000, 2)
            logger.error(f"Error calling PP1: {e}")

            await self._log_service_call(
                request_id=request_id,
                question=question,
                response=None,
                latency_ms=latency_ms,
                timeout=False,
                error=str(e)
            )
            return None

    def _parse_pp1_response(self, response_data: Dict[str, Any]) -> Optional[NormativaAnswer]:
        """
        Parse PP1 response into NormativaAnswer schema

        Expected PP1 response format:
        {
          "success": true,
          "result": {
            "answer": "respuesta generada por el LLM",
            "sources": [
              {
                "title": "nombre del documento",
                "page": número_página,
                "score": puntuación_relevancia
              }
            ],
            "provider": "nombre_del_proveedor_usado",
            "metrics": {
              "tokens": número_tokens_usados,
              "latency": tiempo_respuesta_segundos,
              "cost": costo_estimado_dolares
            }
          },
          "session_id": "id_de_sesion"
        }
        """
        try:
            if not response_data.get("success", False):
                error_msg = response_data.get(
                    "error", "Unknown error from PP1")
                logger.warning(f"PP1 returned error: {error_msg}")
                return None

            result = response_data.get("result", {})
            if not result:
                logger.warning("No result object found in PP1 response")
                return None

            answer_text = result.get("answer", "")
            if not answer_text:
                logger.warning("No answer text found in PP1 response")
                return None

            citations = []
            raw_sources = result.get("sources", [])

            if isinstance(raw_sources, list):
                for source in raw_sources:
                    if isinstance(source, dict):
                        citation = Citation(
                            doc=source.get("title", "Unknown Document"),
                            page=str(source.get("page", "")) if source.get(
                                "page") is not None else None,
                            section=None,  # PP1 doesn't provide section info
                            url=None  # PP1 doesn't provide URLs in current format
                        )
                        citations.append(citation)

            logger.info(f"Parsed PP1 response with {len(citations)} citations")
            logger.debug(f"PP1 metrics: {result.get('metrics', {})}")

            return NormativaAnswer(
                text=answer_text,
                citations=citations
            )

        except Exception as e:
            logger.error(f"Failed to parse PP1 response: {e}")
            return None

    async def _log_service_call(self, request_id: str, question: str,
                                response: Optional[httpx.Response] = None,
                                latency_ms: float = 0, timeout: bool = False,
                                error: Optional[str] = None):
        """
        Log PP1 service call to MongoDB
        """
        try:
            db = await get_db()

            log_doc = {
                "request_id": request_id,
                "ts": datetime.utcnow(),
                "service_type": ServiceType.PP1.value,
                "service_name": "UFRO-RAG",
                "endpoint": f"{self.pp1_url}/api/chat",
                "latency_ms": latency_ms,
                "payload_size_bytes": len(question.encode('utf-8')) if question else 0,
                "timeout": timeout,
                "error": error
            }

            if response:
                try:
                    response_json = response.json() if response.headers.get(
                        "content-type", "").startswith("application/json") else None
                    log_doc.update({
                        "status_code": response.status_code,
                        "result": response_json
                    })
                except:
                    log_doc.update({
                        "status_code": response.status_code,
                        "result": None
                    })
            else:
                log_doc["status_code"] = None
                log_doc["result"] = None

            await db.service_logs.insert_one(log_doc)

        except Exception as e:
            logger.error(f"Failed to log PP1 service call: {e}")

    async def health_check(self) -> bool:
        """
        Check if PP1 service is available
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.pp1_url}/health")
                return response.status_code == 200
        except Exception:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        f"{self.pp1_url}/api/chat",
                        json={"message": "test", "provider": "deepseek", "k": 1}
                    )
                    return True
            except Exception:
                return False


def create_pp1_client() -> PP1Client:
    """
    Create PP1 client with configuration from environment
    """
    import os

    pp1_url = os.getenv("PP1_URL", "http://98.94.200.223:5000")
    pp1_timeout = float(os.getenv("PP1_TIMEOUT", "15.0"))

    logger.info(f"PP1 client configured for: {pp1_url}")
    return PP1Client(pp1_url, pp1_timeout)
