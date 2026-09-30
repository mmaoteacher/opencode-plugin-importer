#!/usr/bin/env python3
"""Import skills, Markdown agents and MCP configuration into OpenCode."""
from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

try:
    import yaml
except ImportError:
    sys.exit('Missing PyYAML. Install scripts/requirements.txt in a Python virtual environment first.')

VERSION = '0.1.0'
STATE = '.plugin-importer/manifest.json'
MANIFESTS = ('plugin.json', '.claude-plugin/plugin.json', '.codex-plugin/plugin.json', '.agy-plugin/plugin.json')
PREFIXES = ('', '.claude', '.codex', '.opencode', '.agents')
ROOT_VARS = ('${CLAUDE_PLUGIN_ROOT}', '${CODEX_PLUGIN_ROOT}', '${PLUGIN_ROOT}')
KINDS = {'skills', 'agents', 'mcp'}
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules'}


class ImportErrorDetail(ValueError):
    pass


def fail(message):
    raise ImportErrorDetail(message)


def warn(message):
    print(f'Warning: {message}', file=sys.stderr)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def normalize_name(value):
    """Coerce an arbitrary label into a legal name; empty results are rejected."""
    fixed = re.sub(r'[^a-z0-9]+', '-', str(value).lower()).strip('-')[:64].strip('-')
    if not fixed:
        fail(f'Cannot derive a valid name from {value!r}; use lowercase words separated by single hyphens.')
    return fixed


def valid_name(value, fix=False):
    if not isinstance(value, str) or len(value) > 64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value):
        if not fix:
            fail(f'Invalid name {value!r}; use lowercase words separated by single hyphens (max 64 characters).')
        fixed = normalize_name(value)
        warn(f'Renamed {value!r} to {fixed!r}.')
        return fixed
    return value


def jsonc(text):
    """Strip comments/trailing commas outside strings; let json reject malformed input."""
    token = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/')
    clean = token.sub(lambda m: m[0] if m[0].startswith('"') else re.sub(r'[^\n]', ' ', m[0]), text)
    clean = re.sub(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])',
                   lambda m: m[0] if m[0].startswith('"') else m[1], clean)
    result = json.loads(clean)
    if not isinstance(result, dict):
        fail('Configuration must be a JSON object.')
    return result


def read_json(path):
    try:
        return jsonc(path.read_text())
    except (ValueError, OSError) as exc:
        fail(f'Cannot read {path}: {exc}')


def inside(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        fail(f'Path must stay within the plugin: {relative}')
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'External symlink/path is unsupported: {path}')
    return path


def check_tree(root):
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in dirs + files:
            path = Path(parent) / name
            if path.is_symlink():
                if not path.exists() or not path.resolve().is_relative_to(root.resolve()):
                    fail(f'Broken or external symlink: {path}')
                # Directory links can hide cycles or expose the same skill twice.
                if path.is_dir():
                    fail(f'Directory symlinks are unsupported; import an unconfigured source: {path}')
            elif not (path.is_dir() or path.is_file()):
                fail(f'Unsupported special file: {path}')


def tree_hash(root):
    result = hashlib.sha256()
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(dirs + files):
            path = Path(parent) / name
            result.update(str(path.relative_to(root)).encode() + b'\0')
            if path.is_symlink():
                result.update(b'L' + os.readlink(path).encode() + b'\0')
            elif path.is_file():
                result.update(b'F' + str(stat.S_IMODE(path.stat().st_mode)).encode() + b'\0')
                result.update(hashlib.sha256(path.read_bytes()).digest())
            else:
                result.update(b'D')
    return result.hexdigest()


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            fail(f'Duplicate YAML field: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def markdown(path):
    text = path.read_text()
    match = re.match(r'\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)', text, re.S)
    if not match:
        fail(f'Missing YAML frontmatter: {path}')
    try:
        metadata = yaml.load(match[1], Loader=UniqueLoader)
    except yaml.YAMLError as exc:
        fail(f'Invalid YAML in {path}: {exc}')
    if not isinstance(metadata, dict):
        fail(f'Frontmatter must be a mapping: {path}')
    description = metadata.get('description')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        fail(f'Missing description: {path}')
    return metadata, text[match.end():]


def write_markdown(path, metadata, body):
    path.write_text('---\n' + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True) + '---\n' + body)


def git(args, cwd=None):
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        fail(f'Git operation failed ({args[0]}). Check repository access and ref; no destination files changed.')
    return result.stdout.strip()


@contextlib.contextmanager
def source_tree(source, ref):
    local = Path(source).expanduser()
    if local.is_dir() and not ref:
        root = local.resolve()
        revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        yield root, str(root), revision.stdout.strip() if revision.returncode == 0 else None
        return
    if source.startswith('-'):
        fail('Invalid source.')
    if '://' in source and urlsplit(source).scheme in {'http', 'https'} and urlsplit(source).username:
        fail('Do not embed credentials in the repository URL; use Git credential helpers or SSH.')
    with tempfile.TemporaryDirectory(prefix='opencode-import-source-') as temporary:
        root = Path(temporary) / 'repo'
        locator = str(local.resolve()) if local.is_dir() else source
        git(['clone', '--quiet', '--no-hardlinks', '--', locator, str(root)])
        if ref:
            if ref.startswith('-'):
                fail('Invalid Git ref.')
            # Explicit fetch also accepts tags and commit SHAs, without touching the original checkout.
            git(['fetch', '--quiet', 'origin', ref], root)
            git(['checkout', '--quiet', '--detach', 'FETCH_HEAD'], root)
        yield root, locator, git(['rev-parse', 'HEAD'], root)


def discover(repo, fallback_name=None, fix=False):
    candidates = {repo}
    if (repo / 'plugins').is_dir():
        candidates.update(p for p in (repo / 'plugins').iterdir() if p.is_dir())
    for market in ('.claude-plugin/marketplace.json', '.agents/plugins/marketplace.json'):
        if (repo / market).is_file():
            for item in read_json(repo / market).get('plugins', []):
                source = item.get('source')
                relative = source if isinstance(source, str) else source.get('path') if isinstance(source, dict) and source.get('source') == 'local' else None
                if relative:
                    candidates.add(inside(repo, relative))
                else:
                    warn('Remote marketplace entries are not recursively downloaded; pass their repository directly.')
    found = {}
    for root in sorted(candidates):
        inside(repo, str(root.relative_to(repo)))
        if root.is_symlink():
            fail(f'Directory symlinks are unsupported: {root}')
        manifests = [read_json(inside(root, name)) for name in MANIFESTS if (root / name).is_file()]
        has_components = any((root / prefix / kind).is_dir() for prefix in PREFIXES for kind in ('skills', 'agents'))
        has_components |= any((root / name).is_file() for name in ('.mcp.json', 'mcp_config.json', 'opencode.json', 'opencode.jsonc'))
        if not manifests and not has_components:
            continue
        names = {m['name'] for m in manifests if 'name' in m}
        if len(names) > 1:
            fail(f'Conflicting plugin names in {root}')
        name = valid_name(next(iter(names)) if names else re.sub(r'[^a-z0-9]+', '-', (fallback_name if root == repo and fallback_name else root.name).lower()).strip('-'), fix)
        if name in found and found[name][0].resolve() != root.resolve():
            fail(f'Duplicate plugin name: {name}')
        found[name] = (root, manifests)
    return found


def entries(root, manifests, kind, fix=False):
    paths = [root / prefix / kind for prefix in PREFIXES]
    for meta in manifests:
        custom = meta.get(kind, [])
        for value in ([custom] if isinstance(custom, str) else custom):
            paths.append(inside(root, value))
    found = {}
    seen = set()
    for path in paths:
        if not path.exists():
            continue
        files = ([path] if path.is_file() else [path / 'SKILL.md']
                 if kind == 'skills' and (path / 'SKILL.md').is_file()
                 else sorted(path.glob('*/SKILL.md' if kind == 'skills' else '*.md')))
        for file in files:
            inside(root, str(file.relative_to(root)))
            if file.resolve() in seen:
                continue
            seen.add(file.resolve())
            meta, body = markdown(file)
            name = valid_name(meta.get('name', file.parent.name if kind == 'skills' else file.stem), fix)
            if name in found:
                fail(f'Duplicate {kind} name: {name}')
            found[name] = (file.relative_to(root), meta, body)
    return found


def mcp_entries(root, manifests, fix=False):
    sources = []
    for prefix in PREFIXES:
        for name in ('.mcp.json', 'mcp_config.json', 'opencode.json', 'opencode.jsonc'):
            path = root / prefix / name
            if path.is_file():
                sources.append(read_json(inside(root, str(path.relative_to(root)))))
    for path in (root / '.codex/config.toml',):
        if path.is_file():
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            sources.append(tomllib.loads(inside(root, str(path.relative_to(root))).read_text()))
    for meta in manifests:
        declaration = meta.get('mcpServers')
        if isinstance(declaration, dict):
            sources.append({'mcpServers': declaration})
        elif isinstance(declaration, str):
            sources.append(read_json(inside(root, declaration)))
    result = {}
    for data in sources:
        servers = data.get('mcpServers', data.get('mcp_servers', data.get('mcp', {})))
        if not isinstance(servers, dict):
            fail('MCP servers must be a mapping.')
        for name, value in servers.items():
            name = valid_name(name, fix)
            if name in result and result[name] != value:
                if mcp_convert(result[name], root, root) != mcp_convert(value, root, root):
                    fail(f'Conflicting MCP definitions: {name}')
            result[name] = value
    return result


def root_tokens(value, installed):
    for token in ROOT_VARS:
        value = value.replace(token, str(installed))
    return value


def mcp_convert(config, root, installed):
    if not isinstance(config, dict):
        fail('MCP entry must be an object.')
    allowed = {'type', 'command', 'args', 'env', 'environment', 'url', 'serverUrl', 'headers',
               'http_headers', 'bearer_token_env_var', 'enabled', 'disabled', 'timeout', 'oauth'}
    unknown = set(config) - allowed
    if unknown:
        fail(f'Unsupported MCP fields: {", ".join(sorted(unknown))}')
    config = copy.deepcopy(config)
    for a, b in [('url', 'serverUrl'), ('env', 'environment'), ('headers', 'http_headers')]:
        if a in config and b in config and config[a] != config[b]:
            fail(f'Conflicting MCP fields: {a} and {b}')

    def strings(value):
        if isinstance(value, str):
            value = root_tokens(value, installed)
            value = re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}', r'{env:\1}', value)
            if '${' in value:
                fail('Unsupported MCP variable expression; only ${NAME} and plugin-root variables are supported.')
            return value
        if isinstance(value, list):
            return [strings(v) for v in value]
        if isinstance(value, dict):
            return {k: strings(v) for k, v in value.items()}
        return value

    config = strings(config)
    result = {}
    if 'enabled' in config and 'disabled' in config:
        fail('Use enabled or disabled, not both.')
    enabled = config.get('enabled', not config.get('disabled', False))
    if not isinstance(enabled, bool) or ('disabled' in config and not isinstance(config['disabled'], bool)):
        fail('MCP enabled/disabled must be boolean.')
    result['enabled'] = enabled
    if not enabled and set(config) <= {'enabled', 'disabled'}:
        return result
    url = config.get('url', config.get('serverUrl'))
    if url is not None:
        if config.get('type') not in (None, 'remote', 'http', 'sse') or 'command' in config:
            fail('Ambiguous remote MCP transport.')
        if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            fail('Remote MCP URL must use http or https.')
        result.update(type='remote', url=url)
        headers = config.get('headers', config.get('http_headers', {}))
        if not isinstance(headers, dict) or not all(isinstance(v, str) for v in headers.values()):
            fail('MCP headers must map names to strings.')
        if config.get('bearer_token_env_var'):
            token = config['bearer_token_env_var']
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', token):
                fail('Invalid bearer_token_env_var.')
            if 'Authorization' in headers:
                fail('Conflicting Authorization header.')
            headers['Authorization'] = 'Bearer {env:' + token + '}'
        if headers:
            result['headers'] = headers
        if 'oauth' in config:
            oauth = config['oauth']
            if oauth is not False and (not isinstance(oauth, dict) or set(oauth) - {'clientId', 'clientSecret', 'scope'}):
                fail('Unsupported OAuth configuration.')
            result['oauth'] = oauth
        if any(k in config for k in ('args', 'env', 'environment')):
            fail('Remote MCP cannot have local process options.')
    else:
        if config.get('type') not in (None, 'stdio', 'command', 'local'):
            fail('Unsupported local MCP transport.')
        command = config.get('command')
        command = [command] if isinstance(command, str) else command
        arguments = config.get('args', [])
        if not isinstance(command, list) or not command or not isinstance(arguments, list):
            fail('Local MCP requires command and an optional args array.')
        command = command + arguments
        if not all(isinstance(v, str) and v for v in command):
            fail('MCP command elements must be non-empty strings.')
        for i, value in enumerate(command):
            if not value.startswith(('-', '/')) and (root / value).exists():
                command[i] = str(installed / inside(root, value).relative_to(root))
        result.update(type='local', command=command)
        environment = config.get('environment', config.get('env', {}))
        if not isinstance(environment, dict) or not all(isinstance(v, str) for v in environment.values()):
            fail('MCP environment must map names to strings.')
        if environment:
            result['environment'] = environment
        if any(k in config for k in ('headers', 'http_headers', 'oauth', 'bearer_token_env_var')):
            fail('Local MCP cannot have remote authentication options.')
    if 'timeout' in config:
        if type(config['timeout']) is not int or config['timeout'] <= 0:
            fail('MCP timeout must be a positive number of milliseconds.')
        result['timeout'] = config['timeout']
    return result


TOOLS = {'Read': 'read', 'Write': 'edit', 'Edit': 'edit', 'MultiEdit': 'edit', 'Bash': 'bash',
         'Glob': 'glob', 'Grep': 'grep', 'LS': 'list', 'WebFetch': 'webfetch', 'WebSearch': 'websearch',
         'Task': 'task', 'Agent': 'task', 'Skill': 'skill', 'TodoWrite': 'todowrite', 'TodoRead': 'todoread'}


def agent_convert(meta):
    meta = copy.deepcopy(meta)
    if any(k in meta for k in ('permissionMode', 'hooks', 'mcpServers', 'skills', 'isolation')):
        fail('Agent has unsupported permissions/hooks/MCP/skills/isolation. Convert it explicitly before importing.')
    result = {k: v for k, v in meta.items() if k in {'description', 'mode', 'temperature', 'top_p', 'steps', 'hidden', 'color', 'disable', 'permission'}}
    result.setdefault('mode', 'subagent')
    if result['mode'] not in ('primary', 'subagent', 'all'):
        fail('Unsupported agent mode.')
    model = meta.get('model')
    if model and model != 'inherit':
        if isinstance(model, str) and '/' in model:
            result['model'] = model
        else:
            fail(f'Model alias {model!r} has no portable mapping; use provider/model or inherit.')
    permission = copy.deepcopy(result.get('permission', {}))
    if not isinstance(permission, dict):
        fail('Agent permission must be a mapping.')
    if 'tools' in meta:
        tools = meta['tools']
        if isinstance(tools, str):
            tools = [v.strip() for v in tools.split(',')]
        if isinstance(tools, list):
            permissions = {'*': 'deny'}
            for tool in tools:
                if tool not in TOOLS and tool not in TOOLS.values():
                    fail(f'Unknown agent tool: {tool}')
                permissions[TOOLS.get(tool, tool)] = 'allow'
        elif isinstance(tools, dict) and all(type(v) is bool for v in tools.values()):
            permissions = {TOOLS.get(k, k): 'allow' if v else 'deny' for k, v in tools.items()}
        else:
            fail('Agent tools must be a list, comma-separated string, or boolean mapping.')
        if permission:
            fail('Agent combines tools and permission; convert to a single permission map first.')
        permission = permissions
    denied = meta.get('disallowedTools', [])
    if isinstance(denied, str):
        denied = [v.strip() for v in denied.split(',')]
    for tool in denied:
        if tool not in TOOLS and tool not in TOOLS.values():
            fail(f'Unknown disallowed tool: {tool}')
        permission[TOOLS.get(tool, tool)] = 'deny'
    if permission:
        result['permission'] = permission
    dropped = set(meta) - set(result) - {'name', 'model', 'tools', 'disallowedTools'}
    if dropped:
        warn('Agent metadata not translated: ' + ', '.join(sorted(dropped)))
    return result


MIGRATION_LOG = []


def build_payload(root, manifests, namespace, destination, kinds, staging, fix=False, skip=False):
    MIGRATION_LOG.clear()
    check_tree(root)
    fingerprint = tree_hash(root)
    key = digest(encoded([VERSION, fingerprint, namespace, str(destination), sorted(kinds)]))[:24]
    snapshot = Path('.plugin-importer/sources') / namespace / key
    installed = destination / snapshot
    shutil.copytree(root, staging, symlinks=True,
                    ignore=shutil.ignore_patterns(*SKIP_DIRS))
    # Rebase absolute internal file links before editing any frontmatter.
    for parent, _, files in os.walk(staging):
        for name in files:
            file = Path(parent) / name
            if file.is_symlink():
                original = root / file.relative_to(staging)
                target = staging / original.resolve().relative_to(root.resolve())
                file.unlink()
                file.symlink_to(os.path.relpath(target, file.parent))
    desired = {}
    for kind in ('skills', 'agents'):
        if kind not in kinds:
            continue
        for name, (relative, meta, body) in entries(root, manifests, kind, fix).items():
            exported = valid_name(f'{namespace}-{name}')
            if kind == 'skills':
                if meta.get('disable-model-invocation') or meta.get('user-invocable') is False or meta.get('allowed-tools'):
                    message = f'Skill {name} uses invocation/tool restrictions OpenCode cannot preserve; adapt it explicitly.'
                    if not skip:
                        fail(message)
                    warn(f'Skipping skill {name}: {message}')
                    continue
                meta['name'] = exported
                export = f'skills/{exported}'
                linked = installed / relative.parent
            else:
                try:
                    meta = agent_convert(meta)
                except ImportErrorDetail as exc:
                    if not skip:
                        raise
                    warn(f'Skipping agent {name}: {exc}')
                    continue
                export = f'agents/{exported}.md'
                linked = installed / relative
            write_markdown(staging / relative, meta, root_tokens(body, installed))
            desired[export] = {'kind': kind, 'link': os.path.relpath(linked, (destination / export).parent)}
            MIGRATION_LOG.append((export, str(root / (relative.parent if kind == 'skills' else relative))))
    if 'mcp' in kinds:
        for name, config in mcp_entries(root, manifests, fix).items():
            exported = valid_name(f'{namespace}-{name}')
            try:
                value = mcp_convert(config, root, installed)
            except ImportErrorDetail as exc:
                if not skip:
                    raise
                warn(f'Skipping MCP server {name}: {exc}')
                continue
            desired[f'mcp/{exported}'] = {'kind': 'mcp', 'value': value}
            MIGRATION_LOG.append((f'mcp/{exported}', None))
    if any((root / path).exists() for path in ('hooks', 'hooks.json', 'commands')) or any('hooks' in m for m in manifests):
        warn('Hooks and slash-command definitions are not imported; only skills, Markdown agents and MCP are supported.')
    check_tree(staging)
    installed_hash = tree_hash(staging)
    for item in desired.values():
        item.update(snapshot=str(snapshot), snapshot_hash=installed_hash)
    return desired, fingerprint, snapshot


def shell_quote(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


def print_manual_script(desired, migration_log):
    """Print a reviewable copy script; the caller returns without touching the destination."""
    sources = dict(migration_log)
    print('#!/bin/sh')
    print('# Generated by install-plugin --manual-mode. Review before running.')
    print('# These copy the original source files; importer frontmatter conversion')
    print('# (renamed entries, resolved plugin-root variables) is NOT applied.')
    print('# Prefer a normal install when you need the converted resources.')
    print('set -eu')
    print('DEST="${1:-$HOME/.config/opencode}"')
    mcp_keys = []
    for export in sorted(desired):
        kind = desired[export]['kind']
        if kind == 'mcp':
            mcp_keys.append(export.split('/', 1)[1])
            continue
        source = sources.get(export)
        if not source:
            continue
        if kind == 'skills':
            print(f'mkdir -p "$DEST/{export}"')
            print(f'cp -R {shell_quote(source)}/. "$DEST/{export}/"')
        else:
            print(f'mkdir -p "$DEST/agents"')
            print(f'cp {shell_quote(source)} "$DEST/{export}"')
    if mcp_keys:
        print(f'# Merge these MCP servers into "$DEST"/opencode.jsonc under "mcp" manually:')
        for key in mcp_keys:
            print(f'#   {key}')


def destination_path(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        fail(f'Invalid managed path: {relative}')
    for parent in path.parents:
        if parent == root:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            fail(f'Unsafe destination parent: {parent}')
    return path


def state_read(root):
    path = destination_path(root, STATE)
    if path.is_symlink():
        fail('Manifest must not be a symlink.')
    if not path.exists():
        if (root / '.plugin-manifest.json').exists():
            fail('Legacy installer manifest found. Use a fresh --config-dir; legacy ownership is not assumed.')
        return {'version': 1, 'plugins': {}}
    data = read_json(path)
    if data.get('version') != 1 or not isinstance(data.get('plugins'), dict):
        fail('Unsupported importer manifest. Preserve it and use a fresh --config-dir.')
    return data


def config_read(root):
    names = [name for name in ('opencode.json', 'opencode.jsonc') if (root / name).exists() or (root / name).is_symlink()]
    if len(names) > 1:
        fail('Both opencode.json and opencode.jsonc exist; choose one before importing MCP.')
    name = names[0] if names else 'opencode.json'
    path = destination_path(root, name)
    if path.is_symlink():
        fail('OpenCode configuration must not be a symlink.')
    config = read_json(path) if path.exists() else {'$schema': 'https://opencode.ai/config.json'}
    if not isinstance(config.get('mcp', {}), dict):
        fail('OpenCode mcp must be an object.')
    return name, config


def check_owned(root, export, old, config, checked):
    if old:
        kind = old.get('kind')
        if kind not in KINDS or not export.startswith(kind + '/'):
            fail('Invalid ownership record.')
        valid_name(export.split('/', 1)[1].removesuffix('.md') if kind == 'agents' else export.split('/', 1)[1])
        snapshot = old.get('snapshot', '')
        if not snapshot.startswith('.plugin-importer/sources/'):
            fail('Invalid snapshot ownership record.')
        path = destination_path(root, snapshot)
        if path.is_symlink():
            fail(f'Modified snapshot link: {path}')
        if snapshot not in checked:
            if not path.is_dir() or tree_hash(path) != old.get('snapshot_hash'):
                fail(f'Local snapshot modified or missing: {path}. Preserve your changes before retrying.')
            checked.add(snapshot)
    if export.startswith('mcp/'):
        key = export[4:]
        current = config.get('mcp', {}).get(key)
        if current is not None and (not old or digest(encoded(current)) != old.get('value_hash')):
            fail(f'Unmanaged or locally modified MCP: {key}')
    else:
        path = destination_path(root, export)
        if path.exists() or path.is_symlink():
            if not old or not path.is_symlink() or os.readlink(path) != old.get('link'):
                fail(f'Unmanaged or locally modified export: {path}')


def make_plan(root, state, namespace, desired, kinds, mode, preview, ask=input):
    old_plugin = state['plugins'].get(namespace, {})
    old_items = old_plugin.get('items', {})
    if not isinstance(old_items, dict):
        fail('Invalid ownership record.')
    config_name, config = config_read(root) if 'mcp' in kinds else ('opencode.json', {})
    updated_config = copy.deepcopy(config)
    retained = copy.deepcopy(old_items)
    changes = []
    checked = set()
    selected = set(desired) | {k for k, v in old_items.items() if v.get('kind') in kinds}
    # Validate everything first, before prompts or writes.
    for export in sorted(selected):
        check_owned(root, export, old_items.get(export), config, checked)
    for export in sorted(selected):
        old = old_items.get(export)
        item = desired.get(export)
        if item is None and mode == 'sync':
            print(f'KEEP {export} (removed upstream)')
            continue
        if item is not None:
            record = {k: v for k, v in item.items() if k != 'value'}
            if item['kind'] == 'mcp':
                record['value_hash'] = digest(encoded(item['value']))
                present = export[4:] in config.get('mcp', {})
            else:
                present = (root / export).is_symlink()
            if record == old and present:
                continue
        elif old is None:
            continue
        action = 'REMOVE' if item is None else 'UPDATE' if old else 'ADD'
        print(f'{action} {export}')
        if mode == 'interactive' and not preview:
            try:
                accepted = ask(f'{action} {export}? [y/N] ').strip().lower() in ('y', 'yes')
            except EOFError:
                fail('Interactive input ended; nothing was written.')
            if not accepted:
                continue
        if item is None:
            retained.pop(export, None)
        else:
            retained[export] = record
        if export.startswith('mcp/'):
            servers = updated_config.setdefault('mcp', {})
            if item is None:
                servers.pop(export[4:], None)
            else:
                servers[export[4:]] = item['value']
        else:
            changes.append((export, None if item is None else ('link', item['link'])))
    if updated_config != config:
        original = root / config_name
        if original.exists():
            content = original.read_bytes()
            backup = '.plugin-importer/backups/' + digest(content) + original.suffix
            backup_path = destination_path(root, backup)
            if backup_path.is_symlink() or (backup_path.exists() and (not backup_path.is_file() or backup_path.read_bytes() != content)):
                fail('Configuration backup path is occupied by unrelated content.')
            if not backup_path.exists():
                changes.append((backup, ('bytes', content)))
        changes.append((config_name, ('bytes', encoded(updated_config))))
    return retained, changes


def apply_transaction(root, changes):
    """Rollback catchable failures, including KeyboardInterrupt; no crash-atomicity claim."""
    ancestor = root
    while not ancestor.exists():
        ancestor = ancestor.parent
    created = []
    completed = []

    def parents(path):
        missing = []
        while not path.exists():
            missing.append(path)
            path = path.parent
        for directory in reversed(missing):
            directory.mkdir()
            created.append(directory)

    with tempfile.TemporaryDirectory(prefix='.opencode-import-transaction-', dir=ancestor) as temp:
        transaction = Path(temp)
        # Stage every new value before touching managed paths.
        staged = []
        for index, (relative, content) in enumerate(changes):
            target = destination_path(root, relative)
            path = transaction / f'new-{index}'
            if content:
                kind, value = content
                if kind == 'tree':
                    shutil.copytree(value, path, symlinks=True)
                elif kind == 'link':
                    path.symlink_to(value)
                else:
                    path.write_bytes(value)
                    path.chmod(0o600)
            staged.append((target, path if content else None))
        try:
            for index, (target, new) in enumerate(staged):
                parents(target.parent)
                backup = transaction / f'old-{index}'
                existed = target.exists() or target.is_symlink()
                if existed:
                    os.replace(target, backup)
                completed.append((target, backup if existed else None))
                if new:
                    os.replace(new, target)
        except BaseException:
            for target, backup in reversed(completed):
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.is_dir():
                    shutil.rmtree(target)
                if backup:
                    os.replace(backup, target)
            for directory in reversed(created):
                directory.rmdir()
            raise


@contextlib.contextmanager
def install_lock(root, preview):
    if preview:
        yield
        return
    lock = Path(tempfile.gettempdir()) / ('opencode-importer-' + digest(str(root).encode()) + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def install(root, source, ref, selected_plugin, namespace, kinds, mode='sync', preview=False, listing=False, ask=input,
            fix=False, skip=False, manual=False):
    root = Path(root).expanduser().resolve()
    with source_tree(source, ref) as (repo, locator, revision):
        fallback_name = Path(locator.rstrip('/')).name.removesuffix('.git')
        plugins = discover(repo, fallback_name, fix)
        if not plugins:
            fail('No supported plugin components found.')
        if listing and not selected_plugin:
            for name, (plugin_root, manifests) in sorted(plugins.items()):
                print(f'PLUGIN {name} ({plugin_root.relative_to(repo)})')
                for kind in ('skills', 'agents'):
                    for entry in entries(plugin_root, manifests, kind, fix):
                        print(f'  {kind}: {entry}')
                for entry in mcp_entries(plugin_root, manifests, fix):
                    print(f'  mcp: {entry}')
            return
        if not selected_plugin:
            if len(plugins) > 1:
                fail('Multiple plugins found; select --plugin: ' + ', '.join(sorted(plugins)))
            selected_plugin = next(iter(plugins))
        if selected_plugin not in plugins:
            fail(f'Plugin not found: {selected_plugin}')
        namespace = valid_name(namespace or selected_plugin)
        plugin_root, manifests = plugins[selected_plugin]
        if root.is_relative_to(plugin_root.resolve()):
            fail('Destination must not be inside the source plugin.')
        with tempfile.TemporaryDirectory(prefix='opencode-import-payload-') as temp:
            staging = Path(temp) / 'payload'
            desired, fingerprint, snapshot = build_payload(plugin_root, manifests, namespace, root, kinds, staging, fix, skip)
            if listing:
                for key in sorted(desired):
                    print(key)
                return
            if manual:
                print_manual_script(desired, MIGRATION_LOG)
                return
            with install_lock(root, preview):
                for item in desired.values():
                    item.update(revision=revision, source_hash=fingerprint)
                state = state_read(root)
                old = state['plugins'].get(namespace)
                if old and (old.get('source') != locator or old.get('plugin') != selected_plugin):
                    fail('Namespace belongs to a different source. Choose another --namespace.')
                retained, changes = make_plan(root, state, namespace, desired, kinds, mode, preview, ask)
                entry = {'source': locator, 'plugin': selected_plugin, 'ref': ref, 'revision': revision,
                         'source_hash': fingerprint, 'items': retained}
                # No accepted changes means no metadata writes, even when prompts were declined.
                if not changes and retained == (old or {}).get('items', {}):
                    print('No changes.')
                    return
                new_snapshot_needed = any(v.get('snapshot') == str(snapshot) for v in retained.values())
                snapshot_path = destination_path(root, str(snapshot))
                if new_snapshot_needed:
                    if snapshot_path.is_symlink():
                        fail('Snapshot destination is a symlink.')
                    if snapshot_path.exists():
                        if not snapshot_path.is_dir() or tree_hash(snapshot_path) != tree_hash(staging):
                            fail('Snapshot path is occupied by modified or unrelated content.')
                    else:
                        changes.insert(0, (str(snapshot), ('tree', staging)))
                state['plugins'][namespace] = entry
                changes.append((STATE, ('bytes', encoded(state))))
                if preview:
                    print('Dry run: no destination files or manifest changed; interactive decisions not requested.')
                    return
                apply_transaction(root, changes)
                print(f'Installed {namespace} into {root}. Restart OpenCode to reload.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', help='Local directory or Git URL')
    parser.add_argument('ref', nargs='?', help='Optional branch, tag or commit SHA')
    parser.add_argument('--plugin', help='Select a plugin in a multi-plugin repository')
    parser.add_argument('--namespace', help='Override the destination name prefix')
    parser.add_argument('--config-dir', default=os.environ.get('OPENCODE_CONFIG_DIR', str(Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'opencode')))
    parser.add_argument('--list', action='store_true', help='List components without writing the destination')
    parser.add_argument('--dry-run', action='store_true', help='Validate and preview without destination writes')
    parser.add_argument('--fix-names', action='store_true',
                        help='Normalize invalid names to lowercase hyphenated form instead of failing')
    parser.add_argument('--skip-unsupported', action='store_true',
                        help='Skip components OpenCode cannot represent instead of failing')
    parser.add_argument('--manual-mode', action='store_true',
                        help='Print a copy script for manual migration without writing the destination')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('-i', '--interactive', action='store_true')
    mode.add_argument('-f', '--force', action='store_true', help='Also prune intact managed components removed upstream')
    for kind in sorted(KINDS):
        parser.add_argument(f'--{kind}-only', action='store_true')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args(argv)
    kinds = {k for k in KINDS if getattr(args, k + '_only')} or KINDS
    try:
        install(args.config_dir, args.source, args.ref, args.plugin, args.namespace, kinds,
                'interactive' if args.interactive else 'force' if args.force else 'sync', args.dry_run, args.list,
                fix=args.fix_names, skip=args.skip_unsupported, manual=args.manual_mode)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Import failed: {exc}', file=sys.stderr)
        if im_migration := MIGRATION_LOG:
            print('Manual migration list (nothing was written):', file=sys.stderr)
            for export, source in im_migration:
                if source:
                    print(f'  {source} -> {export}', file=sys.stderr)
                else:
                    print(f'  {export} (MCP; merge into opencode.jsonc manually)', file=sys.stderr)
            print('Re-run with --fix-names / --skip-unsupported, or copy these paths yourself.',
                  file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
