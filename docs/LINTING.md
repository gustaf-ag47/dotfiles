# Linting - Platform-Independent Code Quality

This repository uses Docker-based linting for platform independence, with automatic fallback to local tools when Docker is unavailable.

## 🐳 Docker-First Approach

All linters run in a consistent Docker environment, ensuring the same results across:
- Linux (Arch, Ubuntu, etc.)
- macOS
- Windows (WSL)
- CI/CD pipelines

**Benefits:**
- ✅ No need to install linters locally
- ✅ Consistent results across all platforms
- ✅ Automatic setup on first use
- ✅ Isolated from system dependencies
- ✅ Easy to update linter versions

## 🚀 Quick Start

### Automatic (Pre-commit Hooks)

Linting runs automatically on every commit:

```bash
# Setup git hooks (one time)
git-setup-hooks

# Linters now run automatically
git add .
git commit -m "feat: add new feature"
# → Runs shellcheck, luac, secret detection, etc.
```

### Manual Linting

```bash
# Run all linters
bin/lint --all

# Run specific linters
bin/lint --shellcheck              # Check all shell scripts
bin/lint --shellcheck bin/backup   # Check specific file
bin/lint --luacheck                # Check Lua files
bin/lint --shfmt                   # Check shell formatting
bin/lint --yamllint                # Check YAML files
```

## 🔧 Available Linters

### ShellCheck
**Purpose**: Shell script static analysis
**Files**: `*.sh`, `*.bash`, `bin/*`
**Detects**: Common shell scripting errors, bad practices

```bash
bin/lint --shellcheck bin/*
```

### Luacheck
**Purpose**: Lua code quality and style
**Files**: `*.lua` (Neovim configs)
**Config**: `.luacheckrc`

```bash
bin/lint --luacheck config/nvim/
```

### shfmt
**Purpose**: Shell script formatting
**Files**: `*.sh`, `*.bash`, `bin/*`
**Style**: 2-space indentation, POSIX-compatible

```bash
bin/lint --shfmt bin/*
```

### yamllint
**Purpose**: YAML syntax and style validation
**Files**: `*.yml`, `*.yaml`

```bash
bin/lint --yamllint
```

## 🏗️ Architecture

### Components

1. **Dockerfile.linters**
   - Alpine Linux base for minimal size (~50MB)
   - Contains all linter tools
   - Built automatically on first use

2. **docker-compose.linters.yml**
   - Individual services for each linter
   - Read-only workspace mounts for security
   - Easy service management

3. **bin/lint**
   - User-friendly CLI interface
   - Automatic Docker/local detection
   - Handles image building

4. **config/git/hooks/pre-commit**
   - Integrates linting into git workflow
   - Uses same Docker infrastructure
   - Fails commits with linting errors

### Fallback Strategy

```
┌─────────────────┐
│  Run linter     │
└────────┬────────┘
         │
         ▼
    ┌─────────┐
    │ Docker? │ ─No──▶ ┌──────────────┐
    └────┬────┘        │ Local tool?  │ ─No──▶ Error
         │Yes          └──────┬───────┘
         │                    │Yes
         ▼                    ▼
    ┌─────────┐         ┌──────────┐
    │ Docker  │         │  Local   │
    │ linter  │         │  linter  │
    └─────────┘         └──────────┘
```

## 🔨 Usage Examples

### Development Workflow

```bash
# 1. Make changes to shell script
vim bin/my-script

# 2. Run shellcheck manually
bin/lint --shellcheck bin/my-script

# 3. Fix any issues
vim bin/my-script

# 4. Commit (runs all checks automatically)
git add bin/my-script
git commit -m "feat: add new script"
```

### Fixing Linter Issues

```bash
# ShellCheck error example
bin/lint --shellcheck bin/backup
# → SC2086: Double quote to prevent globbing
# → SC2164: Use 'cd ... || exit' in case cd fails

# Fix the issues
vim bin/backup

# Verify fix
bin/lint --shellcheck bin/backup
# → ✅ No issues
```

### Suppressing False Positives

```bash
# ShellCheck: Disable specific warning
# shellcheck disable=SC2046
docker ps -q | xargs docker stop

# Luacheck: Ignore unused variable
-- luacheck: ignore unused_param
local function foo(unused_param)
  return 42
end
```

## 🐳 Docker Management

### Building/Rebuilding

```bash
# Automatic build on first use
bin/lint --shellcheck bin/*
# → 📦 Building linters Docker image (first time only)...

# Force rebuild (after updating Dockerfile.linters)
bin/lint --build

# Manual rebuild
docker build -f Dockerfile.linters -t dotfiles-linters:latest .
```

### Inspecting the Image

```bash
# Check image exists
docker image inspect dotfiles-linters:latest

# Run interactive shell in container
docker run -it --rm -v "$PWD:/workspace" -w /workspace dotfiles-linters:latest sh

# Test linters manually
docker run --rm -v "$PWD:/workspace:ro" -w /workspace dotfiles-linters:latest shellcheck bin/backup
```

### Using Docker Compose

```bash
# Run specific linter service
docker compose -f docker-compose.linters.yml run --rm shellcheck bin/*

# Interactive shell
docker compose -f docker-compose.linters.yml run --rm linters sh
```

## 🔧 Forcing Local Tools

Useful when Docker is unavailable or for faster feedback:

```bash
# Force local tools for one command
bin/lint --local --shellcheck bin/*

# Force local via environment variable
export LINT_USE_LOCAL=1
bin/lint --shellcheck bin/*

# Force Docker (fails if unavailable)
export LINT_USE_DOCKER=1
bin/lint --shellcheck bin/*
```

## ⚙️ Configuration Files

### .luacheckrc
```lua
std = "luajit"
globals = { "vim" }
ignore = {
    "212",  -- Unused argument
    "213",  -- Unused loop variable
}
```

### ShellCheck
Use inline directives or `.shellcheckrc`:
```bash
# Disable specific checks
# shellcheck disable=SC2086,SC2046
command $args

# Change shell type
# shellcheck shell=bash
```

## 🐛 Troubleshooting

### Docker image build fails

```bash
# Check Docker is running
docker info

# Build with verbose output
docker build -f Dockerfile.linters -t dotfiles-linters:latest . --no-cache --progress=plain

# Check disk space
docker system df
```

### Linter not found (local mode)

```bash
# Install missing linters
# Arch Linux
sudo pacman -S shellcheck shfmt lua luarocks yamllint

# Lua linter
sudo luarocks install luacheck

# Or use Docker mode
bin/lint --docker --shellcheck bin/*
```

### Pre-commit hook fails

```bash
# Test hook manually
bash config/git/hooks/pre-commit

# Check hook is installed
ls -la .git/hooks/pre-commit

# Reinstall hooks
git-setup-hooks

# Skip hooks temporarily (not recommended)
git commit --no-verify
```

### Permission denied errors

```bash
# Docker socket permission
sudo usermod -aG docker $USER
# Log out and back in

# File permissions
chmod +x bin/lint
chmod +x config/git/hooks/pre-commit
```

## 📊 CI/CD Integration

### GitHub Actions Example

```yaml
name: Lint
on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build linter image
        run: docker build -f Dockerfile.linters -t dotfiles-linters:latest .

      - name: Run shellcheck
        run: bin/lint --shellcheck

      - name: Run luacheck
        run: bin/lint --luacheck
```

## 📈 Best Practices

1. **Run linters early and often**
   ```bash
   bin/lint --all  # Before committing
   ```

2. **Fix issues immediately**
   - Don't accumulate linter warnings
   - Use `# shellcheck disable=SCXXXX` sparingly

3. **Keep Docker image updated**
   ```bash
   bin/lint --build  # After updating Dockerfile.linters
   ```

4. **Use pre-commit hooks**
   - Prevents committing code with issues
   - Saves time in code review

5. **Document suppressions**
   ```bash
   # shellcheck disable=SC2046  # Intentional word splitting for docker ps
   docker stop $(docker ps -q)
   ```

## 🔗 Resources

- [ShellCheck Wiki](https://github.com/koalaman/shellcheck/wiki)
- [Luacheck Documentation](https://luacheck.readthedocs.io/)
- [shfmt Documentation](https://github.com/mvdan/sh)
- [yamllint Documentation](https://yamllint.readthedocs.io/)

---

This Docker-based linting setup provides consistent, platform-independent code quality checks for your dotfiles repository!
