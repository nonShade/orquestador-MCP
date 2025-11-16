# # orchestrator/pp2_client.py
# import httpx
# import asyncio
# from db.mongo import get_db
#
#
# async def verify_all(img_bytes, roster, timeout=2.0):
#     async with httpx.AsyncClient(timeout=timeout) as client:
#         tasks = [client.post(r["endpoint_verify"],
#                              files={"image": ("img.jpg", img_bytes, "image/jpeg")})
#                  for r in roster if r.get("active", True)]
#         return await asyncio.gather(*tasks, return_exceptions=True)
#
#
# async def log_service_call(request_id, r, resp_or_exc, latency_ms):
#     db = await get_db()
#     if isinstance(resp_or_exc, Exception):
#         doc = {"request_id": request_id, "ts": datetime.utcnow(), "service_type": "pp2",
#                "service_name": r["name"], "endpoint": r["endpoint_verify"],
#                "latency_ms": latency_ms, "status_code": None, "timeout": True, "error": str(resp_or_exc)}
#     else:
#         js = resp_or_exc.json() if resp_or_exc.headers.get(
#             "content-type", "").startswith("application/json") else {}
#         doc = {"request_id": request_id, "ts": datetime.utcnow(), "service_type": "pp2",
#                "service_name": r["name"], "endpoint": r["endpoint_verify"],
#                "latency_ms": latency_ms, "status_code": resp_or_exc.status_code,
#                "timeout": False, "result": js}
#     await db.service_logs.insert_one(doc)
