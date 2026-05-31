# entroping: tags=smoke,support
# entroping: story_id=SUP-001
# entroping: owner=examples

GET http://127.0.0.1:18081/health
HTTP 200
[Asserts]
jsonpath "$.service" == "support-api"
jsonpath "$.status" == "ok"

GET http://127.0.0.1:18081/tickets?status=open&limit=2
Accept: application/json
HTTP 200
[Asserts]
jsonpath "$.items[0].id" == "tkt_001"
jsonpath "$.items[0].priority" == "high"
jsonpath "$.next_cursor" exists

POST http://127.0.0.1:18081/tickets
Content-Type: application/json
X-Customer-Id: cust-123
{
  "subject": "Cannot download invoice",
  "priority": "high"
}
HTTP 201
[Asserts]
header "Location" exists
header "X-Audit-Id" exists
jsonpath "$.id" == "tkt_cust-123_001"
jsonpath "$.status" == "open"

PATCH http://127.0.0.1:18081/tickets/tkt_cust-123_001/status
Content-Type: application/json
X-Agent-Id: agent-007
{
  "status": "triaged"
}
HTTP 200
[Asserts]
header "X-Audit-Id" exists
jsonpath "$.id" == "tkt_cust-123_001"
jsonpath "$.status" == "triaged"
