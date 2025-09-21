"""
Schedule Data Refresh Background Task

This module provides automatic refresh functionality for provider schedule data
with configurable intervals and error handling.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..audit import log_audit_event
from .provider_schedule import ProviderScheduleService

logger = logging.getLogger(__name__)


class RefreshStatus(Enum):
    """Status of schedule refresh operation."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    STOPPED = "stopped"


class ScheduleRefreshService:
    """Service for automatic schedule data refresh."""

    def __init__(
        self,
        schedule_service: ProviderScheduleService,
        refresh_interval_minutes: int = 15,
    ):
        """
        Initialize refresh service.

        Args:
            schedule_service: Provider schedule service instance
            refresh_interval_minutes: Refresh interval in minutes (default: 15)
        """
        self.schedule_service = schedule_service
        self.refresh_interval = refresh_interval_minutes * 60  # Convert to seconds

        self._task: Optional[asyncio.Task] = None
        self._status = RefreshStatus.IDLE
        self._last_refresh_time: Optional[float] = None
        self._last_error: Optional[str] = None
        self._refresh_count = 0
        self._error_count = 0
        self._stop_event = asyncio.Event()

        # Callbacks for status updates
        self._status_callbacks: List[Callable[[RefreshStatus, Dict], None]] = []

    @property
    def status(self) -> RefreshStatus:
        """Get current refresh status."""
        return self._status

    @property
    def is_running(self) -> bool:
        """Check if refresh task is running."""
        return self._task is not None and not self._task.done()

    @property
    def last_refresh_time(self) -> Optional[datetime]:
        """Get last successful refresh time."""
        if self._last_refresh_time:
            return datetime.fromtimestamp(self._last_refresh_time)
        return None

    @property
    def next_refresh_time(self) -> Optional[datetime]:
        """Get next scheduled refresh time."""
        if self._last_refresh_time:
            next_time = self._last_refresh_time + self.refresh_interval
            return datetime.fromtimestamp(next_time)
        return None

    @property
    def refresh_stats(self) -> Dict[str, Any]:
        """Get refresh statistics."""
        return {
            "status": self._status.value,
            "refresh_count": self._refresh_count,
            "error_count": self._error_count,
            "last_refresh_time": self.last_refresh_time.isoformat()
            if self.last_refresh_time
            else None,
            "next_refresh_time": self.next_refresh_time.isoformat()
            if self.next_refresh_time
            else None,
            "last_error": self._last_error,
            "refresh_interval_minutes": self.refresh_interval // 60,
            "is_running": self.is_running,
        }

    def add_status_callback(self, callback: Callable[[RefreshStatus, Dict], None]):
        """Add callback function for status updates."""
        self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[RefreshStatus, Dict], None]):
        """Remove callback function."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def _notify_status_change(
        self, status: RefreshStatus, extra_data: Optional[Dict] = None
    ):
        """Notify all callbacks of status change."""
        self._status = status
        data = self.refresh_stats.copy()
        if extra_data:
            data.update(extra_data)

        for callback in self._status_callbacks:
            try:
                callback(status, data)
            except Exception as e:
                logger.warning(f"Status callback error: {e}")

    async def start(self):
        """Start the automatic refresh task."""
        if self.is_running:
            logger.warning("Refresh task is already running")
            return

        logger.info(
            f"Starting schedule refresh service (interval: {self.refresh_interval // 60} minutes)"
        )

        # Reset stop event
        self._stop_event.clear()

        # Create and start background task
        self._task = asyncio.create_task(self._refresh_loop())

        # Log service start
        log_audit_event(
            "schedule_refresh_started",
            "Schedule refresh service started",
            additional_data={"refresh_interval_minutes": self.refresh_interval // 60},
        )

        self._notify_status_change(RefreshStatus.RUNNING)

    async def stop(self):
        """Stop the automatic refresh task."""
        if not self.is_running:
            logger.warning("Refresh task is not running")
            return

        logger.info("Stopping schedule refresh service")

        # Signal stop
        self._stop_event.set()

        # Wait for task to complete
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Refresh task did not stop gracefully, cancelling")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        # Log service stop
        log_audit_event(
            "schedule_refresh_stopped",
            "Schedule refresh service stopped",
            additional_data=self.refresh_stats,
        )

        self._notify_status_change(RefreshStatus.STOPPED)

    async def refresh_now(self) -> bool:
        """Perform immediate refresh of schedule data."""
        logger.info("Performing immediate schedule refresh")

        self._notify_status_change(RefreshStatus.RUNNING, {"manual_refresh": True})

        try:
            # Clear cache to force fresh data
            self.schedule_service.clear_schedule_cache()

            # Get current providers to refresh their schedules
            providers = await self.schedule_service.get_providers()

            # Refresh schedules for each provider
            start_date = datetime.now().isoformat()
            end_date = (datetime.now() + timedelta(days=30)).isoformat()

            total_schedules = 0
            for provider in providers:
                provider_ref = f"Practitioner/{provider.id}"
                schedules = await self.schedule_service.get_provider_schedules(
                    practitioner_reference=provider_ref,
                    start_date=start_date,
                    end_date=end_date,
                )
                total_schedules += len(schedules)

            # Update refresh tracking
            self._last_refresh_time = time.time()
            self._refresh_count += 1
            self._last_error = None

            # Log successful refresh
            log_audit_event(
                "schedule_refresh_completed",
                "Schedule data refresh completed successfully",
                additional_data={
                    "provider_count": len(providers),
                    "schedule_count": total_schedules,
                    "manual_refresh": True,
                },
            )

            logger.info(
                f"Schedule refresh completed: {len(providers)} providers, {total_schedules} schedules"
            )

            self._notify_status_change(
                RefreshStatus.SUCCESS,
                {"provider_count": len(providers), "schedule_count": total_schedules},
            )

            return True

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)

            # Log refresh error
            log_audit_event(
                "schedule_refresh_error",
                "Schedule data refresh failed",
                additional_data={
                    "error": str(e),
                    "error_count": self._error_count,
                    "manual_refresh": True,
                },
            )

            logger.error(f"Schedule refresh failed: {e}")

            self._notify_status_change(RefreshStatus.ERROR, {"error": str(e)})

            return False

    async def _refresh_loop(self):
        """Main refresh loop running in background."""
        logger.info("Schedule refresh loop started")

        while not self._stop_event.is_set():
            try:
                # Wait for refresh interval or stop signal
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.refresh_interval
                    )
                    # Stop event was set
                    break
                except asyncio.TimeoutError:
                    # Timeout reached, time to refresh
                    pass

                # Perform refresh
                await self.refresh_now()

            except asyncio.CancelledError:
                logger.info("Refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in refresh loop: {e}")
                # Continue loop even on error

        logger.info("Schedule refresh loop stopped")

    async def get_refresh_health(self) -> Dict[str, Any]:
        """Get health status of refresh service."""
        current_time = time.time()
        health: Dict[str, Any] = {
            "status": self._status.value,
            "is_healthy": True,
            "issues": [],
        }

        # Check if refresh is overdue
        if self._last_refresh_time:
            time_since_refresh = current_time - self._last_refresh_time
            expected_refresh_time = self.refresh_interval * 1.2  # 20% tolerance

            if time_since_refresh > expected_refresh_time:
                health["is_healthy"] = False
                health["issues"].append(
                    f"Refresh overdue by {int((time_since_refresh - self.refresh_interval) / 60)} minutes"
                )

        # Check error rate
        if self._refresh_count > 0:
            error_rate = self._error_count / self._refresh_count
            if error_rate > 0.2:  # 20% error rate threshold
                health["is_healthy"] = False
                health["issues"].append(f"High error rate: {error_rate:.1%}")

        # Check if service should be running but isn't
        if self._status == RefreshStatus.RUNNING and not self.is_running:
            health["is_healthy"] = False
            health["issues"].append("Service marked as running but task is not active")

        health.update(self.refresh_stats)
        return health
