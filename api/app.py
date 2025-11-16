# # api/app.py (dentro de endpoint)
# from uuid import uuid4
# from time import perf_counter
# from db.mongo import get_db
#
# request_id = str(uuid4())
# t0 = perf_counter()
# # ... orquestar PP2/PP1 ...
# doc = {
#     "request_id": request_id,
#     "ts": datetime.utcnow(),
#     "route": "/identify-and-answer",
#     "user": {"id": user_id, "type": user_type, "role": role},
#     "input": {"has_image": True, "has_question": bool(question),
#               "image_hash": image_sha256, "size_bytes": size},
#     "decision": decision,
#     "identity": identity or None,
#     "timing_ms": round((perf_counter()-t0)*1000, 2),
#     "status_code": 200,
#     "pp2_summary": {"queried": len(roster), "timeouts": timeouts},
#     "pp1_used": bool(question)
# }
# db = await get_db()
# await db.access_logs.insert_one(doc)
