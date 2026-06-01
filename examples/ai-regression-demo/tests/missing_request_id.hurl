# entroping: tags=ai-regression,smoke
# entroping: story_id=DEMO-AI-REG-001
# entroping: owner=examples

GET {{base_url}}/checkout/demo-cart-001
HTTP 200
[Asserts]
jsonpath "$.status" == "accepted"
