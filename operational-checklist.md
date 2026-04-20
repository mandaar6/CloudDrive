# CloudDrive Operational State Checklist

This checklist provides quick questions that can help understand the operational state of CloudDrive. The Product Health Dashboard can be used to answer these questions.

## Recent Activity Metrics (Last 5 minutes)

- [ ] How many login failures have occurred? (Login Failures panel)
- [ ] How many files have been uploaded? (Uploads panel)
- [ ] How many files have been downloaded? (Downloads panel)
- [ ] How many errors have been logged? (Errors panel)

## Activity Trends

- [ ] What does the activity timeline show for logins, uploads, and downloads? (Core Product Activity chart)
- [ ] Are there any spikes or unusual patterns in the activity?

## System Health

- [ ] What are the top failing endpoints? (Top Failing Endpoints table)
- [ ] Are there any endpoints returning 5xx errors?
- [ ] Which endpoints are experiencing the most failures?

## Dashboard Access

- [ ] Is the Grafana dashboard accessible at http://localhost:3000?
- [ ] Are all dashboard panels loading without errors?
- [ ] Is the dashboard showing current data (not stale)?

## Quick Diagnostic Commands

```bash
# Check dashboard access
curl http://localhost:3000

# Query recent login failures
curl "http://localhost:3100/loki/api/v1/query?query=sum(count_over_time({job=\"containerlogs\"} | json | service=\"backend\" | event=\"login_failure\" [5m]))"

# Query recent errors
curl "http://localhost:3100/loki/api/v1/query?query=sum(count_over_time({job=\"containerlogs\"} | json | service=\"backend\" | level=\"error\" [5m]))"

# Query top failing endpoints
curl "http://localhost:3100/loki/api/v1/query?query=topk(10, sum by (endpoint) (count_over_time({job=\"containerlogs\"} | json | service=\"backend\" | http_status=~\"5..\" | endpoint!=\"\" [1h])))"
```