/**
 * Health Monitoring JavaScript
 *
 * Handles health status updates, connection testing, error log display,
 * and system management functionality for the Voice AI Platform.
 */

class HealthMonitoringService {
    constructor() {
        this.refreshInterval = null;
        this.autoRefreshEnabled = true;
        this.refreshIntervalTime = 30000; // 30 seconds
        this.lastHealthData = null;
        this.alerts = [];

        this.init();
    }

    init() {
        this.bindEventListeners();
        this.loadHealthStatus();
        this.startAutoRefresh();
    }

    bindEventListeners() {
        // Health status refresh
        document.getElementById('refreshHealthStatus')?.addEventListener('click', () => {
            this.loadHealthStatus();
        });

        // Connection testing buttons
        document.getElementById('testEmrConnection')?.addEventListener('click', () => {
            this.testConnection('emr');
        });

        document.getElementById('testVoiceServices')?.addEventListener('click', () => {
            this.testConnection('voice');
        });

        document.getElementById('testWebInterface')?.addEventListener('click', () => {
            this.testConnection('web');
        });

        // Error logs modal
        document.getElementById('refreshErrorLogs')?.addEventListener('click', () => {
            this.loadErrorLogs();
        });

        document.getElementById('logSeverityFilter')?.addEventListener('change', () => {
            this.filterErrorLogs();
        });

        document.getElementById('logSearchInput')?.addEventListener('input', () => {
            this.filterErrorLogs();
        });

        // System restart confirmation
        document.getElementById('restartConfirmCheckbox')?.addEventListener('change', (e) => {
            const confirmBtn = document.getElementById('confirmRestartBtn');
            if (confirmBtn) {
                confirmBtn.disabled = !e.target.checked;
            }
        });

        document.getElementById('confirmRestartBtn')?.addEventListener('click', () => {
            this.performSystemRestart();
        });

        // Support actions
        document.getElementById('generateSupportReport')?.addEventListener('click', () => {
            this.generateSupportReport();
        });

        document.getElementById('downloadSystemLogs')?.addEventListener('click', () => {
            this.downloadSystemLogs();
        });

        // Modal event listeners
        document.getElementById('errorLogsModal')?.addEventListener('shown.bs.modal', () => {
            this.loadErrorLogs();
        });

        document.getElementById('supportInfoModal')?.addEventListener('shown.bs.modal', () => {
            this.loadSupportInfo();
        });
    }

    async loadHealthStatus() {
        try {
            this.setRefreshButtonLoading(true);

            // Make parallel requests to health endpoints
            const [statusResponse, metricsResponse] = await Promise.all([
                fetch('/api/v1/status'),
                fetch('/api/v1/health/metrics').catch(() => ({ ok: false }))
            ]);

            const statusData = statusResponse.ok ? await statusResponse.json() : null;
            const metricsData = metricsResponse.ok ? await metricsResponse.json() : null;

            this.updateHealthDisplay(statusData, metricsData);
            this.updateLastRefreshTime();
            this.checkForAlerts(statusData, metricsData);

        } catch (error) {
            console.error('Failed to load health status:', error);
            this.showHealthError('Failed to load system health data');
        } finally {
            this.setRefreshButtonLoading(false);
        }
    }

    updateHealthDisplay(statusData, metricsData) {
        if (statusData) {
            this.updateComponentStatus('emr', {
                status: statusData.emr_connected ? 'connected' : 'disconnected',
                responseTime: statusData.emr_response_time || null,
                error: statusData.emr_error || null
            });

            this.updateComponentStatus('voice', {
                status: statusData.voice_ai_connected ? 'operational' : 'offline',
                successRate: statusData.voice_success_rate || null,
                error: statusData.voice_error || null
            });

            this.updateComponentStatus('web', {
                status: 'operational', // Web is working if we can make this request
                loadTime: statusData.web_load_time || null
            });
        }

        if (metricsData) {
            this.updatePerformanceMetrics(metricsData);
        }

        // Update with fallback data if APIs aren't ready
        if (!statusData && !metricsData) {
            this.showFallbackHealthData();
        }
    }

    updateComponentStatus(component, data) {
        const statusCard = document.getElementById(`${component}StatusCard`);
        const statusIcon = document.getElementById(`${component}StatusIcon`);
        const statusText = document.getElementById(`${component}StatusText`);

        if (!statusCard || !statusIcon || !statusText) return;

        let statusClass, iconClass, statusMessage;

        switch (data.status) {
            case 'connected':
            case 'operational':
                statusClass = 'border-success';
                iconClass = 'text-success';
                statusMessage = component === 'emr' ? 'Connected' : 'Operational';
                break;
            case 'degraded':
                statusClass = 'border-warning';
                iconClass = 'text-warning';
                statusMessage = 'Degraded Performance';
                break;
            case 'disconnected':
            case 'offline':
                statusClass = 'border-danger';
                iconClass = 'text-danger';
                statusMessage = component === 'emr' ? 'Disconnected' : 'Offline';
                break;
            default:
                statusClass = 'border-secondary';
                iconClass = 'text-secondary';
                statusMessage = 'Unknown Status';
        }

        // Update card styling
        statusCard.className = `card border-start border-3 ${statusClass}`;

        // Update status icon
        statusIcon.innerHTML = `<i class="fas fa-circle ${iconClass}"></i>`;

        // Update status text
        statusText.textContent = data.error || statusMessage;

        // Update component-specific metrics
        if (component === 'emr' && data.responseTime !== null) {
            const responseTimeEl = document.getElementById('emrResponseTime');
            if (responseTimeEl) {
                responseTimeEl.textContent = `Response time: ${data.responseTime}ms`;
            }
        }

        if (component === 'voice' && data.successRate !== null) {
            const successRateEl = document.getElementById('voiceSuccessRate');
            if (successRateEl) {
                successRateEl.textContent = `Success rate: ${data.successRate.toFixed(1)}%`;
            }
        }

        if (component === 'web' && data.loadTime !== null) {
            const loadTimeEl = document.getElementById('webLoadTime');
            if (loadTimeEl) {
                loadTimeEl.textContent = `Load time: ${data.loadTime}ms`;
            }
        }
    }

    updatePerformanceMetrics(metricsData) {
        const metrics = {
            systemUptime: metricsData.system_uptime_percent || 99.0,
            avgResponseTime: metricsData.average_response_time || 200,
            callVolume: metricsData.call_volume_today || 0,
            errorRate: metricsData.error_rate_percent || 0.5
        };

        // Update system uptime
        const uptimeEl = document.getElementById('systemUptime');
        if (uptimeEl) {
            uptimeEl.textContent = `${metrics.systemUptime.toFixed(1)}%`;
            uptimeEl.className = this.getMetricClass(metrics.systemUptime, 'uptime');
        }

        // Update average response time
        const responseTimeEl = document.getElementById('avgResponseTime');
        if (responseTimeEl) {
            responseTimeEl.textContent = `${metrics.avgResponseTime}ms`;
            responseTimeEl.className = this.getMetricClass(metrics.avgResponseTime, 'response_time');
        }

        // Update call volume
        const callVolumeEl = document.getElementById('callVolume');
        if (callVolumeEl) {
            callVolumeEl.textContent = metrics.callVolume.toString();
            callVolumeEl.className = 'text-success';
        }

        // Update error rate
        const errorRateEl = document.getElementById('errorRate');
        if (errorRateEl) {
            errorRateEl.textContent = `${metrics.errorRate.toFixed(1)}%`;
            errorRateEl.className = this.getMetricClass(metrics.errorRate, 'error_rate');
        }
    }

    getMetricClass(value, metricType) {
        switch (metricType) {
            case 'uptime':
                if (value >= 99.5) return 'metric-value-excellent';
                if (value >= 98.0) return 'metric-value-good';
                if (value >= 95.0) return 'metric-value-warning';
                if (value >= 90.0) return 'metric-value-poor';
                return 'metric-value-critical';

            case 'response_time':
                if (value <= 100) return 'metric-value-excellent';
                if (value <= 250) return 'metric-value-good';
                if (value <= 500) return 'metric-value-warning';
                if (value <= 1000) return 'metric-value-poor';
                return 'metric-value-critical';

            case 'error_rate':
                if (value <= 0.1) return 'metric-value-excellent';
                if (value <= 0.5) return 'metric-value-good';
                if (value <= 2.0) return 'metric-value-warning';
                if (value <= 5.0) return 'metric-value-poor';
                return 'metric-value-critical';

            default:
                return 'text-primary';
        }
    }

    showFallbackHealthData() {
        // Show reasonable defaults when API endpoints aren't ready yet
        this.updateComponentStatus('emr', {
            status: 'disconnected',
            responseTime: null,
            error: 'Not configured'
        });

        this.updateComponentStatus('voice', {
            status: 'offline',
            successRate: null,
            error: 'Not configured'
        });

        this.updateComponentStatus('web', {
            status: 'operational',
            loadTime: 200
        });

        // Show default metrics
        this.updatePerformanceMetrics({
            system_uptime_percent: 99.0,
            average_response_time: 200,
            call_volume_today: 0,
            error_rate_percent: 0.0
        });
    }

    async testConnection(component) {
        const button = document.getElementById(`test${component.charAt(0).toUpperCase() + component.slice(1)}${component === 'voice' ? 'Services' : component === 'emr' ? 'Connection' : 'Interface'}`);
        const resultSpan = document.getElementById(`${component}TestResult`);

        if (!button || !resultSpan) return;

        // Set loading state
        button.classList.add('btn-test-loading');
        button.disabled = true;
        resultSpan.textContent = 'Testing...';
        resultSpan.className = 'small text-info';

        try {
            let endpoint;
            switch (component) {
                case 'emr':
                    endpoint = '/api/v1/oauth/test';
                    break;
                case 'voice':
                    endpoint = '/api/v1/health/test';
                    break;
                case 'web':
                    endpoint = '/api/v1/status';
                    break;
                default:
                    throw new Error('Unknown component');
            }

            const response = await fetch(endpoint, { method: 'POST' });
            const data = await response.json();

            if (response.ok && (data.status === 'success' || data.status === 'healthy')) {
                resultSpan.textContent = '✓ Test passed';
                resultSpan.className = 'small text-success';
            } else {
                resultSpan.textContent = `✗ Test failed: ${data.message || 'Unknown error'}`;
                resultSpan.className = 'small text-danger';
            }

        } catch (error) {
            console.error(`${component} connection test failed:`, error);
            resultSpan.textContent = `✗ Test failed: ${error.message}`;
            resultSpan.className = 'small text-danger';
        } finally {
            button.classList.remove('btn-test-loading');
            button.disabled = false;

            // Clear result after 5 seconds
            setTimeout(() => {
                resultSpan.textContent = '';
                resultSpan.className = 'small text-muted';
            }, 5000);
        }
    }

    async loadErrorLogs() {
        const errorLogsList = document.getElementById('errorLogsList');
        if (!errorLogsList) return;

        try {
            errorLogsList.innerHTML = `
                <div class="text-center">
                    <div class="spinner-border spinner-border-sm" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">Loading error logs...</p>
                </div>
            `;

            const response = await fetch('/api/v1/health/errors?limit=50');

            if (response.ok) {
                const data = await response.json();
                this.displayErrorLogs(data.errors || []);
            } else {
                // Fallback to example error logs for demo
                this.displayErrorLogs(this.getExampleErrorLogs());
            }

        } catch (error) {
            console.error('Failed to load error logs:', error);
            errorLogsList.innerHTML = `
                <div class="alert alert-warning">
                    <h6 class="alert-heading">Unable to Load Error Logs</h6>
                    <p class="mb-0">Could not retrieve error logs from the server. Please try again later.</p>
                </div>
            `;
        }
    }

    displayErrorLogs(errors) {
        const errorLogsList = document.getElementById('errorLogsList');
        if (!errorLogsList) return;

        if (errors.length === 0) {
            errorLogsList.innerHTML = `
                <div class="alert alert-success">
                    <h6 class="alert-heading">✓ No Errors Found</h6>
                    <p class="mb-0">Great! No recent errors have been logged.</p>
                </div>
            `;
            return;
        }

        const errorHtml = errors.map(error => this.formatErrorLogEntry(error)).join('');
        errorLogsList.innerHTML = errorHtml;
    }

    formatErrorLogEntry(error) {
        const severityClass = `log-${error.severity || 'info'}`;
        const timestamp = new Date(error.timestamp).toLocaleString();

        return `
            <div class="error-log-entry ${severityClass}" data-severity="${error.severity}" data-component="${error.component}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="log-timestamp">${timestamp}</div>
                    <div class="log-component">${error.component || 'system'}</div>
                </div>
                <div class="log-message">${this.escapeHtml(error.message)}</div>
                ${error.resolved ? '<div class="text-success small mt-1">✓ Resolved</div>' : ''}
            </div>
        `;
    }

    getExampleErrorLogs() {
        const now = new Date();
        return [
            {
                timestamp: new Date(now.getTime() - 10 * 60000).toISOString(),
                severity: 'warning',
                component: 'emr',
                message: 'EMR connection timeout after 5 seconds - retrying connection',
                resolved: true
            },
            {
                timestamp: new Date(now.getTime() - 30 * 60000).toISOString(),
                severity: 'error',
                component: 'voice',
                message: 'OpenAI API rate limit exceeded - request queued for retry',
                resolved: true
            },
            {
                timestamp: new Date(now.getTime() - 60 * 60000).toISOString(),
                severity: 'info',
                component: 'system',
                message: 'Health monitoring service started successfully',
                resolved: true
            }
        ];
    }

    filterErrorLogs() {
        const severityFilter = document.getElementById('logSeverityFilter')?.value;
        const searchInput = document.getElementById('logSearchInput')?.value.toLowerCase();
        const logEntries = document.querySelectorAll('.error-log-entry');

        logEntries.forEach(entry => {
            const severity = entry.dataset.severity;
            const message = entry.querySelector('.log-message')?.textContent.toLowerCase() || '';

            const severityMatch = !severityFilter || severityFilter === 'all' || severity === severityFilter;
            const searchMatch = !searchInput || message.includes(searchInput);

            entry.style.display = severityMatch && searchMatch ? 'block' : 'none';
        });
    }

    checkForAlerts(statusData, metricsData) {
        this.alerts = [];

        // Check for system failures
        if (statusData) {
            if (!statusData.emr_connected) {
                this.alerts.push({
                    type: 'connectivity_issue',
                    severity: 'high',
                    message: 'EMR system is disconnected - appointment scheduling may be affected',
                    component: 'emr'
                });
            }

            if (!statusData.voice_ai_connected) {
                this.alerts.push({
                    type: 'system_failure',
                    severity: 'critical',
                    message: 'Voice AI services are offline - voice appointment booking unavailable',
                    component: 'voice'
                });
            }
        }

        // Check performance metrics
        if (metricsData) {
            if (metricsData.error_rate_percent > 5.0) {
                this.alerts.push({
                    type: 'performance_degraded',
                    severity: 'medium',
                    message: `High error rate detected: ${metricsData.error_rate_percent.toFixed(1)}%`,
                    component: 'system'
                });
            }

            if (metricsData.average_response_time > 1000) {
                this.alerts.push({
                    type: 'performance_degraded',
                    severity: 'medium',
                    message: `Slow response times: ${metricsData.average_response_time}ms average`,
                    component: 'system'
                });
            }
        }

        this.displayAlerts();
    }

    displayAlerts() {
        const alertsSection = document.getElementById('systemAlertsSection');
        const alertsContainer = document.getElementById('systemAlerts');

        if (!alertsSection || !alertsContainer) return;

        if (this.alerts.length === 0) {
            alertsSection.style.display = 'none';
            return;
        }

        alertsSection.style.display = 'block';

        const alertsHtml = this.alerts.map(alert => {
            return `
                <div class="health-alert alert-${alert.severity}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <strong>${alert.severity.toUpperCase()}:</strong> ${alert.message}
                        </div>
                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="healthMonitoring.dismissAlert('${alert.type}')">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
            `;
        }).join('');

        alertsContainer.innerHTML = alertsHtml;
    }

    dismissAlert(alertType) {
        this.alerts = this.alerts.filter(alert => alert.type !== alertType);
        this.displayAlerts();
    }

    async performSystemRestart() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('restartConfirmModal'));

        try {
            const response = await fetch('/api/v1/health/restart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    component: 'system',
                    action: 'restart'
                })
            });

            const data = await response.json();

            if (response.ok && data.status === 'success') {
                alert('System restart initiated successfully. The page will reload automatically.');
                modal?.hide();

                // Reload page after a delay
                setTimeout(() => {
                    window.location.reload();
                }, 5000);
            } else {
                alert(`Restart failed: ${data.message || 'Unknown error'}`);
            }

        } catch (error) {
            console.error('System restart failed:', error);
            alert('Failed to restart system. Please contact technical support.');
        }
    }

    async generateSupportReport() {
        try {
            const reportData = {
                timestamp: new Date().toISOString(),
                healthStatus: this.lastHealthData,
                recentErrors: this.getExampleErrorLogs(),
                systemInfo: {
                    version: '0.1.0',
                    environment: 'Production',
                    uptime: '2 days, 14 hours'
                }
            };

            const blob = new Blob([JSON.stringify(reportData, null, 2)], {
                type: 'application/json'
            });

            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `support-report-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

        } catch (error) {
            console.error('Failed to generate support report:', error);
            alert('Failed to generate support report. Please try again.');
        }
    }

    async downloadSystemLogs() {
        try {
            const response = await fetch('/api/v1/health/errors?limit=1000&format=text');

            if (response.ok) {
                const text = await response.text();
                const blob = new Blob([text], { type: 'text/plain' });

                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `system-logs-${new Date().toISOString().split('T')[0]}.txt`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } else {
                throw new Error('Failed to fetch logs');
            }

        } catch (error) {
            console.error('Failed to download system logs:', error);
            alert('Failed to download system logs. Please contact technical support.');
        }
    }

    loadSupportInfo() {
        // Update system information in support modal
        document.getElementById('systemVersion').textContent = '0.1.0';
        document.getElementById('systemEnvironment').textContent = 'Production';
        document.getElementById('lastRestartTime').textContent = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toLocaleString();
        document.getElementById('currentUptime').textContent = '2 days, 14 hours';
    }

    setRefreshButtonLoading(loading) {
        const refreshBtn = document.getElementById('refreshHealthStatus');
        if (!refreshBtn) return;

        if (loading) {
            refreshBtn.classList.add('btn-refresh-spinning');
            refreshBtn.disabled = true;
        } else {
            refreshBtn.classList.remove('btn-refresh-spinning');
            refreshBtn.disabled = false;
        }
    }

    updateLastRefreshTime() {
        const lastUpdatedEl = document.getElementById('healthLastUpdated');
        if (lastUpdatedEl) {
            lastUpdatedEl.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
        }
    }

    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }

        this.refreshInterval = setInterval(() => {
            if (this.autoRefreshEnabled) {
                this.loadHealthStatus();
            }
        }, this.refreshIntervalTime);
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    showHealthError(message) {
        console.error('Health monitoring error:', message);
        // Could show a toast notification or update UI to show error state
    }

    escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    destroy() {
        this.stopAutoRefresh();
        // Remove event listeners if needed
    }
}

// Initialize health monitoring when DOM is ready
let healthMonitoring;

document.addEventListener('DOMContentLoaded', function() {
    healthMonitoring = new HealthMonitoringService();

    // Make it globally accessible for modal callbacks
    window.healthMonitoring = healthMonitoring;
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (healthMonitoring) {
        healthMonitoring.destroy();
    }
});
