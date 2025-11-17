# Comprehensive API test suite
# Tests various endpoints and HTTP methods

# Health check endpoint
GET http://localhost:8080/health
HTTP 200
[Asserts]
status == 200
header "Content-Type" contains "json"
jsonpath "$.status" == "healthy"

# API info endpoint
GET http://localhost:8080/api/v1/info
HTTP 200
[Asserts]
status == 200
jsonpath "$.version" exists
jsonpath "$.environment" exists

# Test POST request with JSON payload
POST http://localhost:8080/api/v1/users
Content-Type: application/json
{
  "name": "Test User",
  "email": "test@example.com"
}
HTTP 201
[Captures]
user_id: jsonpath "$.id"
[Asserts]
status == 201
jsonpath "$.name" == "Test User"
jsonpath "$.email" == "test@example.com"
jsonpath "$.id" exists

# Get created user
GET http://localhost:8080/api/v1/users/{{user_id}}
HTTP 200
[Asserts]
status == 200
jsonpath "$.id" == {{user_id}}
jsonpath "$.name" == "Test User"

# Update user
PUT http://localhost:8080/api/v1/users/{{user_id}}
Content-Type: application/json
{
  "name": "Updated User",
  "email": "updated@example.com"
}
HTTP 200
[Asserts]
status == 200
jsonpath "$.name" == "Updated User"

# Delete user
DELETE http://localhost:8080/api/v1/users/{{user_id}}
HTTP 204
[Asserts]
status == 204

# Verify user is deleted
GET http://localhost:8080/api/v1/users/{{user_id}}
HTTP 404
[Asserts]
status == 404