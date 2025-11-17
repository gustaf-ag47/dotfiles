# Local Configuration Directory

This directory contains **personal, private, or company-specific** configurations that should NOT be committed to the public repository.

## Purpose

The `local/` directory provides a space for:
- Company-specific application launchers
- Personal API keys or tokens (use `.env` files)
- Work-related configurations
- Machine-specific settings
- Private shortcuts and aliases

## Directory Structure

```
local/
├── applications/       # Personal .desktop files (copied to ~/.local/share/applications/)
├── bin/               # Personal scripts (added to PATH)
├── config/            # Personal config overrides
│   ├── zsh/          # Personal zsh configs (sourced after main .zshrc)
│   └── git/          # Personal git config
└── env/              # Environment variables for personal use
    └── .env          # Personal environment variables
```

## How It Works

1. **Gitignored**: Everything in `local/` is ignored by git (except this README)
2. **Auto-loaded**: The installation script automatically:
   - Copies `local/applications/*.desktop` to `~/.local/share/applications/`
   - Adds `local/bin/` to your PATH
   - Sources `local/env/.env` in your shell
   - Sources `local/config/zsh/*.zsh` files

## Examples

### Personal Desktop Launchers

Create work-specific launchers in `local/applications/`:

**local/applications/work-slack.desktop:**
```desktop
[Desktop Entry]
Name=Work Slack
Exec=chromium https://app.slack.com/client/YOUR_WORKSPACE/YOUR_CHANNEL
Type=Application
```

**local/applications/company-tools.desktop:**
```desktop
[Desktop Entry]
Name=Company Dashboard
Exec=firefox https://internal-tool.your-company.com
Type=Application
```

### Personal Environment Variables

**local/env/.env:**
```bash
# Company-specific
export COMPANY_API_KEY="your-api-key-here"
export JIRA_TOKEN="your-token"
export WORK_SLACK_WEBHOOK="your-webhook-url"

# Personal
export OPENAI_API_KEY="your-key"
export GITHUB_TOKEN="your-token"
```

### Personal Zsh Configuration

**local/config/zsh/work.zsh:**
```bash
# Work-specific aliases
alias deploy-prod="ssh prod-server && ./deploy.sh"
alias company-vpn="sudo openvpn /path/to/company.ovpn"

# Company-specific functions
work-connect() {
    ssh your-company-server
}
```

### Personal Git Configuration

**local/config/git/config:**
```gitconfig
[user]
    # Override for work repositories
    email = your-name@company.com
    signingkey = YOUR_GPG_KEY

[url "git@github.com:your-company/"]
    insteadOf = https://github.com/your-company/
```

### Personal Scripts

**local/bin/company-deploy:**
```bash
#!/bin/bash
# Company-specific deployment script
echo "Deploying to production..."
```

## Installation

When you run `make install`, the installation script will:

1. Create the `local/` directory structure if it doesn't exist
2. Copy personal desktop files to the correct location
3. Set up PATH to include `local/bin/`
4. Configure shell to source personal configs

## Security Best Practices

### ✅ DO Store Here:
- Company-specific URLs and team IDs
- Personal access tokens (in `.env` files)
- Work-related shortcuts
- Machine-specific configurations
- Private scripts and tools

### ❌ DON'T Store Here:
- Nothing! This is your private space
- But remember: **NEVER commit local/ files to git**

## Backup Considerations

Since `local/` is gitignored, you have two options:

### Option 1: Separate Private Git Repository
```bash
cd $DOTFILES/local
git init
git remote add origin git@github.com:your-username/dotfiles-private.git
git add .
git commit -m "Private configurations"
git push -u origin main
```

### Option 2: Include in System Backup
Your `backup` script already backs up sensitive directories. You can add:
```bash
backup_item "$DOTFILES/local" "$BACKUP_FOLDER/dotfiles-local" "600" "700"
```

## Template Files

Copy these templates to get started:

```bash
# Create directory structure
mkdir -p local/{applications,bin,config/zsh,config/git,env}

# Create template files
cat > local/env/.env << 'EOF'
# Personal environment variables
# Add your API keys, tokens, etc. here
EOF

cat > local/config/zsh/personal.zsh << 'EOF'
# Personal zsh configuration
# Add your personal aliases and functions here
EOF

# Make scripts executable
chmod +x local/bin/*
```

## Sharing Between Machines

If you have multiple machines and want to share personal configs:

```bash
# Store in a synced location
ln -s $SYNC/private/dotfiles-local $DOTFILES/local

# Or use a private git repository (Option 1 above)
```

---

**Remember**: The `local/` directory is YOUR private space. Keep sensitive information here, not in the public repository!
