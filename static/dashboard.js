/**
 * Dashboard JavaScript for Real-Time AI Appointment Monitoring
 *
 * Handles:
 * - Real-time WebSocket connections for appointment updates
 * - AI appointment filtering and display
 * - Export functionality (CSV/PDF)
 * - Analytics display
 */

// Global variables
let websocket = null;
let aiAppointments = [];
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
const reconnectDelay = 3000; // 3 seconds

// Authentication helper
function getAuthHeaders() {
    // In production, use a proper authentication token management system
    // For now, using basic auth with hardcoded credentials
    const username = 'admin';
    const password = 'admin';
    const auth = btoa(`${username}:${password}`);
    return {
        'Authorization': `Basic ${auth}`
    };
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initializeAIDashboard();
    setupEventListeners();
    loadAIAppointments();
    loadAnalytics();
    connectWebSocket();
});

/**
 * Initialize AI Dashboard components
 */
function initializeAIDashboard() {
    // Set default date filters
    const today = new Date();
    const nextMonth = new Date(today.getFullYear(), today.getMonth() + 1, today.getDate());

    document.getElementById('aiDateFrom').value = formatDate(today);
    document.getElementById('aiDateTo').value = formatDate(nextMonth);

    // Initialize tooltips if Bootstrap is available
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

/**
 * Setup event listeners for dashboard controls
 */
function setupEventListeners() {
    // Refresh button
    document.getElementById('refreshAiBtn').addEventListener('click', function() {
        loadAIAppointments();
        loadAnalytics();
    });

    // Filter button
    document.getElementById('aiFilterBtn').addEventListener('click', function() {
        loadAIAppointments();
    });

    // Export buttons
    document.getElementById('exportCsvBtn').addEventListener('click', function() {
        exportAppointments('csv');
    });

    document.getElementById('exportPdfBtn').addEventListener('click', function() {
        exportAppointments('pdf');
    });

    // Filter dropdowns with auto-refresh
    ['aiProviderFilter', 'aiTypeFilter', 'aiStatusFilter'].forEach(id => {
        document.getElementById(id).addEventListener('change', function() {
            loadAIAppointments();
        });
    });
}

/**
 * Connect to WebSocket for real-time updates
 */
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/appointments`;

    try {
        // Note: WebSocket doesn't support custom headers in the constructor
        // Authentication is handled by passing credentials in the URL or using cookies
        // For production, implement proper auth token handling
        websocket = new WebSocket(wsUrl);

        websocket.onopen = function(event) {
            console.log('WebSocket connected');
            reconnectAttempts = 0;
            updateConnectionStatus(true);

            // Send periodic ping to keep connection alive
            setInterval(function() {
                if (websocket.readyState === WebSocket.OPEN) {
                    websocket.send('ping');
                }
            }, 30000); // Every 30 seconds
        };

        websocket.onmessage = function(event) {
            handleWebSocketMessage(event.data);
        };

        websocket.onerror = function(error) {
            console.error('WebSocket error:', error);
            updateConnectionStatus(false);
        };

        websocket.onclose = function(event) {
            console.log('WebSocket disconnected');
            updateConnectionStatus(false);

            // Attempt to reconnect
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                setTimeout(connectWebSocket, reconnectDelay);
            }
        };

    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        updateConnectionStatus(false);
    }
}

/**
 * Handle incoming WebSocket messages
 */
function handleWebSocketMessage(data) {
    try {
        const message = JSON.parse(data);

        if (message.event === 'appointment_created') {
            showRealtimeNotification(`New appointment created for ${message.provider_id}`);
            loadAIAppointments(); // Refresh the list
            loadAnalytics(); // Update statistics
        } else if (message.event === 'appointment_updated') {
            showRealtimeNotification(`Appointment ${message.appointment_id} updated to ${message.status}`);
            updateAppointmentInList(message.appointment_id, message.status);
        } else if (message.event === 'appointment_cancelled') {
            showRealtimeNotification(`Appointment ${message.appointment_id} cancelled`);
            loadAIAppointments();
        }
    } catch (error) {
        if (data === 'pong') {
            // Ignore pong responses
            return;
        }
        console.error('Error handling WebSocket message:', error);
    }
}

/**
 * Update WebSocket connection status indicator
 */
function updateConnectionStatus(connected) {
    const indicator = document.getElementById('realtimeIndicator');
    if (indicator) {
        if (connected) {
            indicator.className = 'badge bg-success ms-2';
            indicator.innerHTML = '<i class="fas fa-circle"></i> Real-time';
        } else {
            indicator.className = 'badge bg-danger ms-2';
            indicator.innerHTML = '<i class="fas fa-circle"></i> Disconnected';
        }
    }
}

/**
 * Show real-time notification
 */
function showRealtimeNotification(message) {
    const notificationArea = document.getElementById('realtimeNotifications');
    const notificationText = document.getElementById('notificationText');

    if (notificationArea && notificationText) {
        notificationText.textContent = message;
        notificationArea.style.display = 'block';

        // Auto-hide after 5 seconds
        setTimeout(function() {
            notificationArea.style.display = 'none';
        }, 5000);
    }
}

/**
 * Load AI appointments from API
 */
async function loadAIAppointments() {
    const tbody = document.getElementById('aiAppointmentsBody');
    tbody.innerHTML = '<tr><td colspan="8" class="text-center"><div class="spinner-border spinner-border-sm" role="status"></div> Loading...</td></tr>';

    // Build query parameters
    const params = new URLSearchParams();

    const dateFrom = document.getElementById('aiDateFrom').value;
    const dateTo = document.getElementById('aiDateTo').value;
    const provider = document.getElementById('aiProviderFilter').value;
    const type = document.getElementById('aiTypeFilter').value;
    const status = document.getElementById('aiStatusFilter').value;

    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (provider) params.append('provider_id', provider);
    if (type) params.append('appointment_type', type);
    if (status) params.append('status', status);

    try {
        const response = await fetch(`/api/v1/appointments/ai-scheduled?${params.toString()}`, {
            headers: getAuthHeaders()
        });
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            aiAppointments = data.appointments;
            displayAIAppointments(aiAppointments);
            updateStatistics(aiAppointments);
        } else {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger">Failed to load appointments</td></tr>';
        }
    } catch (error) {
        console.error('Error loading AI appointments:', error);
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger">Error loading appointments</td></tr>';
    }
}

/**
 * Display AI appointments in table
 */
function displayAIAppointments(appointments) {
    const tbody = document.getElementById('aiAppointmentsBody');

    if (appointments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No AI-scheduled appointments found</td></tr>';
        return;
    }

    tbody.innerHTML = appointments.map(appointment => {
        const statusBadge = getStatusBadge(appointment.status);
        const confidenceBadge = getConfidenceBadge(appointment.ai_confidence);
        const appointmentDate = new Date(appointment.appointment_datetime);

        return `
            <tr data-appointment-id="${appointment.id}">
                <td>${statusBadge}</td>
                <td>${formatDateTime(appointmentDate)}</td>
                <td>${appointment.patient_name || 'N/A'}</td>
                <td>${appointment.provider_name || appointment.provider_id}</td>
                <td>${appointment.appointment_type || 'General'}</td>
                <td><span class="badge bg-info">Voice AI</span></td>
                <td>${confidenceBadge}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" onclick="viewAppointmentDetails('${appointment.id}')">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

/**
 * Update statistics display
 */
function updateStatistics(appointments) {
    const total = appointments.length;
    const confirmed = appointments.filter(a => a.status === 'confirmed').length;
    const pending = appointments.filter(a => a.status === 'pending').length;
    const failed = appointments.filter(a => a.status === 'failed').length;

    document.getElementById('totalBookings').textContent = total;
    document.getElementById('successRate').textContent = total > 0 ?
        Math.round((confirmed / total) * 100) + '%' : '0%';
    document.getElementById('pendingCount').textContent = pending;
    document.getElementById('failedCount').textContent = failed;
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
    switch(status) {
        case 'confirmed':
            return '<span class="badge bg-success">Confirmed</span>';
        case 'pending':
            return '<span class="badge bg-warning">Pending</span>';
        case 'failed':
            return '<span class="badge bg-danger">Failed</span>';
        default:
            return '<span class="badge bg-secondary">Unknown</span>';
    }
}

/**
 * Get confidence badge HTML
 */
function getConfidenceBadge(confidence) {
    const percentage = Math.round(confidence * 100);
    let colorClass = 'bg-danger';

    if (percentage >= 80) {
        colorClass = 'bg-success';
    } else if (percentage >= 60) {
        colorClass = 'bg-warning';
    }

    return `<span class="badge ${colorClass}">${percentage}%</span>`;
}

/**
 * Update appointment in list
 */
function updateAppointmentInList(appointmentId, newStatus) {
    const row = document.querySelector(`tr[data-appointment-id="${appointmentId}"]`);
    if (row) {
        const statusCell = row.cells[0];
        statusCell.innerHTML = getStatusBadge(newStatus);

        // Highlight the row briefly
        row.classList.add('table-info');
        setTimeout(() => {
            row.classList.remove('table-info');
        }, 2000);
    }
}

/**
 * Export appointments
 */
async function exportAppointments(format) {
    const params = new URLSearchParams();

    const dateFrom = document.getElementById('aiDateFrom').value;
    const dateTo = document.getElementById('aiDateTo').value;
    const provider = document.getElementById('aiProviderFilter').value;

    params.append('format', format);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (provider) params.append('provider_id', provider);

    try {
        const response = await fetch(`/api/v1/appointments/export?${params.toString()}`, {
            headers: getAuthHeaders()
        });

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `ai_appointments.${format}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            showRealtimeNotification(`Exported appointments as ${format.toUpperCase()}`);
        } else {
            alert('Failed to export appointments');
        }
    } catch (error) {
        console.error('Error exporting appointments:', error);
        alert('Error exporting appointments');
    }
}

/**
 * Load analytics data
 */
async function loadAnalytics() {
    try {
        const response = await fetch('/api/v1/appointments/analytics', {
            headers: getAuthHeaders()
        });
        const data = await response.json();

        if (response.ok) {
            // Update analytics display if needed
            console.log('Analytics loaded:', data);
        }
    } catch (error) {
        console.error('Error loading analytics:', error);
    }
}

/**
 * View appointment details
 */
function viewAppointmentDetails(appointmentId) {
    const appointment = aiAppointments.find(a => a.id === appointmentId);
    if (appointment) {
        // In production, this would open a modal or detail view
        console.log('View details for appointment:', appointment);
        alert(`Appointment Details:\n\nID: ${appointment.id}\nPatient: ${appointment.patient_name}\nProvider: ${appointment.provider_name}\nTime: ${appointment.appointment_datetime}\nStatus: ${appointment.status}`);
    }
}

/**
 * Format date for input fields
 */
function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Format date and time for display
 */
function formatDateTime(date) {
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return date.toLocaleDateString('en-US', options);
}
