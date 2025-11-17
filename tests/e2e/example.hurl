# Example Hurl test file for dotfiles system testing
# This tests that the system is responding correctly

GET http://localhost:8080/health
HTTP 200
[Asserts]
status == 200
header "Content-Type" contains "application/json"

GET http://localhost:8080/api/status
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"