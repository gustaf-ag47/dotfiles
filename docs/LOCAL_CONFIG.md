# Managing Personal & Private Configurations

This guide explains how to manage personal, company-specific, or sensitive configurations separately from your public dotfiles repository.

## Quick Start

### 1. Create Your Personal Files

The `local/` directory is already set up and gitignored. Create your personal configurations:

```bash
cd $DOTFILES/local

# Create personal environment variables
cat > env/.env << 'EOF'
# Your personal API keys and tokens
export OPENAI_API_KEY="your-key-here"
export GITHUB_TOKEN="your-token-here"
EOF

# Create work-specific desktop launcher
cat > applications/work-slack.desktop << 'EOF'
[Desktop Entry]
Name=Work Slack
Exec=firefox https://app.slack.com/client/YOUR_WORKSPACE/YOUR_CHANNEL
Type=Application
EOF

# Create personal zsh config
cat > config/zsh/work.zsh << 'EOF'
# Work-specific aliases
alias deploy="ssh prod-server './deploy.sh'"
EOF

# Create personal script
cat > bin/company-connect << 'EOF'
#!/bin/bash
ssh your-company-vpn
EOF
chmod +x bin/company-connect
```

### 2. Install

Run `make install` and your personal files will be automatically integrated:

```bash
cd $DOTFILES
make install
```

This will:
- Copy `local/applications/*.desktop` to `~/.local/share/applications/`
- Add `local/bin/` to your PATH
- Source `local/env/.env` in your shell
- Load `local/config/zsh/*.zsh` files

### 3. Reload Shell

```bash
source ~/.zshenv
source ~/.config/zsh/.zshrc
# or just: exec zsh
```

## Directory Structure

```
local/
├── README.md                      # Documentation (tracked in git)
├── .gitkeep                       # Keeps structure (tracked in git)
├── applications/                  # Personal .desktop files
│   ├── example-work-tool.desktop.example  # Template (tracked)
│   └── work-slack.desktop        # Your file (gitignored)
├── bin/                          # Personal scripts
│   └── company-deploy            # Your script (gitignored)
├── config/                       # Config overrides
│   ├── zsh/                     # Personal zsh configs
│   │   └── work.zsh             # Your config (gitignored)
│   └── git/                     # Personal git config
│       └── config               # Your config (gitignored)
└── env/                         # Environment variables
    ├── .env.example             # Template (tracked)
    └── .env                     # Your file (gitignored)
```

## Common Use Cases

### Company-Specific Application Launchers

**Problem**: You removed company-specific launchers from the public repo.

**Solution**: Recreate them in `local/applications/`:

```bash
# Shortcut.com (project management)
cat > local/applications/shortcut.desktop << 'EOF'
[Desktop Entry]
Name=Shortcut
Exec=firefox https://app.shortcut.com/YOUR_COMPANY/stories
Type=Application
Icon=web-browser
EOF

# Sentry (error tracking)
cat > local/applications/sentry.desktop << 'EOF'
[Desktop Entry]
Name=Sentry
Exec=firefox https://YOUR_COMPANY.sentry.io
Type=Application
Icon=web-browser
EOF

# BetterStack (logging)
cat > local/applications/betterstack.desktop << 'EOF'
[Desktop Entry]
Name=BetterStack
Exec=firefox https://logs.betterstack.com/team/YOUR_TEAM_ID/sources
Type=Application
Icon=web-browser
EOF

# Work Slack
cat > local/applications/work-slack.desktop << 'EOF'
[Desktop Entry]
Name=Work Slack
Exec=chromium https://app.slack.com/client/YOUR_WORKSPACE/YOUR_CHANNEL
Type=Application
Icon=slack
EOF
```

Then reinstall:
```bash
make install
```

### Personal API Keys & Tokens

**Problem**: Need API keys for development but can't commit them.

**Solution**: Add to `local/env/.env`:

```bash
# local/env/.env
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GITHUB_TOKEN="ghp_..."
export SLACK_WEBHOOK="https://hooks.slack.com/..."
```

These are automatically loaded in your shell!

### Work-Specific Aliases & Functions

**Problem**: Need work shortcuts but don't want them public.

**Solution**: Create `local/config/zsh/work.zsh`:

```bash
# Deployment shortcuts
alias deploy-staging="ssh staging-server './deploy.sh'"
alias deploy-prod="ssh prod-server './deploy.sh'"

# VPN connections
alias vpn-connect="sudo openvpn /etc/openvpn/company.conf"

# Database connections
alias db-prod="psql $PROD_DATABASE_URL"
alias db-staging="psql $STAGING_DATABASE_URL"

# Company-specific functions
work-sync() {
    rsync -av --progress \
        company-server:/data/ \
        ~/work/data/
}
```

### Private Deployment Scripts

**Problem**: Company-specific deployment scripts.

**Solution**: Add to `local/bin/`:

```bash
#!/bin/bash
# local/bin/deploy-company-app

set -e

echo "Deploying to production..."
ssh prod-server "cd /app && git pull && docker-compose up -d"
echo "Deployment complete!"
```

Make executable:
```bash
chmod +x local/bin/deploy-company-app
```

### Git Configuration for Work

**Problem**: Different git config for work repositories.

**Solution**: Create `local/config/git/config`:

```gitconfig
[user]
    email = your-name@company.com
    signingkey = YOUR_WORK_GPG_KEY

[url "git@github.com:your-company/"]
    insteadOf = https://github.com/your-company/
```

Then use conditional includes in main git config:
```gitconfig
# In config/git/config
[includeIf "gitdir:~/work/"]
    path = ~/.config/git/local-config
```

## Backup & Sync

### Option 1: Private Git Repository (Recommended)

```bash
cd $DOTFILES/local
git init
git remote add origin git@github.com:your-username/dotfiles-private.git

# Add all your personal files
git add .
git commit -m "Initial private configurations"
git push -u origin main
```

**Advantages**:
- Version control for personal configs
- Easy sync between machines
- Can use private GitHub repo

### Option 2: Sync Directory

```bash
# Move local/ to synced location
mv $DOTFILES/local $SYNC/dotfiles-local

# Create symlink
ln -s $SYNC/dotfiles-local $DOTFILES/local
```

**Advantages**:
- Syncs with other files (Syncthing, Dropbox, etc.)
- No separate git repo needed

### Option 3: System Backup

Add to `bin/backup` script:

```bash
backup_item "$DOTFILES/local" "$BACKUP_FOLDER/dotfiles-local" "600" "700"
```

## Security Best Practices

### ✅ Store in `local/`:
- Company URLs and team IDs
- API keys and tokens
- Work-related shortcuts
- Personal scripts
- Machine-specific configs
- Private deployment scripts

### ❌ Never Commit:
- Actual secrets/credentials
- Private keys or certificates
- Company-specific information
- Personal identifying details

### 🔒 Permissions:
```bash
# Secure your env files
chmod 600 local/env/.env

# Secure your config directory
chmod 700 local/config

# Make scripts executable
chmod +x local/bin/*
```

## Troubleshooting

### Changes Not Applied?

```bash
# Reinstall to copy desktop files
make install

# Reload shell to source configs
exec zsh
```

### Environment Variables Not Loaded?

```bash
# Check if .env exists
ls -la $DOTFILES/local/env/.env

# Manually source it
source $DOTFILES/local/env/.env

# Check if it's being loaded
echo $YOUR_VARIABLE_NAME
```

### Scripts Not in PATH?

```bash
# Check if directory exists
ls -la $DOTFILES/local/bin

# Check PATH
echo $PATH | grep local/bin

# Reload shell
exec zsh
```

## Migration Guide

If you previously had company-specific configs in the public repo:

### 1. Move Desktop Files
```bash
# These were removed from the public repo
cd $DOTFILES
mkdir -p local/applications

# Recreate your work launchers (see examples above)
# Then reinstall
make install
```

### 2. Extract Hardcoded Secrets
```bash
# Find any hardcoded values
grep -r "YOUR_PATTERN" config/

# Move to local/env/.env
echo 'export YOUR_SECRET="value"' >> local/env/.env
```

### 3. Move Company-Specific Aliases
```bash
# Extract from config/zsh/aliases
# Move to local/config/zsh/work.zsh
```

## FAQ

**Q: Can I share some local configs between machines?**
A: Yes! Use Option 1 (Private Git Repo) or Option 2 (Sync Directory)

**Q: What if I want different configs per machine?**
A: Create machine-specific files: `local/config/zsh/machine-laptop.zsh`

**Q: Can I have different local configs for work vs personal?**
A: Yes! Use different directories or git branches in your private repo

**Q: How do I know what's being loaded?**
A: Add debug output to `.zshrc`:
```bash
if [ -f "$DOTFILES/local/env/.env" ]; then
    echo "Loading personal environment..."
    source "$DOTFILES/local/env/.env"
fi
```

---

**Remember**: The `local/` directory is completely private and gitignored. Store anything personal, sensitive, or company-specific here without worry!
