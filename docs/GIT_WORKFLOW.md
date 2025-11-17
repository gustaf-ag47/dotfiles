# Git Workflow - Trunk-Based Development

This document outlines the standardized Git workflow for the dotfiles repository, implementing trunk-based development with automated enforcement.

## 🌿 Branching Strategy

### Master Branch
- **Single source of truth** - All development branches from `master`
- **Always deployable** - Master should always be in a working state
- **Protected** - Direct pushes discouraged, prefer PR workflow
- **Up-to-date** - Sync frequently with `git sync`

### Feature Branches
Short-lived branches (1-3 days max) for focused development:

```bash
# Branch naming convention: <type>/<description>-<date>
feature/add-dark-mode-20250623
fix/resolve-clipboard-issue-20250623
hotfix/critical-security-patch-20250623
refactor/simplify-config-loading-20250623
experiment/test-new-ui-framework-20250623
```

## 🚀 Quick Start Commands

### Creating a New Branch
```bash
# Automated branch creation with validation
git nb feature add-dark-mode
git nb fix resolve-clipboard-issue
git nb hotfix critical-security-patch

# Manual equivalent
git new-branch feature add-dark-mode
```

### Daily Workflow
```bash
# 1. Start of day - sync with master
git sync

# 2. Create feature branch
git nb feature your-feature-name

# 3. Make changes and commit (uses template)
git add .
git commit  # Opens template editor

# 4. Quick commits with conventional format
git feat "add user authentication"
git fix "resolve button alignment issue"
git docs "update installation guide"

# 5. Push branch
git push -u origin HEAD

# 6. Before merging - rebase on master
git sync
git rebase master
git pushf  # Force push with lease (safe)

# 7. Clean up after merge
git clean  # Interactive cleanup tool
```

## 📝 Commit Message Standards

### Conventional Commits Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: New features
- **fix**: Bug fixes  
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code restructuring without feature changes
- **test**: Adding or updating tests
- **chore**: Tooling, dependencies, maintenance
- **perf**: Performance improvements
- **build**: Build system changes
- **ci**: CI/CD pipeline changes

### Examples
```bash
feat(auth): add OAuth2 integration
fix(ui): resolve button alignment on mobile devices
docs: update installation instructions for new users
refactor(parser): simplify tokenization logic
test(utils): add unit tests for date helper functions
chore(deps): update dependencies to latest versions
```

### Quick Commit Aliases
```bash
git feat "add OAuth2 integration"
git fix "resolve button alignment issue"  
git docs "update installation guide"
git refactor "simplify config loading"
git test "add unit tests for utilities"
git chore "update dependencies"
```

## 🔧 Automated Enforcement

### Pre-commit Hooks
Automatically run on every commit:
- ✅ Syntax validation (shell scripts, Lua files)
- ✅ Merge conflict marker detection
- ✅ Large file detection (>1MB warning)
- ✅ Secret/sensitive data detection
- ✅ Code quality checks

### Commit Message Validation
Automatically enforces:
- ✅ Conventional commit format
- ✅ Subject line length (≤50 characters)
- ✅ Proper capitalization (lowercase start)
- ✅ No period at end of subject
- ✅ Valid commit types

### Branch Name Validation
Automated through `git-new-branch`:
- ✅ Standardized naming convention
- ✅ Type validation
- ✅ Automatic sanitization
- ✅ Timestamp for uniqueness

## 🛠️ Git Aliases Reference

### Workflow Commands
```bash
git sync          # Checkout master + pull origin
git nb <type> <desc>  # Create new standardized branch
git clean         # Interactive branch cleanup

git co <branch>   # Checkout branch
git br            # List branches with info
git st            # Short status
```

### Commit & Push
```bash
git cm "message"  # Commit with message
git ca            # Amend last commit
git pushf         # Safe force push (--force-with-lease)

git rim           # Interactive rebase on master
git ahead         # Show commits not in master
```

### Quick Commits
```bash
git feat "message"     # feat: message
git fix "message"      # fix: message
git docs "message"     # docs: message
git style "message"    # style: message
git refactor "message" # refactor: message
git test "message"     # test: message
git chore "message"    # chore: message
```

## 📋 Best Practices

### Branch Lifecycle
1. **Create** from latest master (`git sync` first)
2. **Work** in small, focused commits
3. **Commit** frequently with descriptive messages
4. **Rebase** on master before merging
5. **Merge** via PR with squash/rebase
6. **Delete** branch after merge

### Commit Guidelines
- **Small & Focused**: One logical change per commit
- **Descriptive**: Explain what and why, not how
- **Present Tense**: "add feature" not "added feature"
- **Imperative**: "fix bug" not "fixes bug"
- **Reference Issues**: Include issue numbers when relevant

### Common Patterns
```bash
# Start new feature
git sync
git nb feature add-user-profiles

# Work on feature
git add .
git feat "add user profile creation"
git add .
git feat "add profile editing interface"
git add .
git test "add profile validation tests"

# Prepare for merge
git sync
git rebase master
git pushf

# After PR merged
git sync
git clean
```

## 🔍 Troubleshooting

### Commit Message Rejected
```bash
# Error: Invalid commit message format
# Fix: Use conventional commit format
git commit -m "feat: add new feature"

# Or use quick aliases
git feat "add new feature"
```

### Pre-commit Hook Failures
```bash
# Shell script syntax error
bash -n problematic-script.sh  # Test manually

# Large files detected
git reset HEAD large-file.bin  # Unstage large file
```

### Branch Cleanup
```bash
# Clean up merged and orphaned branches
git clean

# Manual cleanup
git branch -d merged-branch-name
git branch -D force-delete-branch-name
```

### Rebase Conflicts
```bash
git rebase master
# Fix conflicts in files
git add resolved-files
git rebase --continue

# Or abort and try merge
git rebase --abort
git merge master
```

## 📊 Workflow Summary

This trunk-based development approach provides:

- **🚀 Fast Integration**: Short-lived branches reduce merge conflicts
- **🔄 Continuous Sync**: Regular master updates keep branches current  
- **🤖 Automated Quality**: Hooks and validation prevent common issues
- **📝 Consistent History**: Conventional commits improve readability
- **🧹 Clean Repository**: Automated cleanup removes stale branches
- **🔧 Developer Experience**: Aliases and tools streamline common tasks

The workflow balances flexibility with consistency, enabling productive development while maintaining high code quality standards.