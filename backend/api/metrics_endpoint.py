"""
Metrics and Monitoring Endpoints for ClipForge
Provides Prometheus-compatible metrics and performance monitoring
"""

import logging
import time
from collections import defaultdict, deque
from typing import Any, Dict

from api.dependencies import setup_request_context
from core.config import settings
from fastapi import APIRouter, Depends, HTTPException
from services.cache_service import get_cache

logger = logging.getLogger(__name__)

# Global metrics storage
request_metrics: Dict[str, Any] = {
    "request_count": defaultdict(int),
    "request_duration": defaultdict(deque),
    "error_count": defaultdict(int),
    "status_codes": defaultdict(int),
}

# Performance tracking
performance_data: Dict[str, Any] = {
    "start_time": time.time(),
    "requests_total": 0,
    "errors_total": 0,
    "cache_hits": 0,
    "cache_misses": 0,
}

metrics_router = APIRouter(prefix="/metrics", tags=["monitoring"])


def record_request_metric(duration_ms: float, status_code: int, endpoint: str = "unknown") -> None:
    """Record request metrics for monitoring"""
    performance_data["requests_total"] += 1

    # Track by endpoint
    request_metrics["request_count"][endpoint] += 1
    request_metrics["status_codes"][status_code] += 1

    # Track duration (keep last 1000 requests)
    duration_deque = request_metrics["request_duration"][endpoint]
    duration_deque.append(duration_ms)
    if len(duration_deque) > 1000:
        duration_deque.popleft()

    # Track errors
    if status_code >= 400:
        performance_data["errors_total"] += 1
        request_metrics["error_count"][endpoint] += 1


def record_cache_metric(hit: bool) -> None:
    """Record cache hit/miss metrics"""
    if hit:
        performance_data["cache_hits"] += 1
    else:
        performance_data["cache_misses"] += 1


@metrics_router.get("/prometheus")
async def prometheus_metrics(_: str = Depends(setup_request_context)) -> str:
    """
    Prometheus-compatible metrics endpoint
    Returns metrics in Prometheus text format
    """

    cache = get_cache()
    cache_stats = await cache.get_stats()

    current_time = time.time()
    uptime = current_time - performance_data["start_time"]

    # Calculate rates
    requests_per_second = performance_data["requests_total"] / uptime if uptime > 0 else 0
    error_rate = (
        performance_data["errors_total"] / performance_data["requests_total"]
        if performance_data["requests_total"] > 0
        else 0
    )
    cache_hit_rate = (
        performance_data["cache_hits"]
        / (performance_data["cache_hits"] + performance_data["cache_misses"])
        if (performance_data["cache_hits"] + performance_data["cache_misses"]) > 0
        else 0
    )

    # Build Prometheus metrics
    metrics_lines = [
        "# HELP clipforge_requests_total Total number of HTTP requests",
        "# TYPE clipforge_requests_total counter",
        f"clipforge_requests_total {performance_data['requests_total']}",
        "",
        "# HELP clipforge_errors_total Total number of HTTP errors",
        "# TYPE clipforge_errors_total counter",
        f"clipforge_errors_total {performance_data['errors_total']}",
        "",
        "# HELP clipforge_request_rate_per_second Current request rate per second",
        "# TYPE clipforge_request_rate_per_second gauge",
        f"clipforge_request_rate_per_second {requests_per_second:.2f}",
        "",
        "# HELP clipforge_error_rate Error rate (errors/total requests)",
        "# TYPE clipforge_error_rate gauge",
        f"clipforge_error_rate {error_rate:.4f}",
        "",
        "# HELP clipforge_uptime_seconds Application uptime in seconds",
        "# TYPE clipforge_uptime_seconds gauge",
        f"clipforge_uptime_seconds {uptime:.0f}",
        "",
        "# HELP clipforge_cache_hits_total Total cache hits",
        "# TYPE clipforge_cache_hits_total counter",
        f"clipforge_cache_hits_total {performance_data['cache_hits']}",
        "",
        "# HELP clipforge_cache_misses_total Total cache misses",
        "# TYPE clipforge_cache_misses_total counter",
        f"clipforge_cache_misses_total {performance_data['cache_misses']}",
        "",
        "# HELP clipforge_cache_hit_rate Cache hit rate (hits/(hits+misses))",
        "# TYPE clipforge_cache_hit_rate gauge",
        f"clipforge_cache_hit_rate {cache_hit_rate:.4f}",
        "",
        "# HELP clipforge_cache_entries_active Active cache entries",
        "# TYPE clipforge_cache_entries_active gauge",
        f"clipforge_cache_entries_active {cache_stats['active_entries']}",
        "",
        "# HELP clipforge_cache_size_bytes Estimated cache size in bytes",
        "# TYPE clipforge_cache_size_bytes gauge",
        f"clipforge_cache_size_bytes {cache_stats['estimated_size_bytes']}",
    ]

    # Add per-endpoint metrics
    for endpoint, count in request_metrics["request_count"].items():
        metrics_lines.extend(
            [
                "",
                "# HELP clipforge_requests_by_endpoint_total Requests by endpoint",
                "# TYPE clipforge_requests_by_endpoint_total counter",
                f'clipforge_requests_by_endpoint_total{{endpoint="{endpoint}"}} {count}',
            ]
        )

    # Add status code metrics
    for status_code, count in request_metrics["status_codes"].items():
        metrics_lines.extend(
            [
                "",
                f'clipforge_responses_by_status_total{{status="{status_code}"}} {count}',
            ]
        )

    return "\n".join(metrics_lines)


@metrics_router.get("/health/detailed")
async def detailed_health_metrics(
    _: str = Depends(setup_request_context),
) -> Dict[str, Any]:
    """
    Detailed health metrics in JSON format
    """

    cache = get_cache()
    cache_stats = await cache.get_stats()

    current_time = time.time()
    uptime = current_time - performance_data["start_time"]

    # Calculate endpoint statistics
    endpoint_stats = {}
    for endpoint in request_metrics["request_count"].keys():
        durations = list(request_metrics["request_duration"][endpoint])
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            min_duration = min(durations)

            # Calculate percentiles
            sorted_durations = sorted(durations)
            p50_idx = int(len(sorted_durations) * 0.5)
            p95_idx = int(len(sorted_durations) * 0.95)
            p99_idx = int(len(sorted_durations) * 0.99)

            endpoint_stats[endpoint] = {
                "requests": request_metrics["request_count"][endpoint],
                "errors": request_metrics["error_count"][endpoint],
                "avg_duration_ms": round(avg_duration, 2),
                "min_duration_ms": round(min_duration, 2),
                "max_duration_ms": round(max_duration, 2),
                "p50_duration_ms": (
                    round(sorted_durations[p50_idx], 2) if p50_idx < len(sorted_durations) else 0
                ),
                "p95_duration_ms": (
                    round(sorted_durations[p95_idx], 2) if p95_idx < len(sorted_durations) else 0
                ),
                "p99_duration_ms": (
                    round(sorted_durations[p99_idx], 2) if p99_idx < len(sorted_durations) else 0
                ),
            }

    return {
        "status": "healthy",
        "timestamp": current_time,
        "uptime_seconds": round(uptime, 0),
        "performance": {
            "requests_total": performance_data["requests_total"],
            "errors_total": performance_data["errors_total"],
            "requests_per_second": (
                round(performance_data["requests_total"] / uptime, 2) if uptime > 0 else 0
            ),
            "error_rate": (
                round(
                    performance_data["errors_total"] / performance_data["requests_total"],
                    4,
                )
                if performance_data["requests_total"] > 0
                else 0
            ),
        },
        "cache": {
            "hits": performance_data["cache_hits"],
            "misses": performance_data["cache_misses"],
            "hit_rate": (
                round(
                    performance_data["cache_hits"]
                    / (performance_data["cache_hits"] + performance_data["cache_misses"]),
                    4,
                )
                if (performance_data["cache_hits"] + performance_data["cache_misses"]) > 0
                else 0
            ),
            "active_entries": cache_stats["active_entries"],
            "expired_entries": cache_stats["expired_entries"],
            "estimated_size_bytes": cache_stats["estimated_size_bytes"],
        },
        "endpoints": endpoint_stats,
        "status_codes": dict(request_metrics["status_codes"]),
    }


@metrics_router.get("/performance/summary")
async def performance_summary(
    _: str = Depends(setup_request_context),
) -> Dict[str, Any]:
    """
    Performance summary for dashboard
    """

    current_time = time.time()
    uptime = current_time - performance_data["start_time"]

    # Find slowest endpoints
    slowest_endpoints = []
    for endpoint in request_metrics["request_count"].keys():
        durations = list(request_metrics["request_duration"][endpoint])
        if durations and len(durations) >= 10:  # Only consider endpoints with enough data
            avg_duration = sum(durations) / len(durations)
            slowest_endpoints.append(
                {
                    "endpoint": endpoint,
                    "avg_duration_ms": round(avg_duration, 2),
                    "requests": request_metrics["request_count"][endpoint],
                }
            )

    slowest_endpoints.sort(key=lambda x: x["avg_duration_ms"], reverse=True)

    # Find most active endpoints
    most_active = sorted(
        [{"endpoint": k, "requests": v} for k, v in request_metrics["request_count"].items()],
        key=lambda x: x["requests"],
        reverse=True,
    )[:5]

    return {
        "uptime_hours": round(uptime / 3600, 1),
        "total_requests": performance_data["requests_total"],
        "total_errors": performance_data["errors_total"],
        "requests_per_minute": (
            round(performance_data["requests_total"] / (uptime / 60), 1) if uptime > 0 else 0
        ),
        "error_percentage": (
            round(
                (performance_data["errors_total"] / performance_data["requests_total"]) * 100,
                2,
            )
            if performance_data["requests_total"] > 0
            else 0
        ),
        "slowest_endpoints": slowest_endpoints[:5],
        "most_active_endpoints": most_active,
        "cache_efficiency": (
            round(
                performance_data["cache_hits"]
                / (performance_data["cache_hits"] + performance_data["cache_misses"])
                * 100,
                1,
            )
            if (performance_data["cache_hits"] + performance_data["cache_misses"]) > 0
            else 0
        ),
    }


@metrics_router.post("/reset")
async def reset_metrics(_: str = Depends(setup_request_context)) -> Dict[str, str]:
    """
    Reset all metrics (admin only)
    """

    # In production, add admin authentication check here
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Metrics reset only allowed in debug mode")

    global performance_data, request_metrics

    performance_data = {
        "start_time": time.time(),
        "requests_total": 0,
        "errors_total": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }

    request_metrics = {
        "request_count": defaultdict(int),
        "request_duration": defaultdict(deque),
        "error_count": defaultdict(int),
        "status_codes": defaultdict(int),
    }

    logger.info("Metrics reset by admin")

    return {"message": "Metrics reset successfully"}
