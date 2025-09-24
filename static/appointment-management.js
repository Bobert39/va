/**
 * Appointment Management JavaScript Module
 * Provides client-side functionality for appointment editing, creation, and management
 * Complements the main dashboard.js with specific appointment management features
 */

class AppointmentManager {
    constructor() {
        this.apiBase = '/api/v1/appointments';
        this.currentEditId = null;
        this.initializeEventListeners();
    }

    /**
     * Initialize event listeners for appointment management actions
     */
    initializeEventListeners() {
        // Edit appointment modal handlers
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('edit-appointment-btn')) {
                const appointmentId = e.target.getAttribute('data-appointment-id');
                this.openEditModal(appointmentId);
            }

            if (e.target.classList.contains('cancel-appointment-btn')) {
                const appointmentId = e.target.getAttribute('data-appointment-id');
                this.openCancelModal(appointmentId);
            }

            if (e.target.classList.contains('override-conflicts-btn')) {
                const appointmentId = e.target.getAttribute('data-appointment-id');
                this.openOverrideModal(appointmentId);
            }
        });

        // Form submission handlers
        const editForm = document.getElementById('edit-appointment-form');
        if (editForm) {
            editForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.submitAppointmentEdit();
            });
        }

        const manualForm = document.getElementById('manual-appointment-form');
        if (manualForm) {
            manualForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.submitManualAppointment();
            });
        }
    }

    /**
     * Open edit appointment modal
     */
    async openEditModal(appointmentId) {
        this.currentEditId = appointmentId;

        // Get appointment details and populate form
        // For now, we'll use placeholder data since the appointments are from EMR
        const modal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));

        // Set form values (in real implementation, fetch from EMR)
        document.getElementById('edit-appointment-time').value = '';
        document.getElementById('edit-provider-id').value = '';
        document.getElementById('edit-appointment-notes').value = '';

        modal.show();
    }

    /**
     * Open cancel appointment modal
     */
    openCancelModal(appointmentId) {
        this.currentEditId = appointmentId;

        const modal = new bootstrap.Modal(document.getElementById('cancelAppointmentModal'));
        modal.show();
    }

    /**
     * Open conflict override modal
     */
    openOverrideModal(appointmentId) {
        this.currentEditId = appointmentId;

        const modal = new bootstrap.Modal(document.getElementById('overrideConflictsModal'));
        modal.show();
    }

    /**
     * Submit appointment edit
     */
    async submitAppointmentEdit() {
        const time = document.getElementById('edit-appointment-time').value;
        const providerId = document.getElementById('edit-provider-id').value;
        const notes = document.getElementById('edit-appointment-notes').value;

        const requestData = {
            staff_member_id: 'current-staff-member', // In real implementation, get from session
            time: time,
            provider_id: providerId,
            notes: notes
        };

        try {
            const response = await fetch(`${this.apiBase}/${this.currentEditId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showNotification('Appointment updated successfully', 'success');
                bootstrap.Modal.getInstance(document.getElementById('editAppointmentModal')).hide();
                this.refreshAppointmentList();
            } else {
                this.showNotification(`Error: ${result.detail}`, 'error');
            }
        } catch (error) {
            this.showNotification(`Error updating appointment: ${error.message}`, 'error');
        }
    }

    /**
     * Submit manual appointment creation
     */
    async submitManualAppointment() {
        const patientId = document.getElementById('manual-patient-id').value;
        const time = document.getElementById('manual-appointment-time').value;
        const providerId = document.getElementById('manual-provider-id').value;
        const notes = document.getElementById('manual-appointment-notes').value;

        const requestData = {
            patient_id: patientId,
            time: time,
            provider_id: providerId,
            notes: notes,
            staff_member_id: 'current-staff-member' // In real implementation, get from session
        };

        try {
            const response = await fetch(`${this.apiBase}/manual`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showNotification('Manual appointment created successfully', 'success');
                document.getElementById('manual-appointment-form').reset();
                this.refreshAppointmentList();
            } else {
                this.showNotification(`Error: ${result.detail}`, 'error');
            }
        } catch (error) {
            this.showNotification(`Error creating appointment: ${error.message}`, 'error');
        }
    }

    /**
     * Cancel appointment
     */
    async cancelAppointment() {
        const reason = document.getElementById('cancel-reason').value;
        const notes = document.getElementById('cancel-notes').value;

        const requestData = {
            reason: reason,
            notes: notes,
            staff_member_id: 'current-staff-member' // In real implementation, get from session
        };

        try {
            const response = await fetch(`${this.apiBase}/${this.currentEditId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showNotification('Appointment cancelled successfully', 'success');
                bootstrap.Modal.getInstance(document.getElementById('cancelAppointmentModal')).hide();
                this.refreshAppointmentList();
            } else {
                this.showNotification(`Error: ${result.detail}`, 'error');
            }
        } catch (error) {
            this.showNotification(`Error cancelling appointment: ${error.message}`, 'error');
        }
    }

    /**
     * Override appointment conflicts
     */
    async overrideConflicts() {
        const justification = document.getElementById('override-justification').value;
        const overrideType = document.getElementById('override-type').value;

        const requestData = {
            justification: justification,
            override_type: overrideType,
            staff_member_id: 'current-staff-member' // In real implementation, get from session
        };

        try {
            const response = await fetch(`${this.apiBase}/${this.currentEditId}/override`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showNotification('Conflict override applied successfully', 'success');
                bootstrap.Modal.getInstance(document.getElementById('overrideConflictsModal')).hide();
                this.refreshAppointmentList();
            } else {
                this.showNotification(`Error: ${result.detail}`, 'error');
            }
        } catch (error) {
            this.showNotification(`Error applying override: ${error.message}`, 'error');
        }
    }

    /**
     * Bulk operations handler
     */
    async performBulkOperation(operation, appointmentIds, newParams = {}) {
        const requestData = {
            operation: operation,
            appointment_ids: appointmentIds,
            new_params: newParams,
            staff_member_id: 'current-staff-member' // In real implementation, get from session
        };

        try {
            const response = await fetch(`${this.apiBase}/bulk`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const result = await response.json();

            if (response.ok) {
                this.showNotification(`Bulk ${operation} completed successfully`, 'success');
                this.refreshAppointmentList();
            } else {
                this.showNotification(`Error: ${result.detail}`, 'error');
            }
        } catch (error) {
            this.showNotification(`Error performing bulk operation: ${error.message}`, 'error');
        }
    }

    /**
     * Show notification to user
     */
    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show appointment-notification`;
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        // Add to page
        const container = document.getElementById('appointment-notifications') || document.body;
        container.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

    /**
     * Refresh appointment list (integration with main dashboard)
     */
    refreshAppointmentList() {
        // Trigger refresh of main appointment display
        if (window.dashboardManager && typeof window.dashboardManager.loadTodayAppointments === 'function') {
            window.dashboardManager.loadTodayAppointments();
        }
    }

    /**
     * Format appointment time for display
     */
    formatAppointmentTime(timeString) {
        const date = new Date(timeString);
        return date.toLocaleString();
    }

    /**
     * Validate appointment time input
     */
    validateAppointmentTime(timeString) {
        const appointmentTime = new Date(timeString);
        const now = new Date();

        if (appointmentTime <= now) {
            return { valid: false, message: 'Appointment time must be in the future' };
        }

        return { valid: true };
    }
}

// Initialize appointment manager when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.appointmentManager = new AppointmentManager();
});

// Export for testing purposes
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AppointmentManager;
}
