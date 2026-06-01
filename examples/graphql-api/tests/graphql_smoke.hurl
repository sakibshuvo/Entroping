# entroping: tags=smoke,graphql
# entroping: story_id=GQL-001
# entroping: owner=examples

POST http://127.0.0.1:18082/graphql
Content-Type: application/json
{
  "query": "query UserProfile { user(id: \"usr_001\") { id name plan } }"
}
HTTP 200
[Asserts]
jsonpath "$.errors" not exists
jsonpath "$.data.user.id" == "usr_001"
jsonpath "$.data.user.name" == "Ada Lovelace"
jsonpath "$.data.user.plan" == "pro"

POST http://127.0.0.1:18082/graphql
Content-Type: application/json
{
  "query": "mutation UpdatePlan { updatePlan(id: \"usr_001\", plan: \"enterprise\") { id plan updated } }"
}
HTTP 200
[Asserts]
jsonpath "$.errors" not exists
jsonpath "$.data.updatePlan.id" == "usr_001"
jsonpath "$.data.updatePlan.plan" == "enterprise"
jsonpath "$.data.updatePlan.updated" == true
