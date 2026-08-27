# Testing

This directory contains tests for the dotfiles system.

```
tests/
├── e2e/    # Hurl HTTP tests (require running services)
└── unit/   # Python unit tests for bin/ utilities
```

## Unit Tests

Python `unittest` tests covering scripts in `bin/`. No services or network required.

```bash
make test-unit

# Or a single file
python3 -m unittest discover -s tests/unit -t tests/unit -v
```

Naming: `tests/unit/test_<script-name-with-underscores>.py`.
Scripts in `bin/` have no `.py` extension, so load them with `SourceFileLoader`
(see `test_claude_token_proxy.py` for the pattern).

## E2E Tests

End-to-end tests are written in [Hurl](https://hurl.dev/) format and located in `tests/e2e/`.

### Prerequisites

1. **Install Hurl:**
   ```bash
   # Arch Linux
   sudo pacman -S hurl
   
   # Or from source
   cargo install hurl
   ```

2. **Running Docker Compose:**
   ```bash
   docker compose up -d
   ```

### Running Tests

```bash
# Run all tests
make test

# Or directly
./scripts/test.sh
```

### Test Structure

Tests should be placed in `tests/e2e/` with either `.hurl` or `.http` extensions.

Example test file structure:
```hurl
# Comment describing the test
GET http://localhost:8080/api/endpoint
HTTP 200
[Asserts]
status == 200
jsonpath "$.field" == "expected_value"
```

### Features Supported

- **HTTP Methods:** GET, POST, PUT, DELETE, PATCH, etc.
- **Request Headers:** Custom headers and content types
- **Request Body:** JSON, XML, form data
- **Response Assertions:** Status codes, headers, JSON path
- **Variables:** Capture and reuse values between requests
- **Environment:** Support for different environments via variables

### Test Organization

- `example.hurl` - Basic health check example
- `api-comprehensive.hurl` - Full CRUD operations test
- Add more test files as needed for specific features

### Configuration

Test configuration is in `scripts/test.sh`:
- `E2E_DIR` - Directory containing test files
- `HURL_OPTIONS` - Hurl command options
- Docker compose service validation

### Debugging

For verbose output and debugging:
```bash
# Run with debug output
hurl --test --verbose tests/e2e/your-test.hurl

# Run single test file
hurl --test tests/e2e/api-comprehensive.hurl
```