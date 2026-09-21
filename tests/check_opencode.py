"""Opt-in read-only OpenCode discovery/handshake verification in temporary directories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'skills/install-plugin/scripts/importer.py'


def main():
    with tempfile.TemporaryDirectory(prefix='importer-opencode-check-') as temporary:
        work = Path(temporary).resolve()
        source = work / 'fixture'
        destination = work / 'config/opencode'
        (source / 'skills/sample').mkdir(parents=True)
        (source / 'agents').mkdir()
        (source / 'plugin.json').write_text(json.dumps({'name': 'fixture'}))
        (source / 'skills/sample/SKILL.md').write_text('---\nname: sample\ndescription: Synthetic test skill\n---\nRead a sample.')
        (source / 'agents/reviewer.md').write_text('---\ndescription: Synthetic reviewer\ntools: [Read]\n---\nReview a sample.')
        (source / 'server.py').write_text('''import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    if message['method'] == 'initialize':
        result = {'protocolVersion': message['params']['protocolVersion'], 'serverInfo': {'name': 'fixture', 'version': '1.0'}, 'capabilities': {'tools': {}}}
    elif message['method'] == 'tools/list':
        result = {'tools': [{'name': 'sample', 'description': 'Synthetic test', 'inputSchema': {'type': 'object'}}]}
    else:
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
''')
        (source / '.mcp.json').write_text(json.dumps({'mcpServers': {'local': {
            'command': sys.executable, 'args': ['${CLAUDE_PLUGIN_ROOT}/server.py']}}}))
        subprocess.run([sys.executable, str(SCRIPT), str(source), '--config-dir', str(destination)], check=True)
        env = dict(os.environ)
        for key, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                            ('XDG_STATE_HOME', 'state'), ('XDG_CACHE_HOME', 'cache')]:
            env[key] = str(work / suffix)
        env['OPENCODE_CONFIG_DIR'] = str(destination)
        env['OPENCODE_DISABLE_CLAUDE_CODE'] = 'true'
        env.pop('OPENCODE_CONFIG', None)
        env.pop('OPENCODE_CONFIG_CONTENT', None)

        def run(*arguments):
            p = subprocess.run(['opencode', *arguments], cwd=work, env=env,
                               capture_output=True, text=True, timeout=45)
            if p.returncode:
                raise RuntimeError('OpenCode check failed: ' + p.stderr)
            return p.stdout

        skills = json.loads(run('debug', 'skill'))
        assert any(s['name'] == 'fixture-sample' for s in skills), 'Imported skill missing'
        agent = json.loads(run('debug', 'agent', 'fixture-reviewer'))
        assert agent['name'] == 'fixture-reviewer', 'Imported agent missing'
        config = json.loads(run('debug', 'config'))
        assert config['mcp']['fixture-local']['type'] == 'local'
        status = run('mcp', 'list')
        assert 'fixture-local' in status and 'connected' in status.lower(), 'MCP connection not confirmed'
        print('OpenCode discovered the imported skill and agent and connected to the synthetic MCP.')
        print('No model call was made. All host configuration was isolated and removed.')


if __name__ == '__main__':
    main()
