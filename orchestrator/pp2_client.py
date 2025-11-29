# orchestrator/pp2_client.py
import httpx
import asyncio
import hashlib
import logging
from datetime import datetime
from time import perf_counter
from typing import List, Dict, Any, Optional
from db.mongo import get_db
from orchestrator.schemas import PP2Service, ServiceType

logger = logging.getLogger(__name__)


class PP2Client:
    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    async def verify_all(self, img_bytes: bytes, roster: List[PP2Service], request_id: str) -> List[Dict[str, Any]]:
        """
        Call all active PP2 services in parallel and log results
        """
        active_services = [service for service in roster if service.active]

        if not active_services:
            logger.warning("No active PP2 services found")
            return []

        logger.info(f"Calling {len(active_services)
                               } PP2 services for request {request_id}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = []
            service_start_times = {}

            for service in active_services:
                start_time = perf_counter()
                service_start_times[service.name] = start_time

                task = self._call_pp2_service(
                    client, service, img_bytes, request_id, start_time)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            valid_results = []
            for i, result in enumerate(results):
                service = active_services[i]
                if isinstance(result, dict) and "is_me" in result:
                    valid_results.append({
                        "name": service.name,
                        "score": result.get("score", 0.0),
                        "is_me": result.get("is_me", False),
                        "service": service.name,
                        "model_version": result.get("model_version", "unknown"),
                        "threshold": result.get("threshold", 0.75),
                        "pp2_timing_ms": result.get("timing_ms", 0)
                    })

            logger.info(f"Got {len(valid_results)
                               } valid responses from PP2 services")
            return valid_results

    async def _call_pp2_service(self, client: httpx.AsyncClient, service: PP2Service,
                                img_bytes: bytes, request_id: str, start_time: float) -> Dict[str, Any]:
        """
        Call a single PP2 service and log the result
        """
        try:
            files = {"image": ("image.jpg", img_bytes, "image/jpeg")}

            response = await client.post(service.endpoint_verify, files=files)
            latency_ms = round((perf_counter() - start_time) * 1000, 2)

            await self._log_service_call(
                request_id=request_id,
                service=service,
                response=response,
                latency_ms=latency_ms,
                payload_size=len(img_bytes),
                timeout=False,
                error=None
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    logger.debug(f"PP2 service {
                                 service.name} returned: {result}")
                    return result
                except Exception as e:
                    logger.error(f"Failed to parse JSON from {
                                 service.name}: {e}")
                    return {"error": "Invalid JSON response"}
            else:
                logger.warning(f"PP2 service {service.name} returned status {
                               response.status_code}")
                return {"error": f"HTTP {response.status_code}"}

        except asyncio.TimeoutError:
            latency_ms = round((perf_counter() - start_time) * 1000, 2)
            logger.warning(f"Timeout calling PP2 service {service.name}")

            await self._log_service_call(
                request_id=request_id,
                service=service,
                response=None,
                latency_ms=latency_ms,
                payload_size=len(img_bytes),
                timeout=True,
                error="Timeout"
            )
            return {"error": "timeout"}

        except Exception as e:
            latency_ms = round((perf_counter() - start_time) * 1000, 2)
            logger.error(f"Error calling PP2 service {service.name}: {e}")

            await self._log_service_call(
                request_id=request_id,
                service=service,
                response=None,
                latency_ms=latency_ms,
                payload_size=len(img_bytes),
                timeout=False,
                error=str(e)
            )
            return {"error": str(e)}

    async def _log_service_call(self, request_id: str, service: PP2Service,
                                response: Optional[httpx.Response] = None, latency_ms: float = 0,
                                payload_size: int = 0, timeout: bool = False,
                                error: Optional[str] = None):
        """
        Log service call to MongoDB
        """
        try:
            db = await get_db()

            log_doc = {
                "request_id": request_id,
                "ts": datetime.utcnow(),
                "service_type": ServiceType.PP2.value,
                "service_name": service.name,
                "endpoint": service.endpoint_verify,
                "latency_ms": latency_ms,
                "payload_size_bytes": payload_size,
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
            logger.error(f"Failed to log service call: {e}")


def calculate_image_hash(img_bytes: bytes) -> str:
    """Calculate SHA256 hash of image for logging"""
    return f"sha256:{hashlib.sha256(img_bytes).hexdigest()}"


def convert_registry_to_services(registry_data: List[Dict[str, Any]]) -> List[PP2Service]:
    """Convert YAML registry data to PP2Service objects"""
    services = []
    for item in registry_data:
        try:
            service = PP2Service(
                name=item.get("name", "Unknown"),
                endpoint_verify=item.get("endpoint_verify", ""),
                threshold=item.get("threshold", 0.75),
                active=item.get("active", True)
            )
            services.append(service)
        except Exception as e:
            logger.error(f"Failed to convert registry item to PP2Service: {e}")
            continue
    return services
