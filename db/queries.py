# db/queries.py
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from db.mongo import get_db
import logging

logger = logging.getLogger(__name__)


class MetricsQueries:
    """
    MongoDB aggregation queries for analytics and metrics
    """

    @staticmethod
    async def get_summary_metrics(days: int = 7) -> Dict[str, Any]:
        """
        Get general summary metrics for the last N days
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {"ts": {"$gte": since_date}}},
                {"$group": {
                    "_id": None,
                    "total_requests": {"$sum": 1},
                    "avg_latency_ms": {"$avg": "$timing_ms"},
                    "latencies": {"$push": "$timing_ms"},
                    "error_count": {"$sum": {"$cond": [{"$ne": ["$status_code", 200]}, 1, 0]}},
                    "pp1_used_count": {"$sum": {"$cond": ["$pp1_used", 1, 0]}}
                }},
                {"$project": {
                    "total_requests": 1,
                    "avg_latency_ms": {"$round": ["$avg_latency_ms", 2]},
                    "p50_latency_ms": {"$round": [{"$percentile": {"input": "$latencies", "p": [0.5]}}, 2]},
                    "p95_latency_ms": {"$round": [{"$percentile": {"input": "$latencies", "p": [0.95]}}, 2]},
                    "error_rate": {"$cond": [
                        {"$eq": ["$total_requests", 0]}, 0,
                        {"$round": [
                            {"$divide": ["$error_count", "$total_requests"]}, 3]}
                    ]},
                    "pp1_usage_rate": {"$cond": [
                        {"$eq": ["$total_requests", 0]}, 0,
                        {"$round": [
                            {"$divide": ["$pp1_used_count", "$total_requests"]}, 3]}
                    ]}
                }}
            ]

            result = await db.access_logs.aggregate(pipeline).to_list(length=1)

            if result:
                metrics = result[0]
                metrics["period_days"] = days
                return metrics
            else:
                return {
                    "total_requests": 0,
                    "avg_latency_ms": 0.0,
                    "p50_latency_ms": 0.0,
                    "p95_latency_ms": 0.0,
                    "error_rate": 0.0,
                    "pp1_usage_rate": 0.0,
                    "period_days": days
                }

        except Exception as e:
            logger.error(f"Error getting summary metrics: {e}")
            raise

    @staticmethod
    async def get_user_type_metrics(days: int = 7) -> List[Dict[str, Any]]:
        """
        Get metrics grouped by user type
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {"ts": {"$gte": since_date}}},
                {"$group": {
                    "_id": "$user.type",
                    "total_requests": {"$sum": 1},
                    "avg_latency_ms": {"$avg": "$timing_ms"},
                    "success_count": {"$sum": {"$cond": [{"$eq": ["$status_code", 200]}, 1, 0]}}
                }},
                {"$project": {
                    "user_type": "$_id",
                    "total_requests": 1,
                    "avg_latency_ms": {"$round": ["$avg_latency_ms", 2]},
                    "success_rate": {"$round": [{"$divide": ["$success_count", "$total_requests"]}, 3]}
                }},
                {"$sort": {"total_requests": -1}}
            ]

            result = await db.access_logs.aggregate(pipeline).to_list(length=None)
            return result

        except Exception as e:
            logger.error(f"Error getting user type metrics: {e}")
            raise

    @staticmethod
    async def get_decision_metrics(days: int = 7) -> List[Dict[str, Any]]:
        """
        Get metrics grouped by decision type (identified/ambiguous/unknown)
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {"ts": {"$gte": since_date}}},
                {"$group": {
                    "_id": "$decision",
                    "count": {"$sum": 1}
                }},
                {"$group": {
                    "_id": None,
                    "decisions": {"$push": {"decision": "$_id", "count": "$count"}},
                    "total": {"$sum": "$count"}
                }},
                {"$unwind": "$decisions"},
                {"$project": {
                    "_id": 0,
                    "decision": "$decisions.decision",
                    "count": "$decisions.count",
                    "percentage": {"$round": [{"$multiply": [{"$divide": ["$decisions.count", "$total"]}, 100]}, 1]}
                }},
                {"$sort": {"count": -1}}
            ]

            result = await db.access_logs.aggregate(pipeline).to_list(length=None)
            return result

        except Exception as e:
            logger.error(f"Error getting decision metrics: {e}")
            raise

    @staticmethod
    async def get_service_metrics(days: int = 7) -> List[Dict[str, Any]]:
        """
        Get metrics for PP2/PP1 services performance
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {"ts": {"$gte": since_date}}},
                {"$group": {
                    "_id": "$service_name",
                    "service_type": {"$first": "$service_type"},
                    "total_calls": {"$sum": 1},
                    "avg_latency_ms": {"$avg": "$latency_ms"},
                    "timeout_count": {"$sum": {"$cond": ["$timeout", 1, 0]}},
                    "error_count": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}}
                }},
                {"$project": {
                    "service_name": "$_id",
                    "service_type": 1,
                    "total_calls": 1,
                    "avg_latency_ms": {"$round": ["$avg_latency_ms", 2]},
                    "timeout_count": 1,
                    "error_count": 1,
                    "success_rate": {"$round": [{"$divide": [
                        {"$subtract": ["$total_calls", "$error_count"]},
                        "$total_calls"
                    ]}, 3]}
                }},
                {"$sort": {"total_calls": -1}}
            ]

            result = await db.service_logs.aggregate(pipeline).to_list(length=None)
            return result

        except Exception as e:
            logger.error(f"Error getting service metrics: {e}")
            raise

    @staticmethod
    async def get_hourly_volume(days: int = 7) -> List[Dict[str, Any]]:
        """
        Get request volume by hour for trend analysis
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {"ts": {"$gte": since_date}}},
                {"$group": {
                    "_id": {
                        "year": {"$year": "$ts"},
                        "month": {"$month": "$ts"},
                        "day": {"$dayOfMonth": "$ts"},
                        "hour": {"$hour": "$ts"}
                    },
                    "requests": {"$sum": 1},
                    "avg_latency": {"$avg": "$timing_ms"}
                }},
                {"$project": {
                    "timestamp": {
                        "$dateFromParts": {
                            "year": "$_id.year",
                            "month": "$_id.month",
                            "day": "$_id.day",
                            "hour": "$_id.hour"
                        }
                    },
                    "requests": 1,
                    "avg_latency": {"$round": ["$avg_latency", 2]}
                }},
                {"$sort": {"timestamp": 1}}
            ]

            result = await db.access_logs.aggregate(pipeline).to_list(length=None)
            return result

        except Exception as e:
            logger.error(f"Error getting hourly volume: {e}")
            raise

    @staticmethod
    async def get_top_pp2_timeouts(days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get PP2 services with most timeouts
        """
        try:
            db = await get_db()

            since_date = datetime.utcnow() - timedelta(days=days)

            pipeline = [
                {"$match": {
                    "ts": {"$gte": since_date},
                    "service_type": "pp2"
                }},
                {"$group": {
                    "_id": "$service_name",
                    "total_calls": {"$sum": 1},
                    "timeouts": {"$sum": {"$cond": ["$timeout", 1, 0]}},
                    "avg_latency_ms": {"$avg": "$latency_ms"}
                }},
                {"$project": {
                    "service_name": "$_id",
                    "total_calls": 1,
                    "timeouts": 1,
                    "timeout_rate": {"$round": [{"$divide": ["$timeouts", "$total_calls"]}, 3]},
                    "avg_latency_ms": {"$round": ["$avg_latency_ms", 2]}
                }},
                {"$sort": {"timeouts": -1}},
                {"$limit": limit}
            ]

            result = await db.service_logs.aggregate(pipeline).to_list(length=None)
            return result

        except Exception as e:
            logger.error(f"Error getting PP2 timeout stats: {e}")
            raise
