"""
Health Monitoring Service for ClipForge
Provides comprehensive health checks, monitoring metrics, and alerting
"""

import asyncio
import shutil
import time
from datetime import datetime
from typing import Any, Dict

import psutil
from core.config import settings
from core.logging import get_logger, performance_logger
from infrastructure.database import check_database_health, get_db_session
from sqlalchemy import text

logger = get_logger("health_service")


class HealthMonitoringService:
    """Comprehensive health monitoring service"""

    def __init__(self) -> None:
        self._error_counts: Dict[str, int] = {}
        self._last_error_check = datetime.utcnow()
        self._performance_metrics: Dict[str, Any] = {
            "request_count": 0,
            "error_count": 0,
            "avg_response_time": 0,
            "last_reset": datetime.utcnow(),
        }

    async def get_comprehensive_health(self) -> Dict[str, Any]:
        """Get comprehensive health status of all system components"""
        start_time = time.time()

        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "service": settings.app_name,
            "version": settings.app_version,
            "uptime_seconds": self._get_uptime(),
            "checks": {},
        }

        # Perform all health checks concurrently
        checks = await asyncio.gather(
            self._check_database_health(),
            self._check_storage_health(),
            self._check_external_services_health(),
            self._check_system_resources(),
            self._check_error_rates(),
            return_exceptions=True,
        )

        check_names = [
            "database",
            "storage",
            "external_services",
            "system_resources",
            "error_rates",
        ]

        # Process check results
        overall_healthy = True
        for name, result in zip(check_names, checks):
            if isinstance(result, Exception):
                health_status["checks"][name] = {  # type: ignore[index]
                    "status": "unhealthy",
                    "error": str(result),
                }
                overall_healthy = False
            else:
                health_status["checks"][name] = result  # type: ignore[index]
                if isinstance(result, dict) and result.get("status") != "healthy":
                    overall_healthy = False

        # Set overall status
        if not overall_healthy:
            health_status["status"] = "unhealthy"

        # Log performance metrics
        duration_ms = (time.time() - start_time) * 1000
        performance_logger.log_request_duration(
            "/health", "GET", duration_ms, 200 if overall_healthy else 503
        )

        return health_status

    async def _check_database_health(self) -> Dict[str, Any]:
        """Check database connectivity and performance"""
        start_time = time.time()

        try:
            # Get basic health from existing function
            basic_health = check_database_health()

            # Add performance metrics
            with get_db_session() as session:
                # Test query performance
                query_start = time.time()
                session.execute(text("SELECT COUNT(*) FROM users"))
                query_duration = (time.time() - query_start) * 1000

                # Check connection pool status (if applicable)
                pool_status = {
                    "active_connections": "N/A (SQLite)",
                    "pool_size": "N/A (SQLite)",
                }

                duration_ms = (time.time() - start_time) * 1000
                performance_logger.log_database_query_duration("health_check", duration_ms)

                return {
                    "status": basic_health.get("database", "unknown"),
                    "connection": basic_health.get("connection", False),
                    "tables_exist": basic_health.get("tables_exist", False),
                    "query_performance_ms": round(query_duration, 2),
                    "pool_status": pool_status,
                    "last_checked": datetime.utcnow().isoformat() + "Z",
                }

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

    async def _check_storage_health(self) -> Dict[str, Any]:
        """Check storage capacity and accessibility"""
        try:
            clips_path = settings.absolute_clips_path

            # Check if path exists and is accessible
            if not clips_path.exists():
                return {
                    "status": "unhealthy",
                    "error": f"Storage path does not exist: {clips_path}",
                    "path": str(clips_path),
                }

            if not clips_path.is_dir():
                return {
                    "status": "unhealthy",
                    "error": f"Storage path is not a directory: {clips_path}",
                    "path": str(clips_path),
                }

            # Check disk space
            total, used, free = shutil.disk_usage(clips_path)
            free_gb = free // (1024**3)
            total_gb = total // (1024**3)
            used_percent = (used / total) * 100

            # Determine health based on free space
            status = "healthy"
            warnings = []

            if free_gb < 1:  # Less than 1GB free
                status = "unhealthy"
                warnings.append("Critical: Less than 1GB free space")
            elif free_gb < 5:  # Less than 5GB free
                status = "degraded"
                warnings.append("Warning: Less than 5GB free space")
            elif used_percent > 90:
                status = "degraded"
                warnings.append("Warning: Disk usage over 90%")

            # Test write permissions
            test_file = clips_path / ".health_check_temp"
            try:
                test_file.write_text("health check")
                test_file.unlink()
                writable = True
            except Exception:
                writable = False
                status = "unhealthy"
                warnings.append("Storage directory is not writable")

            return {
                "status": status,
                "path": str(clips_path),
                "writable": writable,
                "disk_space": {
                    "total_gb": total_gb,
                    "used_gb": (used // (1024**3)),
                    "free_gb": free_gb,
                    "used_percent": round(used_percent, 2),
                },
                "warnings": warnings,
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

        except Exception as e:
            logger.error(f"Storage health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

    async def _check_external_services_health(self) -> Dict[str, Any]:
        """Check health of external services (Plex, etc.)"""
        try:
            services_status = {
                "status": "healthy",
                "services": {},
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

            # For now, we'll do a basic check
            # In the future, this could include actual Plex server connectivity
            services_status["services"]["plex"] = {  # type: ignore[index]
                "status": "healthy",
                "note": "Basic check only - actual connectivity requires user token",
            }

            return services_status

        except Exception as e:
            logger.error(f"External services health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "services": {},
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available_gb = memory.available / (1024**3)

            # Determine status based on resource usage
            status = "healthy"
            warnings = []

            if cpu_percent > 90:
                status = "degraded"
                warnings.append(f"High CPU usage: {cpu_percent}%")
            elif cpu_percent > 80:
                warnings.append(f"Elevated CPU usage: {cpu_percent}%")

            if memory_percent > 90:
                status = "degraded"
                warnings.append(f"High memory usage: {memory_percent}%")
            elif memory_percent > 80:
                warnings.append(f"Elevated memory usage: {memory_percent}%")

            if memory_available_gb < 0.5:  # Less than 500MB available
                status = "unhealthy"
                warnings.append(f"Critical: Low available memory: {memory_available_gb:.1f}GB")

            return {
                "status": status,
                "cpu_percent": round(cpu_percent, 1),
                "memory": {
                    "percent_used": round(memory_percent, 1),
                    "available_gb": round(memory_available_gb, 2),
                    "total_gb": round(memory.total / (1024**3), 2),
                },
                "warnings": warnings,
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

        except Exception as e:
            logger.error(f"System resources health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

    async def _check_error_rates(self) -> Dict[str, Any]:
        """Check error rates and patterns"""
        try:
            now = datetime.utcnow()

            # Calculate error rate since last check
            time_window = (now - self._last_error_check).total_seconds()
            if time_window > 0:
                error_rate = float(self._performance_metrics["error_count"]) / time_window
            else:
                error_rate = 0

            # Determine status based on error rate
            status = "healthy"
            warnings = []

            if error_rate > 5:  # More than 5 errors per second
                status = "unhealthy"
                warnings.append(f"High error rate: {error_rate:.2f} errors/second")
            elif error_rate > 1:  # More than 1 error per second
                status = "degraded"
                warnings.append(f"Elevated error rate: {error_rate:.2f} errors/second")

            # Reset counters
            self._last_error_check = now

            return {
                "status": status,
                "error_rate_per_second": round(error_rate, 3),
                "total_requests": self._performance_metrics["request_count"],
                "total_errors": self._performance_metrics["error_count"],
                "avg_response_time_ms": round(
                    float(self._performance_metrics["avg_response_time"]), 2
                ),
                "warnings": warnings,
                "last_checked": now.isoformat() + "Z",
            }

        except Exception as e:
            logger.error(f"Error rate health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "last_checked": datetime.utcnow().isoformat() + "Z",
            }

    def record_request(self, response_time_ms: float, status_code: int) -> None:
        """Record request metrics for monitoring"""
        self._performance_metrics["request_count"] = (
            int(self._performance_metrics["request_count"]) + 1
        )

        if status_code >= 400:
            self._performance_metrics["error_count"] = (
                int(self._performance_metrics["error_count"]) + 1
            )

        # Update running average response time
        current_avg = self._performance_metrics["avg_response_time"]
        request_count = self._performance_metrics["request_count"]

        # Calculate new average
        new_avg = ((float(current_avg) * (int(request_count) - 1)) + response_time_ms) / int(
            request_count
        )
        self._performance_metrics["avg_response_time"] = new_avg

    def _get_uptime(self) -> int:
        """Get application uptime in seconds"""
        # This is a simple implementation - in production, you might store start time
        return int(time.time() - psutil.boot_time())

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get a summary of key metrics for monitoring dashboards"""
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "requests_total": self._performance_metrics["request_count"],
            "errors_total": self._performance_metrics["error_count"],
            "avg_response_time_ms": round(float(self._performance_metrics["avg_response_time"]), 2),
            "uptime_seconds": self._get_uptime(),
            "last_reset": self._performance_metrics["last_reset"].isoformat() + "Z",
        }

    def reset_metrics(self) -> None:
        """Reset performance metrics (useful for testing or scheduled resets)"""
        self._performance_metrics = {
            "request_count": 0,
            "error_count": 0,
            "avg_response_time": 0,
            "last_reset": datetime.utcnow(),
        }
        self._error_counts.clear()
        logger.info("Health monitoring metrics reset")


# Global instance
health_service = HealthMonitoringService()
