"""
System Monitoring Service

Provides operational monitoring, API usage tracking, cost calculation,
and dashboard metrics for the Voice AI Platform.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from src.audit import audit_logger_instance
from src.services.openai_integration import openai_service

logger = logging.getLogger(__name__)


class SystemMonitoringService:
    """
    Operational monitoring service for the Voice AI Platform.

    Features:
    - Call counts and success rates tracking
    - API usage monitoring with cost calculation
    - Monthly budget alerts ($197 threshold)
    - Dashboard metrics for visualization
    - Performance and error rate monitoring
    """

    def __init__(self, metrics_file: str = "metrics.json"):
        """Initialize system monitoring service."""
        self.metrics_file = Path(metrics_file)
        self.monthly_budget_dollars = 197.0
        self.alert_threshold_percent = 80.0  # Alert at 80% of budget

        # Initialize metrics structure
        self.metrics = {
            "call_metrics": {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "average_call_duration": 0.0,
                "total_call_minutes": 0.0,
            },
            "api_usage": {
                "openai_requests": 0,
                "openai_audio_minutes": 0.0,
                "openai_cost_dollars": 0.0,
                "twilio_calls": 0,
                "twilio_minutes": 0.0,
                "twilio_cost_dollars": 0.0,
            },
            "error_tracking": {
                "transcription_errors": 0,
                "timeout_events": 0,
                "system_errors": 0,
                "last_error_time": None,
            },
            "monthly_summary": {
                "current_month": datetime.now(timezone.utc).strftime("%Y-%m"),
                "total_cost_dollars": 0.0,
                "budget_used_percent": 0.0,
                "calls_this_month": 0,
                "alerts_sent": 0,
            },
            "performance": {
                "average_transcription_time": 0.0,
                "average_response_time": 0.0,
                "system_uptime_percent": 99.0,
            },
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        self._load_metrics()

    def _load_metrics(self):
        """Load metrics from file."""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, "r") as f:
                    saved_metrics = json.load(f)
                    self.metrics.update(saved_metrics)

                # Check if we need to reset monthly metrics
                current_month = datetime.now(timezone.utc).strftime("%Y-%m")
                if self.metrics["monthly_summary"]["current_month"] != current_month:
                    self._reset_monthly_metrics()

                logger.info("Metrics loaded successfully")
            else:
                logger.info("No existing metrics file, starting with defaults")

        except Exception as e:
            logger.error(f"Failed to load metrics: {e}")
            # Continue with default metrics

    def _save_metrics(self):
        """Save metrics to file."""
        try:
            self.metrics["last_updated"] = datetime.now(timezone.utc).isoformat()

            # Ensure metrics directory exists
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.metrics_file, "w") as f:
                json.dump(self.metrics, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def _reset_monthly_metrics(self):
        """Reset monthly metrics at the start of a new month."""
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        # Archive previous month's data
        previous_data = {
            "month": self.metrics["monthly_summary"]["current_month"],
            "total_cost": self.metrics["monthly_summary"]["total_cost_dollars"],
            "calls": self.metrics["monthly_summary"]["calls_this_month"],
            "budget_used": self.metrics["monthly_summary"]["budget_used_percent"],
        }

        audit_logger_instance.log_system_event(
            action="MONTHLY_METRICS_RESET",
            result="SUCCESS",
            additional_data=previous_data,
        )

        # Reset monthly counters
        self.metrics["monthly_summary"] = {
            "current_month": current_month,
            "total_cost_dollars": 0.0,
            "budget_used_percent": 0.0,
            "calls_this_month": 0,
            "alerts_sent": 0,
        }

        # Reset OpenAI usage tracking
        openai_service.reset_monthly_usage()

        logger.info(f"Monthly metrics reset for {current_month}")

    def record_call_start(self, call_sid: str):
        """Record the start of a new call."""
        self.metrics["call_metrics"]["total_calls"] += 1
        self.metrics["monthly_summary"]["calls_this_month"] += 1
        self._save_metrics()

        audit_logger_instance.log_system_event(
            action="CALL_RECORDED",
            result="SUCCESS",
            additional_data={"call_sid": call_sid, "event": "start"},
        )

    def record_call_end(
        self,
        call_sid: str,
        duration_seconds: float,
        success: bool,
        error_type: Optional[str] = None,
    ):
        """Record the end of a call with duration and success status."""
        duration_minutes = duration_seconds / 60.0

        if success:
            self.metrics["call_metrics"]["successful_calls"] += 1
        else:
            self.metrics["call_metrics"]["failed_calls"] += 1
            if error_type:
                self.metrics["error_tracking"][f"{error_type}_errors"] = (
                    self.metrics["error_tracking"].get(f"{error_type}_errors", 0) + 1
                )

        # Update average call duration
        total_calls = self.metrics["call_metrics"]["total_calls"]
        current_total_minutes = self.metrics["call_metrics"]["total_call_minutes"]
        new_total_minutes = current_total_minutes + duration_minutes

        self.metrics["call_metrics"]["total_call_minutes"] = new_total_minutes
        self.metrics["call_metrics"]["average_call_duration"] = new_total_minutes / max(
            total_calls, 1
        )

        self._save_metrics()

        audit_logger_instance.log_system_event(
            action="CALL_RECORDED",
            result="SUCCESS",
            additional_data={
                "call_sid": call_sid,
                "event": "end",
                "duration_seconds": duration_seconds,
                "success": success,
                "error_type": error_type,
            },
        )

    def record_api_usage(
        self,
        service: str,
        request_type: str,
        cost_dollars: float,
        duration: Optional[float] = None,
        success: bool = True,
    ):
        """Record API usage and costs."""
        if service == "openai":
            self.metrics["api_usage"]["openai_requests"] += 1
            self.metrics["api_usage"]["openai_cost_dollars"] += cost_dollars
            if duration:
                self.metrics["api_usage"]["openai_audio_minutes"] += duration

        elif service == "twilio":
            self.metrics["api_usage"]["twilio_calls"] += 1
            self.metrics["api_usage"]["twilio_cost_dollars"] += cost_dollars
            if duration:
                self.metrics["api_usage"]["twilio_minutes"] += duration

        # Update monthly cost tracking
        self.metrics["monthly_summary"]["total_cost_dollars"] += cost_dollars
        self.metrics["monthly_summary"]["budget_used_percent"] = (
            self.metrics["monthly_summary"]["total_cost_dollars"]
            / self.monthly_budget_dollars
        ) * 100

        # Check for budget alerts
        self._check_budget_alerts()
        self._save_metrics()

    def _check_budget_alerts(self):
        """Check if budget alerts should be sent."""
        budget_used = self.metrics["monthly_summary"]["budget_used_percent"]
        alerts_sent = self.metrics["monthly_summary"]["alerts_sent"]

        # Send alert at 80%, 90%, and 100% of budget
        alert_thresholds = [80.0, 90.0, 100.0]

        for threshold in alert_thresholds:
            if budget_used >= threshold and alerts_sent < len(alert_thresholds):
                self._send_budget_alert(threshold, budget_used)
                self.metrics["monthly_summary"]["alerts_sent"] = alerts_sent + 1
                break

    def _send_budget_alert(self, threshold: float, current_usage: float):
        """Send budget alert (dashboard indication for MVP)."""
        alert_data = {
            "threshold": threshold,
            "current_usage": current_usage,
            "current_cost": self.metrics["monthly_summary"]["total_cost_dollars"],
            "budget": self.monthly_budget_dollars,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Log alert
        audit_logger_instance.log_system_event(
            action="BUDGET_ALERT", result="SUCCESS", additional_data=alert_data
        )

        logger.warning(
            f"Budget alert: {current_usage:.1f}% of monthly budget used "
            f"(${self.metrics['monthly_summary']['total_cost_dollars']:.2f} "
            f"of ${self.monthly_budget_dollars})"
        )

    def record_error(self, error_type: str, error_details: Optional[Dict] = None):
        """Record system errors for monitoring."""
        self.metrics["error_tracking"]["system_errors"] += 1
        self.metrics["error_tracking"]["last_error_time"] = datetime.now(
            timezone.utc
        ).isoformat()

        if error_type in self.metrics["error_tracking"]:
            self.metrics["error_tracking"][error_type] += 1

        self._save_metrics()

        audit_logger_instance.log_system_event(
            action="ERROR_RECORDED",
            result="SUCCESS",
            additional_data={"error_type": error_type, "details": error_details or {}},
        )

    def get_dashboard_metrics(self) -> Dict[str, any]:
        """Get metrics formatted for dashboard display."""
        # Sync with OpenAI service usage
        openai_stats = openai_service.get_usage_stats()

        # Update OpenAI metrics from service
        self.metrics["api_usage"]["openai_requests"] = openai_stats["total_requests"]
        self.metrics["api_usage"]["openai_audio_minutes"] = openai_stats[
            "total_audio_minutes"
        ]
        self.metrics["api_usage"]["openai_cost_dollars"] = openai_stats["cost_dollars"]

        # Recalculate monthly totals
        total_cost = (
            self.metrics["api_usage"]["openai_cost_dollars"]
            + self.metrics["api_usage"]["twilio_cost_dollars"]
        )
        self.metrics["monthly_summary"]["total_cost_dollars"] = total_cost
        self.metrics["monthly_summary"]["budget_used_percent"] = (
            total_cost / self.monthly_budget_dollars
        ) * 100

        # Calculate success rates
        total_calls = self.metrics["call_metrics"]["total_calls"]
        success_rate = (
            self.metrics["call_metrics"]["successful_calls"] / max(total_calls, 1)
        ) * 100

        return {
            "current_time": datetime.now(timezone.utc).isoformat(),
            "call_statistics": {
                "total_calls": total_calls,
                "successful_calls": self.metrics["call_metrics"]["successful_calls"],
                "failed_calls": self.metrics["call_metrics"]["failed_calls"],
                "success_rate_percent": round(success_rate, 1),
                "average_duration_minutes": round(
                    self.metrics["call_metrics"]["average_call_duration"], 2
                ),
            },
            "cost_tracking": {
                "monthly_budget": self.monthly_budget_dollars,
                "current_cost": round(
                    self.metrics["monthly_summary"]["total_cost_dollars"], 2
                ),
                "budget_used_percent": round(
                    self.metrics["monthly_summary"]["budget_used_percent"], 1
                ),
                "openai_cost": round(
                    self.metrics["api_usage"]["openai_cost_dollars"], 2
                ),
                "twilio_cost": round(
                    self.metrics["api_usage"]["twilio_cost_dollars"], 2
                ),
                "remaining_budget": round(
                    self.monthly_budget_dollars
                    - self.metrics["monthly_summary"]["total_cost_dollars"],
                    2,
                ),
                "alert_status": "warning"
                if self.metrics["monthly_summary"]["budget_used_percent"] >= 80
                else "normal",
            },
            "api_usage": {
                "openai_requests": self.metrics["api_usage"]["openai_requests"],
                "openai_audio_minutes": round(
                    self.metrics["api_usage"]["openai_audio_minutes"], 2
                ),
                "twilio_calls": self.metrics["api_usage"]["twilio_calls"],
                "twilio_minutes": round(self.metrics["api_usage"]["twilio_minutes"], 2),
                "openai_success_rate": openai_stats["success_rate"],
            },
            "error_summary": {
                "total_errors": self.metrics["error_tracking"]["system_errors"],
                "transcription_errors": self.metrics["error_tracking"][
                    "transcription_errors"
                ],
                "timeout_events": self.metrics["error_tracking"]["timeout_events"],
                "last_error": self.metrics["error_tracking"]["last_error_time"],
            },
            "monthly_summary": self.metrics["monthly_summary"],
        }

    def get_cost_projection(self) -> Dict[str, any]:
        """Calculate projected monthly costs based on current usage."""
        current_date = datetime.now(timezone.utc)
        days_in_month = (
            current_date.replace(month=current_date.month + 1, day=1)
            - current_date.replace(day=1)
        ).days
        days_elapsed = current_date.day

        current_cost = self.metrics["monthly_summary"]["total_cost_dollars"]

        if days_elapsed > 0:
            daily_average = current_cost / days_elapsed
            projected_monthly = daily_average * days_in_month
        else:
            projected_monthly = 0

        return {
            "current_cost": round(current_cost, 2),
            "projected_monthly": round(projected_monthly, 2),
            "budget": self.monthly_budget_dollars,
            "projected_over_budget": projected_monthly > self.monthly_budget_dollars,
            "projected_over_amount": max(
                0, round(projected_monthly - self.monthly_budget_dollars, 2)
            ),
            "days_elapsed": days_elapsed,
            "days_remaining": days_in_month - days_elapsed,
        }

    def export_metrics(self, format_type: str = "json") -> str:
        """Export metrics in specified format."""
        if format_type == "json":
            return json.dumps(self.get_dashboard_metrics(), indent=2)
        else:
            # Could add CSV, XML formats in future
            return json.dumps(self.get_dashboard_metrics(), indent=2)

    def test_monitoring(self) -> bool:
        """Test the monitoring system."""
        try:
            # Test recording a sample call
            test_call_id = "test_call_123"
            self.record_call_start(test_call_id)
            self.record_call_end(test_call_id, 120.0, True)

            # Test API usage recording
            self.record_api_usage("openai", "transcription", 0.05, 2.0, True)

            # Test error recording
            self.record_error("test_error", {"test": True})

            # Verify metrics were updated
            metrics = self.get_dashboard_metrics()
            if metrics["call_statistics"]["total_calls"] > 0:
                logger.info("Monitoring system test successful")
                return True
            else:
                logger.error("Monitoring system test failed - no metrics recorded")
                return False

        except Exception as e:
            logger.error(f"Monitoring system test failed: {e}")
            return False

    def track_dashboard_view(self, appointment_count: int):
        """
        Track dashboard view event.

        Args:
            appointment_count: Number of appointments displayed
        """
        try:
            if "dashboard_metrics" not in self.metrics:
                self.metrics["dashboard_metrics"] = {
                    "total_views": 0,
                    "appointments_displayed": 0,
                    "last_viewed": None,
                }

            self.metrics["dashboard_metrics"]["total_views"] += 1
            self.metrics["dashboard_metrics"][
                "appointments_displayed"
            ] += appointment_count
            self.metrics["dashboard_metrics"]["last_viewed"] = datetime.now(
                timezone.utc
            ).isoformat()

            self._save_metrics()
            logger.info(f"Dashboard view tracked: {appointment_count} appointments")

        except Exception as e:
            logger.error(f"Failed to track dashboard view: {e}")

    def track_ai_appointment(self, status: str, confidence: float):
        """
        Track AI-scheduled appointment.

        Args:
            status: Appointment status (confirmed, pending, failed)
            confidence: AI confidence score (0.0-1.0)
        """
        try:
            if "ai_appointments" not in self.metrics:
                self.metrics["ai_appointments"] = {
                    "total_scheduled": 0,
                    "confirmed": 0,
                    "pending": 0,
                    "failed": 0,
                    "average_confidence": 0.0,
                }

            self.metrics["ai_appointments"]["total_scheduled"] += 1

            if status in ["confirmed", "pending", "failed"]:
                self.metrics["ai_appointments"][status] += 1

            # Update average confidence
            current_total = self.metrics["ai_appointments"]["total_scheduled"]
            current_avg = self.metrics["ai_appointments"]["average_confidence"]
            new_avg = ((current_avg * (current_total - 1)) + confidence) / current_total
            self.metrics["ai_appointments"]["average_confidence"] = round(new_avg, 3)

            self._save_metrics()
            logger.info(
                f"AI appointment tracked: status={status}, confidence={confidence}"
            )

        except Exception as e:
            logger.error(f"Failed to track AI appointment: {e}")


# Global service instance
monitoring_service = SystemMonitoringService()
