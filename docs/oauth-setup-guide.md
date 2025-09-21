# OpenEMR OAuth 2.0 Client Registration Guide

## Overview

This guide provides step-by-step instructions for practice staff to register an OAuth 2.0 client with their OpenEMR instance for secure voice AI integration.

## Prerequisites

- OpenEMR 7.0+ instance with OAuth 2.0 enabled
- Administrative access to OpenEMR
- Voice AI platform installed and configured

## Step 1: Access OpenEMR OAuth Client Registration

1. Log into your OpenEMR instance as an administrator
2. Navigate to **Administration** → **System** → **API Clients**
3. Click **Register New Client**

## Step 2: Configure OAuth Client Settings

### Required Client Information:

| Field | Value | Description |
|-------|-------|-------------|
| **Client Name** | `Voice AI Platform` | Descriptive name for identification |
| **Client Type** | `Confidential` | Required for server-side applications |
| **Grant Types** | `Authorization Code` | OAuth 2.0 authorization code flow |
| **Redirect URI** | `http://localhost:8000/oauth/callback` | Voice AI callback endpoint |
| **Scopes** | See below | FHIR R4 access permissions |

### Required OAuth Scopes for FHIR R4 Access:

```text
openid                    # OpenID Connect authentication
fhirUser                  # FHIR user context
patient/*.read           # Read patient data
patient/*.write          # Write patient data (for notes)
Patient.read             # Specific patient resource access
Encounter.read           # Patient encounters
DiagnosticReport.read    # Lab results and reports
Medication.read          # Medication information
```

## Step 3: Save Client Credentials

After registration, OpenEMR will provide:

- **Client ID**: Public identifier for your application
- **Client Secret**: Private secret key (treat as password)

**⚠️ Security Note**: Store these credentials securely. The client secret will only be shown once.

## Step 4: Configure OpenEMR OAuth Settings

### Enable Required OAuth Features:

1. Go to **Administration** → **Globals** → **Security**
2. Ensure these settings are enabled:
   - `Enable OAuth2 Authentication`: Yes
   - `OAuth2 PKCE Required`: Yes (recommended for security)
   - `OAuth2 Refresh Tokens`: Yes

### FHIR R4 API Configuration:

1. Navigate to **Administration** → **System** → **API**
2. Ensure FHIR R4 API is enabled
3. Verify base URL: `https://your-openemr-instance/apis/default/fhir`

## Step 5: Test OAuth Configuration

### Manual Test Process:

1. Note your OpenEMR OAuth endpoints:
   - **Authorization**: `https://your-openemr-instance/oauth2/authorize`
   - **Token**: `https://your-openemr-instance/oauth2/token`

2. Test authorization URL (replace `YOUR_CLIENT_ID`):
   ```
   https://your-openemr-instance/oauth2/authorize?
     response_type=code&
     client_id=YOUR_CLIENT_ID&
     redirect_uri=http://localhost:8000/oauth/callback&
     scope=openid%20fhirUser%20patient/*.read&
     state=test123&
     code_challenge=YOUR_PKCE_CHALLENGE&
     code_challenge_method=S256
   ```

## Step 6: Configure Voice AI Platform

1. Open Voice AI configuration interface
2. Navigate to **OAuth Settings** section
3. Enter the following information:

| Field | Value |
|-------|-------|
| **Client ID** | From Step 3 |
| **Client Secret** | From Step 3 |
| **Authorization Endpoint** | `https://your-openemr-instance/oauth2/authorize` |
| **Token Endpoint** | `https://your-openemr-instance/oauth2/token` |
| **FHIR Base URL** | `https://your-openemr-instance/apis/default/fhir` |

4. Click **Test Connection** to verify setup
5. Complete OAuth authorization flow when prompted

## Troubleshooting

### Common Issues:

**Issue**: "Invalid redirect URI"
- **Solution**: Ensure redirect URI exactly matches what was registered
- **Check**: No trailing slashes, correct port number

**Issue**: "Insufficient scope"
- **Solution**: Verify all required scopes are granted to the client
- **Check**: Patient read/write permissions in OpenEMR

**Issue**: "Invalid client credentials"
- **Solution**: Double-check client ID and secret
- **Check**: No extra spaces, correct case sensitivity

**Issue**: "PKCE verification failed"
- **Solution**: Ensure OpenEMR has PKCE enabled
- **Check**: OAuth2 PKCE setting in Globals

### Verification Steps:

1. **Client Registration**: Verify client appears in OpenEMR API Clients list
2. **Scope Assignment**: Confirm all required scopes are granted
3. **FHIR API**: Test FHIR endpoints are accessible
4. **Network**: Ensure no firewall blocking OAuth endpoints

## Security Best Practices

1. **Use HTTPS**: Always use HTTPS for production OpenEMR instances
2. **Secure Storage**: Store client credentials in encrypted configuration
3. **Regular Rotation**: Periodically rotate client secrets
4. **Monitor Access**: Review OAuth access logs regularly
5. **Minimal Scope**: Only request necessary permissions

## Support

For additional help:
- OpenEMR Documentation: https://www.open-emr.org/wiki/
- OpenEMR Forums: https://community.open-emr.org/
- Voice AI Platform: See system documentation
