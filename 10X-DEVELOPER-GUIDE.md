# 🚀 10x Developer Setup Guide

## Overview

This guide transforms your Arch Linux setup into a productivity powerhouse for 10x development. You already have a solid foundation with Hyprland, Neovim, and tmux - now let's supercharge it!

## 🎯 Quick Start

```bash
# Run the setup script to install all enhancements
~/sync/src/dotfiles/bin/dev-setup

# Source enhanced shell configuration
source ~/.zshrc

# Check your new development environment
dev-monitor status
```

## 🛠️ New Tools & Commands

### Project Management
```bash
# Create new projects with templates
project-manager new my-app react
project-manager new api-server fastapi
project-manager new rust-cli rust

# List and navigate projects
project-manager list
project-manager open              # FZF selection
project-manager open my-app      # Direct navigation

# Clone and auto-setup repositories
project-manager clone https://github.com/user/repo
```

### System Monitoring
```bash
# Quick status overview
dev-monitor status

# Performance analysis
dev-monitor performance --watch

# Monitor development processes
dev-monitor processes

# Check ports and services
dev-monitor ports

# System health check
dev-monitor health

# Run benchmarks
dev-monitor benchmark
```

### Enhanced Git Workflow
```bash
# Smart git operations
gs                    # git status --short
gd                    # git diff  
gl                    # git log --oneline --graph -10
gwip                  # git add . && commit "WIP"
gunwip                # undo WIP commit
gclone <url>          # clone and cd into repo
git_clean_branches    # remove merged branches
git_backup            # backup current branch
```

### Smart Navigation & Search
```bash
# Enhanced file operations
ll                    # beautiful file listing with git status
lt                    # tree view with git info
lsize                 # sort by size
ltime                 # sort by modification time

# FZF-powered commands
vf                    # edit file with preview
cf                    # cd to directory
preview               # preview files with syntax highlighting
fzf_history          # search command history
```

### Docker Development
```bash
# Docker shortcuts
dps                   # formatted docker ps
dimg                  # formatted docker images
dlogs <container>     # follow logs
dexec <container>     # exec into container
dclean                # clean up docker system
docker_dev <service>  # start and follow service logs
docker_shell          # interactive shell selection
```

### Development Environment
```bash
# Quick servers
serve_dir [port] [dir]    # HTTP server (default: port 8000, current dir)
pg_connect [db] [host]    # PostgreSQL connection
redis_connect [host]      # Redis connection

# Environment management
use_node [version]        # Switch Node.js version (fnm/nvm)
use_python [version]      # Switch Python version (pyenv)
show_env                  # Show all development tools

# Process monitoring
port_check <port>         # Check what's using a port
process_monitor <name>    # Monitor specific process
psg <pattern>            # ps aux | grep pattern
```

### Productivity Helpers
```bash
# Quick notes and bookmarks
note [name]              # Create/edit notes with FZF
bookmark [name]          # Bookmark current directory
weather                  # Current weather
cheat <topic>           # Quick cheat sheets

# File operations
extract <file>           # Smart extraction for any archive
backup_file <file>       # Timestamped backup
disk_usage_top [dir]     # Top 20 largest directories
```

## 🔧 Advanced Features

### Project Templates

The system includes templates for:
- **Node.js/TypeScript**: Full setup with tsx, eslint, prettier
- **React**: Create React App with TypeScript
- **Next.js**: Next.js with TypeScript and Tailwind
- **Express**: Node.js API server with TypeScript
- **Python**: Poetry project with dev tools
- **Flask**: Python web framework
- **FastAPI**: Modern Python API framework  
- **Rust**: Cargo project
- **Go**: Go module project
- **Vue**: Vue 3 with TypeScript

### Docker Services

Pre-configured Docker Compose files for:
- PostgreSQL with development user
- Redis for caching
- MongoDB with authentication
- All services optimized for development

### Shell Enhancements

Your shell now includes:
- **200+ new aliases** for common development tasks
- **50+ advanced functions** for complex workflows
- **FZF integration** for fuzzy searching everything
- **Git integration** showing repository status
- **Smart cd** with zoxide for frecency-based navigation

### Monitoring & Optimization

- **Real-time performance monitoring**
- **Development process tracking**
- **Port and service management**
- **Disk usage analysis**
- **Network monitoring**
- **System health checks**
- **Performance benchmarking**

## 📚 Key Productivity Principles

### 1. Command Line Mastery
- Everything accessible via keyboard
- FZF for instant fuzzy searching
- Intelligent aliases for common tasks
- Process monitoring and management

### 2. Project Organization
- Standardized project structure
- Template-based project creation
- Automatic dependency management
- Git integration everywhere

### 3. Development Workflow
- Fast environment switching
- Container-based development
- Automated testing and building
- Performance monitoring

### 4. System Optimization
- Resource monitoring
- Cleanup automation
- Performance benchmarking
- Health checks

## 🎨 Customization

### Adding Custom Aliases
Edit `~/sync/src/dotfiles/config/zsh/aliases-enhanced`:
```bash
# Your custom aliases
alias myalias='my command'
```

### Adding Custom Functions
Edit `~/sync/src/dotfiles/config/zsh/functions-advanced`:
```bash
# Your custom functions
my_function() {
    echo "Custom function"
}
```

### Project Templates
Add templates in `~/Documents/templates/`:
```
templates/
├── my-custom-template/
│   ├── package.json
│   ├── src/
│   └── README.md
```

## 🚀 Recommended Additional Tools

### Install with your package manager:

```bash
# Modern CLI tools
yay -S lazygit lazydocker bottom dust tokei hyperfine tealdeer

# Development languages
yay -S nodejs npm python python-pip rust go

# Database tools  
yay -S postgresql redis mongodb

# Container tools
yay -S docker docker-compose

# Monitoring tools
yay -S htop iotop nethogs

# Text processing
yay -S jq yq ripgrep fd bat eza fzf
```

### Node.js ecosystem:
```bash
# Global utilities
npm install -g pnpm yarn tsx nodemon pm2

# Development tools
npm install -g eslint prettier typescript

# Useful CLIs
npm install -g serve http-server json-server
```

### Python ecosystem:
```bash
# Package managers
pip install poetry pipx

# Development tools  
pipx install black flake8 mypy pytest ipython jupyter

# Useful tools
pipx install httpie tldr rich-cli
```

## 🎯 Performance Tips

### 1. Terminal Performance
- Use Alacritty (GPU-accelerated)
- Configure tmux with 256 colors
- Use Starship prompt (fast Rust-based)

### 2. Editor Performance
- Neovim with lazy loading plugins
- Use LSP for intelligent code completion
- Configure for specific languages

### 3. System Performance
- Monitor with `dev-monitor status`
- Clean Docker regularly: `dclean`
- Monitor disk usage: `dev-monitor disk`
- Optimize git repositories: `git gc`

### 4. Development Workflow
- Use project templates for consistency
- Leverage Docker for environment isolation
- Automate repetitive tasks with scripts
- Monitor system resources during development

## 🔍 Troubleshooting

### Common Issues

**Slow shell startup:**
```bash
# Profile shell loading
zsh -xvs < /dev/null
```

**High memory usage:**
```bash
# Check development processes
dev-monitor processes
dev-monitor memory
```

**Docker issues:**
```bash
# Clean up Docker
dclean
docker system df
```

**Git performance:**
```bash
# Optimize git repositories
find ~/projects ~/repos -name ".git" -type d -exec git -C {}/../ gc \;
```

## 📈 Measuring Your 10x Impact

Track your productivity improvements:

1. **Speed Metrics**:
   - Project setup time (should be < 2 minutes)
   - Build times
   - Test execution time
   - Deploy time

2. **Workflow Metrics**:
   - Commands per task (fewer is better)
   - Context switches per hour
   - Time to find files/code
   - Git operations speed

3. **Quality Metrics**:
   - Fewer bugs due to better tooling
   - Consistent code formatting
   - Better test coverage
   - Faster code reviews

## 🎊 Next Steps

1. **Customize** the setup to your specific needs
2. **Practice** the new commands until they become muscle memory  
3. **Expand** with language-specific tools for your primary stack
4. **Share** improvements back to your dotfiles repository
5. **Monitor** your productivity gains with the built-in tools

Remember: The goal isn't just to have more tools, but to have a **seamless, efficient workflow** that gets out of your way and lets you focus on building amazing software!

---

*Happy coding! 🚀*