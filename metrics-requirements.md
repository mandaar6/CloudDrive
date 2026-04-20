# CloudDrive Metrics for Grafana Dashboard

This document outlines the structured log events that CloudDrive must emit for the Product Health Grafana dashboard to function properly.

## Required Log Structure

All events must be logged as JSON using the `log_event()` function from `logging_utils.py`. The base structure includes:

```json
{
  "timestamp": "2026-04-20T05:48:00.982586Z",
  "service": "backend",
  "event": "event_name",
  "level": "info|warning|error",
  "endpoint": "/api/path",
  "http_status": 200,
  "ip": "client_ip",
  "user_id": 123,
  "latency_ms": 150
}
```

## Required Events for Dashboard Panels

### 1. Authentication Events

#### Login Failures
```json
{
  "event": "login_failure",
  "level": "warning",
  "endpoint": "/api/auth/login",
  "http_status": 401,
  "ip": "client_ip",
  "email": "user@example.com"
}
```
- **Used by**: Login Failures (5m) panel
- **Query**: `count_over_time({job="containerlogs"} | json | service="backend" | event="login_failure" [5m])`

#### Login Success
```json
{
  "event": "login_success",
  "endpoint": "/api/auth/login",
  "http_status": 200,
  "ip": "client_ip",
  "user_id": 123,
  "email": "user@example.com",
  "latency_ms": 306
}
```
- **Used by**: Core Product Activity timeseries

### 2. File Operation Events

#### File Upload Success
```json
{
  "event": "file_upload_success",
  "endpoint": "/api/files/upload",
  "http_status": 201,
  "ip": "client_ip",
  "user_id": 123,
  "file_id": 456,
  "file_name": "document.pdf",
  "file_size": 1024000,
  "content_type": "application/pdf",
  "s3_bucket": "clouddrivesample",
  "s3_key": "uploads/123/abc123_document.pdf",
  "latency_ms": 1517
}
```
- **Used by**: Uploads (5m) panel and Core Product Activity timeseries
- **Query**: `count_over_time({job="containerlogs"} | json | service="backend" | event="file_upload_success" [5m])`

#### File Download Success
```json
{
  "event": "file_download_success",
  "endpoint": "/api/files/456/download",
  "http_status": 200,
  "ip": "client_ip",
  "user_id": 123,
  "file_id": 456,
  "owner_id": 123,
  "s3_key": "uploads/123/abc123_document.pdf",
  "latency_ms": 10
}
```
- **Used by**: Downloads (5m) panel and Core Product Activity timeseries
- **Query**: `count_over_time({job="containerlogs"} | json | service="backend" | event="file_download_success" [5m])`

### 3. Error Events

#### General Errors
```json
{
  "event": "any_event_name",
  "level": "error",
  "endpoint": "/api/some/endpoint",
  "http_status": 500,
  "ip": "client_ip",
  "user_id": 123,
  "error": "Error description",
  "additional_fields": "..."
}
```
- **Used by**: Errors (5m) panel
- **Query**: `count_over_time({job="containerlogs"} | json | service="backend" | level="error" [5m])`

### 4. HTTP Error Events (5xx Status Codes)

#### Server Errors
```json
{
  "event": "any_event_name",
  "level": "error",
  "endpoint": "/api/failing/endpoint",
  "http_status": 500,
  "ip": "client_ip",
  "user_id": 123,
  "error": "Internal server error",
  "additional_fields": "..."
}
```
- **Used by**: Top Failing Endpoints table
- **Query**: `topk(10, sum by (endpoint) (count_over_time({job="containerlogs"} | json | service="backend" | http_status=~"5.." | endpoint!="" [$__range])))`

## Implementation Requirements

### 1. Structured Logging
- All events must use the `log_event()` function
- Events must include `service: "backend"` for filtering
- Timestamps must be in ISO format with 'Z' suffix

### 2. Required Fields by Event Type

#### All Events (Base Fields)
- `timestamp`: ISO 8601 format
- `service`: Must be "backend"
- `event`: Event name string
- `level`: "info", "warning", or "error"
- `endpoint`: API endpoint path
- `http_status`: HTTP status code
- `ip`: Client IP address

#### Authentication Events (Additional)
- `email`: User email address
- `user_id`: User ID (on success)

#### File Events (Additional)
- `user_id`: User performing action
- `file_id`: File ID
- `file_name`: Original filename
- `file_size`: File size in bytes
- `content_type`: MIME type
- `s3_bucket`: S3 bucket name
- `s3_key`: S3 object key
- `owner_id`: File owner ID (downloads)
- `latency_ms`: Operation duration

#### Error Events (Additional)
- `error`: Error description/message

### 3. Loki Ingestion Requirements
- Logs must be sent to stdout/stderr in containers
- Promtail must be configured to collect from Docker containers
- Loki must be running and accessible
- Grafana datasource must be configured with `uid: loki`

## Current Implementation Status

✅ **Implemented Events:**
- `login_failure` - Logged on authentication failure
- `login_success` - Logged on successful login
- `file_upload_success` - Logged on successful file upload
- `file_download_success` - Logged on successful file download
- Error events - Logged with `level="error"`

✅ **Required Fields Present:**
- All base fields (timestamp, service, event, level, endpoint, http_status, ip)
- Authentication fields (email, user_id)
- File operation fields (file_id, file_name, file_size, etc.)
- Error fields (error description)

## Testing Metrics Emission

To verify metrics are working:

1. **Generate test activity:**
   ```bash
   # Failed login
   curl -X POST http://localhost/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"wrong@example.com","password":"wrong"}'

   # Successful login
   curl -X POST http://localhost/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"password"}'

   # File upload (requires auth token)
   # File download (requires auth token)
   ```

2. **Check Grafana dashboard** at http://localhost:3000
3. **Query Loki directly:**
   ```bash
   curl "http://localhost:3100/loki/api/v1/query?query={job=\"containerlogs\"} | json | service=\"backend\" | event=\"login_failure\""
   ```

## Troubleshooting

If dashboard shows no data:
1. Check Loki is running: `docker-compose ps loki`
2. Check Promtail is running: `docker-compose ps promtail`
3. Verify logs are being generated: `docker-compose logs backend --tail 10`
4. Check Loki ingestion: Query Loki directly for recent logs
5. Verify Grafana datasource: Check http://localhost:3000/datasources