# Port Security Guide - Voice AI Platform

## 🔒 Why Non-Standard Ports Matter

Using uncommon ports provides several security benefits:
- **Reduces automated scanning** - Most bots target common ports (80, 443, 8000, 8080)
- **Avoids service conflicts** - Prevents conflicts with other applications
- **Security through obscurity** - Additional layer of protection
- **Professional deployment** - Indicates security-conscious development

## 🎯 Current Configuration

**Primary Application Port**: `9847`
- **Rationale**: Outside common port ranges, not typically scanned
- **Access**: `http://localhost:9847` or `https://yourdomain.com:9847`

**CORS Origins**: Limited to specific hosts and the application port
- `http://localhost:9847`
- `http://127.0.0.1:9847`
- `http://192.168.1.100:9847` (local network access)

## 📋 Port Selection Best Practices

### ✅ Recommended Port Ranges
```
High-numbered ports (less likely to conflict):
- 9000-9999   (Good for development)
- 10000-19999 (Good for internal services)
- 20000-65535 (Good for production)

Current choice: 9847 ✅
```

### ❌ Ports to Avoid
```
Common/Predictable Ports:
- 80, 443     (HTTP/HTTPS - heavily scanned)
- 8000, 8080  (Common development ports)
- 3000, 5000  (Common framework defaults)
- 22, 21, 23  (SSH, FTP, Telnet - high-value targets)
- 25, 53, 110 (Email/DNS - often filtered)
```

### 🔒 Port Security Levels

**Level 1 - Minimal Security (Avoid)**
- Ports: 80, 443, 8000, 8080, 3000, 5000
- Risk: High automated scanning, predictable

**Level 2 - Basic Security**
- Ports: 8001-8999, 9000-9099
- Risk: Medium scanning, somewhat predictable

**Level 3 - Good Security** ⭐ **Current**
- Ports: 9100-9999, 10000-19999
- Risk: Low scanning, unpredictable

**Level 4 - High Security**
- Ports: 20000-65535
- Risk: Minimal scanning, highly unpredictable

## 🛡️ Additional Security Measures

### Firewall Configuration
```bash
# Allow only specific port
sudo ufw allow 9847/tcp
sudo ufw deny 8000,8080,3000,5000/tcp

# For production (with domain)
sudo ufw allow from yourdomain.com to any port 9847
```

### Reverse Proxy (Production)
```nginx
# nginx configuration
server {
    listen 443 ssl;
    server_name yourdomain.com;

    location / {
        proxy_pass http://localhost:9847;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Environment-Specific Ports
```bash
# Development
PORT=9847

# Staging
PORT=9848

# Production
PORT=9849
```

## 🔍 Security Validation

The system automatically validates port security:

### Automated Checks
- ⚠️ Warns about common ports (8000, 8080, 3000, etc.)
- ℹ️ Notes privileged ports (<1024) requiring elevated access
- 📊 Includes port security in overall security score

### Manual Verification
```bash
# Check if port is in use
sudo netstat -tulpn | grep :9847

# Test external access (from another machine)
curl http://your-ip:9847/health

# Verify firewall rules
sudo ufw status numbered
```

## 🌐 Production Deployment

### Domain-Based Access (Recommended)
```bash
# Instead of: https://yourdomain.com:9847
# Use reverse proxy: https://yourdomain.com
```

### Health Monitoring
```bash
# Monitor port accessibility
curl -f http://localhost:9847/health || echo "Service down"

# Check for port conflicts
ss -tulpn | grep :9847
```

## 📊 Security Score Impact

**Port Security Scoring:**
- Common ports (80, 443, 8000, 8080, 3000): -10 points
- Privileged ports (<1024) in development: Warning only
- Secure ports (>9000, not common): +0 points (baseline)

**Current Status:** ✅ Port 9847 contributes to 100/100 security score

## 🔄 Migration Guide

If changing from common ports:

1. **Update Configuration**
   ```bash
   # In .env file
   PORT=9847
   CORS_ORIGINS=http://localhost:9847,http://127.0.0.1:9847
   EMR_REDIRECT_URI=http://localhost:9847/auth/callback
   ```

2. **Update External Services**
   - OAuth redirect URIs (EMR, Google, etc.)
   - Twilio webhook URLs
   - Monitoring systems
   - Load balancer configurations

3. **Test Connectivity**
   ```bash
   # Start application
   python -m uvicorn src.main:app --host 0.0.0.0 --port 9847

   # Verify access
   curl http://localhost:9847/health
   ```

## 🎯 Summary

**Current Configuration**: Secure ✅
- **Port**: 9847 (non-standard, secure range)
- **Security Score**: 100/100
- **Risk Level**: Low
- **Scan Probability**: Minimal

Your port configuration follows security best practices and significantly reduces the attack surface of your application.
