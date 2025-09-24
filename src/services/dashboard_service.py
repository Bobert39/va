"""
Dashboard Service for Real-Time Appointment Monitoring

Provides appointment data retrieval, filtering, and real-time updates
for the appointment monitoring dashboard.
"""

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AppointmentStatus(Enum):
    """Appointment status indicators for dashboard display."""

    CONFIRMED = "confirmed"
    PENDING = "pending"
    FAILED = "failed"


class DashboardService:
    """Manages appointment dashboard data and real-time updates."""

    def __init__(self, emr_service, system_monitoring, audit_service):
        """
        Initialize dashboard service.

        Args:
            emr_service: EMR integration service instance
            system_monitoring: System monitoring service instance
            audit_service: Security and audit service instance
        """
        self.emr_service = emr_service
        self.system_monitoring = system_monitoring
        self.audit_service = audit_service

        # Track AI-scheduled appointments in memory
        # TODO: SCALABILITY NOTE - Current implementation uses in-memory storage
        # which limits deployment to single instance. For production with multiple
        # instances, replace with Redis or persistent session storage (ARCH-001)
        self.ai_appointments = {}

        # WebSocket connections for real-time updates
        self.active_connections = []

        # Dashboard configuration
        self.config = {
            "max_appointments_display": 100,
            "auto_refresh_interval": 30,
            "status_colors": {
                "confirmed": "#28a745",
                "pending": "#ffc107",
                "failed": "#dc3545",
            },
        }

        logger.info("Dashboard service initialized")

    async def get_ai_scheduled_appointments(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        provider_id: Optional[str] = None,
        appointment_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve AI-scheduled appointments with filtering.

        Args:
            date_from: Start date for filtering
            date_to: End date for filtering
            provider_id: Filter by specific provider
            appointment_type: Filter by appointment type
            status: Filter by appointment status

        Returns:
            Dictionary containing filtered appointments and metadata
        """
        try:
            # Log dashboard access for HIPAA compliance
            self.audit_service.log_dashboard_access(
                user_id="dashboard_user", action="view_ai_appointments"
            )

            # Get all appointments from EMR
            if not date_from:
                date_from = datetime.now() - timedelta(days=7)
            if not date_to:
                date_to = datetime.now() + timedelta(days=30)

            # Retrieve appointments from EMR
            emr_appointments = await self.emr_service.get_appointments_range(
                start_date=date_from, end_date=date_to, provider_id=provider_id
            )

            # Filter for AI-scheduled appointments
            ai_appointments = []
            for appointment in emr_appointments:
                appointment_id = appointment.get("id")

                # Check if this appointment was scheduled by AI
                if appointment_id in self.ai_appointments:
                    ai_metadata = self.ai_appointments[appointment_id]

                    # Apply filters
                    if status and ai_metadata.get("status") != status:
                        continue
                    if appointment_type and appointment.get("type") != appointment_type:
                        continue

                    # Combine EMR data with AI metadata
                    enhanced_appointment = {
                        **appointment,
                        "booking_source": ai_metadata.get("booking_source", "voice_ai"),
                        "status": ai_metadata.get(
                            "status", AppointmentStatus.CONFIRMED.value
                        ),
                        "ai_confidence": ai_metadata.get("ai_confidence", 0.0),
                        "booking_timestamp": ai_metadata.get("booking_timestamp"),
                        "voice_call_id": ai_metadata.get("voice_call_id"),
                        "status_color": self.config["status_colors"].get(
                            ai_metadata.get("status", "confirmed"), "#6c757d"
                        ),
                    }

                    # Hash patient phone for privacy
                    if "patient_phone" in enhanced_appointment:
                        enhanced_appointment["patient_phone_hash"] = hashlib.sha256(
                            enhanced_appointment["patient_phone"].encode()
                        ).hexdigest()[:8]
                        del enhanced_appointment["patient_phone"]

                    ai_appointments.append(enhanced_appointment)

            # Sort by appointment datetime
            ai_appointments.sort(
                key=lambda x: x.get("appointment_datetime", datetime.now()),
                reverse=True,
            )

            # Limit display count
            if len(ai_appointments) > self.config["max_appointments_display"]:
                ai_appointments = ai_appointments[
                    : self.config["max_appointments_display"]
                ]

            # Track metrics
            self.system_monitoring.track_dashboard_view(
                appointment_count=len(ai_appointments)
            )

            return {
                "appointments": ai_appointments,
                "total_count": len(ai_appointments),
                "filters_applied": {
                    "date_from": date_from.isoformat() if date_from else None,
                    "date_to": date_to.isoformat() if date_to else None,
                    "provider_id": provider_id,
                    "appointment_type": appointment_type,
                    "status": status,
                },
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Failed to retrieve AI appointments: {str(e)}")
            return {
                "appointments": [],
                "total_count": 0,
                "error": "Failed to retrieve appointments",
                "status": "error",
            }

    def track_ai_appointment(
        self,
        appointment_id: str,
        voice_call_id: str,
        status: AppointmentStatus,
        ai_confidence: float,
        provider_id: str,
        appointment_type: str,
        appointment_datetime: datetime,
        patient_phone_hash: str = None,
    ):
        """
        Track an appointment that was scheduled by AI.

        Args:
            appointment_id: EMR appointment ID
            voice_call_id: Reference to original voice call
            status: Appointment status
            ai_confidence: AI confidence score (0.0-1.0)
            provider_id: Provider ID
            appointment_type: Type of appointment
            appointment_datetime: Scheduled appointment time
            patient_phone_hash: Hashed patient phone for privacy
        """
        try:
            # Store AI appointment metadata
            self.ai_appointments[appointment_id] = {
                "appointment_id": appointment_id,
                "booking_source": "voice_ai",
                "created_via": "phone_call",
                "ai_confidence": ai_confidence,
                "booking_timestamp": datetime.now().isoformat(),
                "status": status.value,
                "voice_call_id": voice_call_id,
                "patient_phone_hash": patient_phone_hash,
                "provider_id": provider_id,
                "appointment_type": appointment_type,
                "appointment_datetime": appointment_datetime.isoformat(),
            }

            # Broadcast real-time update
            asyncio.create_task(
                self.broadcast_appointment_update(
                    {
                        "event": "appointment_created",
                        "appointment_id": appointment_id,
                        "status": status.value,
                        "provider_id": provider_id,
                        "appointment_datetime": appointment_datetime.isoformat(),
                    }
                )
            )

            # Track metrics
            self.system_monitoring.track_ai_appointment(
                status=status.value, confidence=ai_confidence
            )

            logger.info(
                f"Tracked AI appointment {appointment_id} with status {status.value}"
            )

        except Exception as e:
            logger.error(f"Failed to track AI appointment: {str(e)}")

    def update_appointment_status(
        self, appointment_id: str, new_status: AppointmentStatus
    ):
        """
        Update the status of an AI-scheduled appointment.

        Args:
            appointment_id: EMR appointment ID
            new_status: New appointment status
        """
        try:
            if appointment_id in self.ai_appointments:
                self.ai_appointments[appointment_id]["status"] = new_status.value

                # Broadcast real-time update
                asyncio.create_task(
                    self.broadcast_appointment_update(
                        {
                            "event": "appointment_updated",
                            "appointment_id": appointment_id,
                            "status": new_status.value,
                        }
                    )
                )

                logger.info(
                    f"Updated appointment {appointment_id} status to {new_status.value}"
                )

        except Exception as e:
            logger.error(f"Failed to update appointment status: {str(e)}")

    async def export_appointments(
        self,
        format: str,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        provider_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Export appointment data in specified format.

        Args:
            format: Export format (csv or pdf)
            date_from: Start date for export
            date_to: End date for export
            provider_id: Filter by provider

        Returns:
            Export data or file path
        """
        try:
            # Log export for HIPAA compliance
            self.audit_service.log_data_export(
                user_id="dashboard_user", export_type=f"ai_appointments_{format}"
            )

            # Get filtered appointments
            appointments_data = await self.get_ai_scheduled_appointments(
                date_from=date_from, date_to=date_to, provider_id=provider_id
            )

            appointments = appointments_data.get("appointments", [])

            if format == "csv":
                # Generate CSV content
                csv_content = self._generate_csv(appointments)
                return {
                    "format": "csv",
                    "content": csv_content,
                    "filename": f"ai_appointments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "status": "success",
                }

            elif format == "pdf":
                # Generate PDF report asynchronously
                pdf_content = await self._generate_pdf_report(appointments)
                return {
                    "format": "pdf",
                    "content": pdf_content,
                    "filename": f"ai_appointments_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    "status": "success",
                }

            else:
                return {
                    "error": f"Unsupported export format: {format}",
                    "status": "error",
                }

        except Exception as e:
            logger.error(f"Failed to export appointments: {str(e)}")
            return {"error": "Failed to export appointments", "status": "error"}

    def _generate_csv(self, appointments: List[Dict]) -> str:
        """Generate CSV content from appointments."""
        import csv
        import io

        output = io.StringIO()

        if appointments:
            fieldnames = [
                "appointment_id",
                "patient_name",
                "provider_name",
                "appointment_datetime",
                "appointment_type",
                "status",
                "booking_source",
                "ai_confidence",
                "booking_timestamp",
            ]

            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()

            for appointment in appointments:
                row = {
                    "appointment_id": appointment.get("id", ""),
                    "patient_name": appointment.get("patient_name", ""),
                    "provider_name": appointment.get("provider_name", ""),
                    "appointment_datetime": appointment.get("appointment_datetime", ""),
                    "appointment_type": appointment.get("appointment_type", ""),
                    "status": appointment.get("status", ""),
                    "booking_source": appointment.get("booking_source", ""),
                    "ai_confidence": appointment.get("ai_confidence", ""),
                    "booking_timestamp": appointment.get("booking_timestamp", ""),
                }
                writer.writerow(row)

        return output.getvalue()

    async def _generate_pdf_report(self, appointments: List[Dict]) -> bytes:
        """Generate PDF report from appointments asynchronously."""
        # For MVP, return a simple text-based report
        # In production, would use a proper PDF library
        # Run in executor to avoid blocking event loop
        import asyncio

        report_lines = [
            "AI-Scheduled Appointments Report",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Appointments: {len(appointments)}",
            "",
            "Appointment Summary:",
            "-" * 30,
        ]

        # Count by status
        status_counts = defaultdict(int)
        provider_counts = defaultdict(int)

        for appointment in appointments:
            status_counts[appointment.get("status", "unknown")] += 1
            provider_counts[appointment.get("provider_name", "unknown")] += 1

        report_lines.append("")
        report_lines.append("By Status:")
        for status, count in status_counts.items():
            report_lines.append(f"  {status}: {count}")

        report_lines.append("")
        report_lines.append("By Provider:")
        for provider, count in provider_counts.items():
            report_lines.append(f"  {provider}: {count}")

        report_lines.append("")
        report_lines.append("Recent Appointments:")
        report_lines.append("-" * 30)

        for appointment in appointments[:10]:
            report_lines.append(
                f"{appointment.get('appointment_datetime', 'N/A')} - "
                f"{appointment.get('patient_name', 'N/A')} - "
                f"{appointment.get('provider_name', 'N/A')} - "
                f"{appointment.get('status', 'N/A')}"
            )

        # Convert to bytes (would be PDF in production)
        return "\n".join(report_lines).encode("utf-8")

    def add_connection(self, websocket):
        """Add a new WebSocket connection for real-time updates."""
        self.active_connections.append(websocket)
        logger.info(
            f"Added WebSocket connection. Total: {len(self.active_connections)}"
        )

    def remove_connection(self, websocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"Removed WebSocket connection. Total: {len(self.active_connections)}"
            )

    async def broadcast_appointment_update(self, update_data: Dict[str, Any]):
        """
        Broadcast appointment update to all connected clients.

        Args:
            update_data: Update event data to broadcast
        """
        if self.active_connections:
            message = json.dumps(update_data)

            # Send to all connected clients
            disconnected = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send update to client: {str(e)}")
                    disconnected.append(connection)

            # Remove disconnected clients
            for connection in disconnected:
                self.remove_connection(connection)

    def get_appointment_analytics(self) -> Dict[str, Any]:
        """
        Generate appointment analytics for dashboard display.

        Returns:
            Analytics data including totals, success rates, and provider utilization
        """
        try:
            total_bookings = len(self.ai_appointments)

            # Calculate success rate
            status_counts = defaultdict(int)
            provider_bookings = defaultdict(int)
            hourly_distribution = defaultdict(int)

            for appointment in self.ai_appointments.values():
                status_counts[appointment.get("status", "unknown")] += 1
                provider_bookings[appointment.get("provider_id", "unknown")] += 1

                # Parse appointment time for hourly distribution
                try:
                    appt_time = datetime.fromisoformat(
                        appointment.get("appointment_datetime", "")
                    )
                    hourly_distribution[appt_time.hour] += 1
                except:
                    pass

            confirmed_count = status_counts.get(AppointmentStatus.CONFIRMED.value, 0)
            success_rate = (
                (confirmed_count / total_bookings * 100) if total_bookings > 0 else 0
            )

            return {
                "total_bookings": total_bookings,
                "success_rate": round(success_rate, 1),
                "status_breakdown": dict(status_counts),
                "provider_utilization": dict(provider_bookings),
                "hourly_distribution": dict(hourly_distribution),
                "last_updated": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to generate analytics: {str(e)}")
            return {
                "error": "Failed to generate analytics",
                "total_bookings": 0,
                "success_rate": 0,
            }
