# entroping: tags=smoke,checkout
# entroping: story_id=DEMO-001
# entroping: owner=examples

GET http://127.0.0.1:18080/health
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"

POST http://127.0.0.1:18080/checkout
Content-Type: application/json
{
  "cart_id": "demo-cart-001"
}
HTTP 201
[Asserts]
jsonpath "$.id" exists
jsonpath "$.status" == "accepted"
