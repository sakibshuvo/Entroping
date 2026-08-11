# entroping: tags=smoke,checkout
# entroping: story_id=DEMO-001
# entroping: owner=examples

GET {{base_url}}/health
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"

POST {{base_url}}/checkout
Content-Type: application/json
{
  "cart_id": "demo-cart-001"
}
HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.status" == "accepted"
