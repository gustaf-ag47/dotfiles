#!/usr/bin/env python3
"""
Neovim Keybinding Scanner
Scans a Neovim configuration directory and extracts all keybindings.
Supports modular configurations and generates documentation.
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class Keybinding:
    mode: str
    key: str
    command: str
    desc: str
    file: str
    line: int
    module: str
    pattern: str = ""


class KeybindingScanner:
    """Scans Neovim configuration for keybindings."""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        
        # Patterns to match different keymap styles
        self.patterns = {
            # vim.keymap.set('n', '<leader>ff', '<cmd>Telescope find_files<cr>', { desc = 'Find files' })
            'standard': re.compile(
                r"vim\.keymap\.set\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?([^'\"]*)['\"]?\s*,\s*{[^}]*desc\s*=\s*['\"]([^'\"]*)['\"]"
            ),
            
            # map('n', '<leader>ff', '<cmd>cmd<cr>', { desc = 'description' })
            'local_map': re.compile(
                r"map\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]?([^'\"]*)['\"]?\s*,\s*[^}]*desc\s*=\s*['\"]([^'\"]*)['\"]"
            ),
            
            # vim.keymap.set('n', '<leader>ff', '<cmd>cmd<cr>')
            'simple': re.compile(
                r"vim\.keymap\.set\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]"
            ),
            
            # keymap.set calls
            'keymap_set': re.compile(
                r"keymap\.set\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*[^,]*,\s*[^}]*desc\s*=\s*['\"]([^'\"]*)['\"]"
            ),
        }
        
        # Directories to scan in priority order
        self.scan_dirs = [
            'lua/core',
            'lua/features',
            'lua/lang',
            'lua/plugins',
            'lua/utils',
            'lua',  # fallback
        ]
    
    def detect_module(self, file_path: str) -> str:
        """Detect module type from file path."""
        rel_path = os.path.relpath(file_path, self.config_path)
        
        if '/core/' in rel_path:
            return 'core'
        elif '/features/' in rel_path:
            return 'features'
        elif '/lang/' in rel_path:
            lang_match = re.search(r'/lang/([^/]+)\.lua$', rel_path)
            return f'lang:{lang_match.group(1)}' if lang_match else 'lang:unknown'
        elif '/plugins/' in rel_path:
            return 'plugins'
        elif '/utils/' in rel_path:
            return 'utils'
        else:
            return 'other'
    
    def extract_from_line(self, line: str, file_path: str, line_number: int) -> List[Keybinding]:
        """Extract keybindings from a single line."""
        keybindings = []
        
        # Try each pattern
        for pattern_name, pattern in self.patterns.items():
            matches = pattern.findall(line)
            for match in matches:
                if pattern_name in ['standard', 'local_map']:
                    mode, key, command, desc = match
                elif pattern_name == 'keymap_set':
                    mode, key, desc = match
                    command = '(function)'
                else:  # simple
                    mode, key, command = match
                    desc = ''
                
                keybinding = Keybinding(
                    mode=mode,
                    key=key,
                    command=command,
                    desc=desc,
                    file=file_path,
                    line=line_number,
                    module=self.detect_module(file_path),
                    pattern=pattern_name
                )
                keybindings.append(keybinding)
        
        # Handle complex cases
        if 'vim.keymap.set' in line and not keybindings:
            mode_match = re.search(r"vim\.keymap\.set\s*\(\s*['\"]([^'\"]+)['\"]", line)
            key_match = re.search(r"vim\.keymap\.set\s*\([^,]+,\s*['\"]([^'\"]+)['\"]", line)
            
            if mode_match and key_match:
                desc_match = re.search(r"desc\s*=\s*['\"]([^'\"]*)['\"]", line)
                comment_match = re.search(r"--\s*(.*)", line)
                
                desc = ''
                if desc_match:
                    desc = desc_match.group(1)
                elif comment_match:
                    desc = comment_match.group(1).strip()
                
                keybinding = Keybinding(
                    mode=mode_match.group(1),
                    key=key_match.group(1),
                    command='(complex)',
                    desc=desc,
                    file=file_path,
                    line=line_number,
                    module=self.detect_module(file_path),
                    pattern='complex'
                )
                keybindings.append(keybinding)
        
        return keybindings
    
    def scan_file(self, file_path: str) -> List[Keybinding]:
        """Scan a single file for keybindings."""
        keybindings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                for line_number, line in enumerate(file, 1):
                    extracted = self.extract_from_line(line, file_path, line_number)
                    keybindings.extend(extracted)
        except (UnicodeDecodeError, IOError) as e:
            print(f"Warning: Could not read {file_path}: {e}")
        
        return keybindings
    
    def get_lua_files(self, directory: Path) -> List[str]:
        """Get all Lua files in a directory recursively."""
        files = []
        if directory.exists():
            for file_path in directory.rglob('*.lua'):
                files.append(str(file_path))
        return files
    
    def scan_config(self) -> List[Keybinding]:
        """Scan entire configuration for keybindings."""
        all_keybindings = []
        
        print(f"Scanning Neovim configuration at: {self.config_path}")
        
        for scan_dir in self.scan_dirs:
            full_path = self.config_path / scan_dir
            if not full_path.exists():
                continue
                
            files = self.get_lua_files(full_path)
            print(f"Scanning {scan_dir} ({len(files)} files)")
            
            for file_path in files:
                keybindings = self.scan_file(file_path)
                all_keybindings.extend(keybindings)
        
        return all_keybindings
    
    def group_keybindings(self, keybindings: List[Keybinding]) -> Dict[str, Any]:
        """Group keybindings by various criteria."""
        grouped = {
            'by_module': {},
            'by_mode': {},
            'by_leader': {},
            'global': [],
            'language_specific': [],
        }
        
        for kb in keybindings:
            # By module
            if kb.module not in grouped['by_module']:
                grouped['by_module'][kb.module] = []
            grouped['by_module'][kb.module].append(kb)
            
            # By mode
            if kb.mode not in grouped['by_mode']:
                grouped['by_mode'][kb.mode] = []
            grouped['by_mode'][kb.mode].append(kb)
            
            # By leader key usage
            if '<leader>' in kb.key:
                suffix = kb.key.replace('<leader>', '')
                if suffix not in grouped['by_leader']:
                    grouped['by_leader'][suffix] = []
                grouped['by_leader'][suffix].append(kb)
            
            # Global vs language-specific
            if kb.module.startswith('lang:'):
                grouped['language_specific'].append(kb)
            else:
                grouped['global'].append(kb)
        
        return grouped
    
    def generate_markdown(self, keybindings: List[Keybinding], grouped: Dict[str, Any]) -> str:
        """Generate markdown documentation."""
        lines = [
            '# Neovim Keybinding Reference',
            '',
            'Auto-generated from configuration scan.',
            '',
            '## Summary',
            '',
            f'- **Total keybindings**: {len(keybindings)}',
            f'- **Global keybindings**: {len(grouped["global"])}',
            f'- **Language-specific keybindings**: {len(grouped["language_specific"])}',
            '',
        ]
        
        # Global keybindings
        lines.extend([
            '## Global Keybindings',
            '',
            '| Mode | Key | Command | Description | Module | File |',
            '|------|-----|---------|-------------|--------|------|',
        ])
        
        for kb in grouped['global']:
            file_name = os.path.basename(kb.file)
            lines.append(f'| `{kb.mode}` | `{kb.key}` | `{kb.command}` | {kb.desc} | {kb.module} | {file_name}:{kb.line} |')
        
        # Language-specific keybindings
        languages = {}
        for kb in grouped['language_specific']:
            if kb.module.startswith('lang:'):
                lang = kb.module[5:]  # Remove 'lang:' prefix
                if lang not in languages:
                    languages[lang] = []
                languages[lang].append(kb)
        
        for lang, kbs in sorted(languages.items()):
            lines.extend([
                '',
                f'## {lang.upper()} Keybindings',
                '',
                '| Mode | Key | Command | Description |',
                '|------|-----|---------|-------------|',
            ])
            
            for kb in kbs:
                lines.append(f'| `{kb.mode}` | `{kb.key}` | `{kb.command}` | {kb.desc} |')
        
        # Leader key reference
        lines.extend([
            '',
            '## Leader Key Reference',
            '',
            '| Suffix | Key | Description | Module |',
            '|--------|-----|-------------|--------|',
        ])
        
        for suffix in sorted(grouped['by_leader'].keys()):
            kbs = grouped['by_leader'][suffix]
            if kbs:
                kb = kbs[0]  # Take first occurrence
                lines.append(f'| `{suffix}` | `<leader>{suffix}` | {kb.desc} | {kb.module} |')
        
        return '\n'.join(lines)
    
    def generate_json(self, keybindings: List[Keybinding], grouped: Dict[str, Any]) -> str:
        """Generate JSON documentation."""
        # Convert dataclasses to dicts
        keybindings_dict = [asdict(kb) for kb in keybindings]
        
        # Convert grouped data
        grouped_dict = {}
        for key, value in grouped.items():
            if isinstance(value, list):
                grouped_dict[key] = [asdict(kb) for kb in value]
            elif isinstance(value, dict):
                grouped_dict[key] = {}
                for k, v in value.items():
                    grouped_dict[key][k] = [asdict(kb) for kb in v]
        
        data = {
            'summary': {
                'total': len(keybindings),
                'global': len(grouped['global']),
                'language_specific': len(grouped['language_specific']),
                'generated_at': __import__('datetime').datetime.now().isoformat(),
            },
            'keybindings': keybindings_dict,
            'grouped': grouped_dict,
        }
        
        return json.dumps(data, indent=2)


def main():
    parser = argparse.ArgumentParser(description='Scan Neovim configuration for keybindings')
    parser.add_argument('config_path', nargs='?', 
                       default=os.path.expanduser('~/.config/nvim'),
                       help='Path to Neovim configuration directory')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown',
                       help='Output format')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    # Initialize scanner
    scanner = KeybindingScanner(args.config_path)
    
    # Scan configuration
    keybindings = scanner.scan_config()
    grouped = scanner.group_keybindings(keybindings)
    
    if args.verbose:
        print(f"\nFound {len(keybindings)} keybindings:")
        for module, kbs in grouped['by_module'].items():
            print(f"  {module}: {len(kbs)} keybindings")
    
    # Generate output
    if args.format == 'markdown':
        content = scanner.generate_markdown(keybindings, grouped)
    else:  # json
        content = scanner.generate_json(keybindings, grouped)
    
    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(content)
        print(f"\nDocumentation written to: {args.output}")
    else:
        print(content)


if __name__ == '__main__':
    main()