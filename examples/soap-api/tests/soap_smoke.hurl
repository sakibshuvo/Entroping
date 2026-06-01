# entroping: tags=smoke,soap
# entroping: story_id=SOAP-001
# entroping: owner=examples

POST http://127.0.0.1:18083/soap/orders
Content-Type: text/xml; charset=utf-8
SOAPAction: GetOrder
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ord="https://entroping.dev/examples/orders">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:id>ord_1001</ord:id>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
HTTP 200
[Asserts]
header "X-Request-Id" exists
xpath "string(//*[local-name()='id'])" == "ord_1001"
xpath "string(//*[local-name()='status'])" == "paid"
xpath "string(//*[local-name()='total'])" == "42.50"
