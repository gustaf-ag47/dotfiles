# Security Guide - Preventing Secret Leaks

This guide explains how the dotfiles repository prevents secrets and sensitive information from being committed.

## 🛡️ Built-in Protection Layers

### 1. Global Gitignore (`config/git/ignore`)

Automatically ignores common secret files:
- `.env` files (except `.env.example`, `.env.template`)
- Private keys (`.pem`, `.key`, `id_rsa`, etc.)
- Credentials files (`.npmrc`, `.pypirc`, `.aws-credentials`)
- Service account files (`service-account*.json`, `gcloud-auth.json`)
- API key files (`*apikey*`, `*api-key*`)

**Setup:**
```bash
# Applied automatically during `make install`
# Or manually:
git config --global core.excludesfile ~/.config/git/ignore
```

### 2. Pre-commit Hook (`config/git/hooks/pre-commit`)

Runs automatically before each commit with multiple checks:

#### ✅ Sensitive Filename Detection
Blocks commits containing:
- `.env`, `.pem`, `.key`, `.cert` files
- `credentials`, `secret`, `password` in filenames
- Private key files (`id_rsa`, `id_dsa`, etc.)

#### ✅ Secret Pattern Matching
Detects common secret formats:
- **AWS Keys**: `AKIA[0-9A-Z]{16}`
- **GitHub Tokens**: `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`
- **Stripe Keys**: `sk_live_`, `rk_live_`
- **Google API Keys**: `AIza[0-9A-Za-z\-_]{35}`
- **Slack Tokens**: `xox[baprs]-`
- **Private Keys**: `-----BEGIN ... PRIVATE KEY-----`
- **Generic Patterns**: `password=`, `api_key=`, `secret=`, `token=`

#### ✅ High-Entropy String Detection
Warns about suspicious base64-like strings (40+ chars) that might be encoded secrets

**Setup:**
```bash
# Install hooks for current repo
git-setup-hooks

# Hooks are automatically copied from config/git/hooks/ to .git/hooks/
```

### 3. Repository .gitignore

Project-specific ignore file for:
- Zsh history and cache files
- Tmux plugins (installed during setup)
- Claude Code local settings
- MCP configuration

## 🚀 Quick Setup

```bash
# 1. Install dotfiles (sets up everything)
make install

# 2. Setup hooks for any git repository
cd /path/to/your/repo
git-setup-hooks
```

## 🔍 Testing Secret Detection

Test that your hooks are working:

```bash
# Create a test file with a fake secret
echo 'export AWS_ACCESS_KEY_ID="AKIAIOSFODNN7EXAMPLE"' > test-secret.sh

# Try to commit it
git add test-secret.sh
git commit -m "test"

# Expected: ❌ Hook should block this commit!

# Clean up
rm test-secret.sh
```

## 📋 Best Practices

### Use Environment Variables
```bash
# ❌ Don't hardcode in scripts
API_KEY="sk_live_abc123xyz789"

# ✅ Use environment variables
API_KEY="${API_KEY}"

# ✅ Load from .env (gitignored)
source .env
```

### Template Files
```bash
# Create .env.example for documentation
cat > .env.example << 'EOF'
API_KEY=your_api_key_here
DATABASE_URL=postgresql://localhost/dbname
SECRET_KEY=your_secret_key_here
EOF

# Users copy and customize
cp .env.example .env
# Edit .env with real values (automatically gitignored)
```

### Using Secrets in Scripts
```bash
#!/bin/bash

# Check if secret is provided
if [ -z "$API_KEY" ]; then
    echo "Error: API_KEY environment variable not set"
    echo "Set it with: export API_KEY=your_key"
    exit 1
fi

# Use the secret
curl -H "Authorization: Bearer $API_KEY" https://api.example.com
```

## 🔧 Advanced: Additional Tools

For extra protection, consider installing dedicated secret scanners:

### Gitleaks (Recommended)

Fast, comprehensive secret scanner:

```bash
# Install
sudo pacman -S gitleaks  # Arch Linux
# or: brew install gitleaks  # macOS

# Scan repository
gitleaks detect --source . --verbose

# Scan commit history
gitleaks detect --source . --log-opts="--all"

# Add as pre-commit hook (in addition to existing hook)
gitleaks protect --staged --verbose
```

### TruffleHog

Deep git history scanner:

```bash
# Install
pip install trufflehog

# Scan repository
trufflehog filesystem . --json

# Scan git history
trufflehog git file://. --since-commit HEAD~10
```

### git-secrets (AWS)

AWS-focused secret prevention:

```bash
# Install
brew install git-secrets  # macOS
# or build from: https://github.com/awslabs/git-secrets

# Setup in repository
git secrets --install
git secrets --register-aws
```

## 🆘 If You Already Committed Secrets

### 1. Remove from Latest Commit
```bash
# If not pushed yet
git reset --soft HEAD~1
# Remove secret, update files
git add -A
git commit -m "your message"
```

### 2. Remove from History (Dangerous!)
```bash
# Using BFG Repo Cleaner (recommended)
java -jar bfg.jar --delete-files secret-file.env
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Or using git-filter-repo
git filter-repo --path secret-file.env --invert-paths
```

### 3. Rotate Compromised Secrets
**IMPORTANT**: Even after removing from git, assume secrets are compromised:
1. Immediately rotate/regenerate all exposed credentials
2. Update secret values in your secret management system
3. Monitor for unauthorized access

## 📊 Checking Protection Status

```bash
# Check global gitignore is set
git config --global core.excludesfile
# Should show: /home/user/.config/git/ignore

# Check hooks are installed
ls -la .git/hooks/pre-commit
# Should exist and be executable

# Test pre-commit hook manually
bash .git/hooks/pre-commit
```

## 🎓 Resources

- [GitHub: Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [OWASP: Secret Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Gitleaks Documentation](https://github.com/gitleaks/gitleaks)

## 🔐 Summary

Your dotfiles provide **three layers of protection**:

1. **Prevention**: Global gitignore blocks common secret files
2. **Detection**: Pre-commit hook scans for secret patterns
3. **Education**: This guide and example templates

**Remember**: No automated tool is 100% perfect. Always review your commits and never commit sensitive data intentionally!
