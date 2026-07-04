# entroping: tags=smoke,aha-endpoint
# entroping: story_id=AHA-001
# entroping: owner=examples

GET {{base_url}}/health
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"

GET {{base_url}}/products
HTTP 200
[Asserts]
jsonpath "$.items[0].id" == "prd_001"

GET {{base_url}}/products/ghost
HTTP 404
