# **Core Components**

## **VoiceCallHandler**
- **Responsibility:** Complete voice call processing
- **Dependencies:** OpenAI APIs, EMR service, Audit service
- **Error Handling:** Graceful failure with human handoff

## **EMRIntegrationService**
- **Responsibility:** Direct OpenEMR communication
- **Key Operations:** Patient lookup, appointment creation
- **No Local Storage:** All data remains in EMR

## **SecurityAndAuditService**
- **Responsibility:** HIPAA compliance and security
- **Features:** Audit logging, credential encryption
- **Implementation:** File-based logs with rotation

## **SystemMonitoringService**
- **Responsibility:** Operational monitoring
- **Metrics:** Call counts, success rates, errors
- **Alerting:** Dashboard indicators only for MVP

## **ConfigurationManager**
- **Responsibility:** Practice settings management
- **Storage:** Encrypted JSON configuration file
- **Validation:** Startup configuration verification
