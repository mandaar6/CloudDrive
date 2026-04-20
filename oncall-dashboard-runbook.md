# CloudDrive On-Call Dashboard Runbook

This runbook guides on-call engineers through using the Grafana Product Health dashboard to diagnose and respond to CloudDrive incidents.

## Quick Access

- **Dashboard URL**: http://localhost:3000/dashboards (admin/admin)
- **Time Range**: Default to "Last 6 hours" for context
- **Refresh**: Auto-refresh every 30 seconds during incidents

## Dashboard Overview

The Product Health dashboard provides real-time visibility into CloudDrive's operational health through 6 key panels:

### 1. Login Failures (5m)
**What it shows**: Count of failed authentication attempts in the last 5 minutes
**Normal range**: 0-5 (occasional typos/forgetful users)
**Alert thresholds**:
- >10/min: Investigate authentication issues
- >50/min: Possible brute force attack or auth service down
- >100/min: **Wake up team** - Major auth outage

**Common causes**:
- Database connectivity issues
- Password hashing problems
- User account lockouts
- Brute force attacks

### 2. Uploads (5m)
**What it shows**: Successful file uploads in the last 5 minutes
**Normal range**: Varies by usage, but should be >0 during business hours
**Alert thresholds**:
- =0 for >30min: Check S3 connectivity
- Sudden drop >80%: Investigate upload service
- **Wake up team**: Complete upload outage

**Common causes**:
- S3 bucket issues
- Database write failures
- File size limits
- Network connectivity

### 3. Downloads (5m)
**What it shows**: Successful file downloads in the last 5 minutes
**Normal range**: Should exceed uploads (files downloaded multiple times)
**Alert thresholds**:
- =0 for >30min: Check S3 presigned URL generation
- Sudden drop >80%: Investigate download service
- **Wake up team**: Complete download outage

**Common causes**:
- S3 access issues
- Presigned URL expiry problems
- Database read failures

### 4. Errors (5m)
**What it shows**: Count of ERROR level log entries in the last 5 minutes
**Normal range**: 0-2 (rare exceptions)
**Alert thresholds**:
- >5/min: Investigate error patterns
- >20/min: **Wake up team** - Application experiencing failures
- Sustained >10/min: Performance degradation

**Common causes**:
- Database connection issues
- S3 timeouts
- Code exceptions
- Resource exhaustion

### 5. Core Product Activity (Timeseries)
**What it shows**: Time-series chart of login failures, uploads, and downloads
**How to read**:
- Look for spikes, drops, or flatlines
- Compare trends across all three metrics
- Identify correlation between events

**Patterns to watch**:
- All metrics drop to zero: Complete service outage
- Only uploads fail: S3 write issues
- Only downloads fail: S3 read/presigned URL issues
- Login failures spike: Auth problems or attack

### 6. Top Failing Endpoints
**What it shows**: Endpoints returning 5xx errors, ranked by frequency
**How to use**:
- Identifies which API endpoints are failing
- Helps prioritize which service to investigate first
- Shows error distribution across the application

**Common failing endpoints**:
- `/api/auth/login`: Authentication service issues
- `/api/files/upload`: Upload/S3 problems
- `/api/files/{id}/download`: Download/presigned URL issues
- `/api/files/`: Database or file listing problems

## Incident Response Workflow

### Step 1: Assess Severity
1. **Check all panels for zero values**:
   - If all metrics = 0: **Complete outage** - Wake up team immediately
   - If only some metrics = 0: Partial failure - Investigate specific service

2. **Check error rates**:
   - Errors >20/min: **High severity** - Application failing
   - Errors 5-20/min: **Medium severity** - Investigate patterns
   - Errors <5/min: **Low severity** - Monitor and investigate if sustained

3. **Check failing endpoints**:
   - Multiple endpoints failing: **System-wide issue**
   - Single endpoint failing: **Isolated service problem**

### Step 2: Correlate Symptoms
Use the timeseries chart to understand the timeline:
- **When did the problem start?**
- **What changed at that time?**
- **Are there multiple symptoms or just one?**

### Step 3: Investigate by Symptom

#### Authentication Issues (High Login Failures)
```bash
# Check database connectivity
docker-compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1"

# Check backend logs
docker-compose logs backend --tail 50 | grep -i auth

# Test login manually
curl -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test"}'
```

#### File Operation Issues (Zero Uploads/Downloads)
```bash
# Check S3 connectivity
docker-compose exec backend python3 -c "
import boto3
s3 = boto3.client('s3')
s3.head_bucket(Bucket='your-bucket-name')
print('S3 OK')
"

# Check backend logs
docker-compose logs backend --tail 50 | grep -i "upload\|download\|s3"

# Test file operations manually
# (Requires authentication token)
```

#### High Error Rates
```bash
# Get detailed error logs
docker-compose logs backend --tail 100 | grep ERROR

# Check Loki for error patterns
curl "http://localhost:3100/loki/api/v1/query?query={job=\"containerlogs\"} | json | level=\"error\""

# Check system resources
docker stats
```

### Step 4: Common Quick Fixes

#### Database Issues
```bash
# Restart database
docker-compose restart db

# Check database logs
docker-compose logs db --tail 20
```

#### Backend Issues
```bash
# Restart backend
docker-compose restart backend

# Check backend health
curl http://localhost/api/health
```

#### S3/Network Issues
```bash
# Check network connectivity
docker-compose exec backend ping -c 3 s3.amazonaws.com

# Verify AWS credentials
docker-compose exec backend python3 -c "
import os
print('AWS_ACCESS_KEY_ID:', bool(os.getenv('AWS_ACCESS_KEY_ID')))
print('AWS_SECRET_ACCESS_KEY:', bool(os.getenv('AWS_SECRET_ACCESS_KEY')))
"
```

### Step 5: Escalation Criteria

**Wake up the team if:**
- All dashboard metrics = 0 (complete outage)
- Error rate >20/min sustained for >5 minutes
- Authentication completely broken (can't login at all)
- Critical customer-impacting issues
- Issues persist >30 minutes without resolution

**Page team lead if:**
- Security-related issues (brute force patterns)
- Data loss or corruption suspected
- Infrastructure problems (disk space, memory)

**Monitor and investigate if:**
- Intermittent issues
- Single service degradation
- Non-critical functionality affected

## Dashboard Maintenance

### During Normal Operations
- Verify dashboard loads without errors
- Check that all panels show data during business hours
- Monitor for unusual patterns even when no alerts

### After Incident Resolution
- Document what the dashboard showed during the incident
- Note any dashboard gaps or improvements needed
- Update runbook with new patterns learned

## Common False Positives

- **Zero metrics during off-hours**: Normal if no users active
- **Login failures**: Common during password resets or account issues
- **Temporary spikes**: May be due to batch operations or testing
- **Weekend drops**: Expected if usage is business-hours only

## Dashboard Limitations

- **No infrastructure metrics**: Doesn't show CPU, memory, disk usage
- **No user experience data**: Doesn't measure page load times or client-side errors
- **Log-based only**: Dependent on application logging quality
- **No alerting**: Dashboard is monitoring tool, not alerting system

## Contact Information

- **On-call Engineer**: Current rotation
- **Team Lead**: [contact]
- **DevOps/SRE**: [contact]
- **Security Team**: [contact]

---

**Last Updated**: April 19, 2026
**Dashboard Version**: Product Health v1.0