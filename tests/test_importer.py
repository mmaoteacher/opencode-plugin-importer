import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/install-plugin/scripts/importer.py'
spec = importlib.util.spec_from_file_location('importer', SCRIPT)
im = importlib.util.module_from_spec(spec)
spec.loader.exec_module(im)


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='importer tests ')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.source = self.base / 'sample'
        self.source.mkdir()
        self.dest = self.base / 'config dir'
        self.json(self.source / '.claude-plugin/plugin.json', {'name': 'demo'})
        self.skill('hello')
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def skill(self, name, prefix='', body='hello', extra=''):
        path = self.source / prefix / 'skills' / name / 'SKILL.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'---\nname: {name}\ndescription: Example skill\n{extra}---\n{body}\n')
        return path

    def install(self, **kwargs):
        options = dict(root=self.dest, source=str(self.source), ref=None, selected_plugin=None,
                       namespace=None, kinds=im.KINDS)
        options.update(kwargs)
        im.install(**options)

    def snapshot(self):
        if not self.dest.exists():
            return None
        return {str(p.relative_to(self.dest)): ('link', os.readlink(p)) if p.is_symlink()
                else ('dir',) if p.is_dir() else ('file', p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.dest.rglob('*')}

    def test_fresh_install_idempotent_and_relative_assets(self):
        (self.source / 'skills/hello/.hidden').write_text('hidden')
        (self.source / 'scripts').mkdir()
        (self.source / 'scripts/helper.py').write_text('print(1)')
        self.install()
        exported = self.dest / 'skills/demo-hello'
        self.assertTrue(exported.is_symlink())
        self.assertEqual(im.markdown(exported / 'SKILL.md')[0]['name'], 'demo-hello')
        self.assertEqual((exported / '.hidden').read_text(), 'hidden')
        self.assertEqual((exported.resolve() / '../../scripts/helper.py').read_text(), 'print(1)')
        before = self.snapshot()
        self.install()
        self.assertEqual(before, self.snapshot())

    def test_dry_run_and_list_never_create_destination(self):
        self.install(preview=True)
        self.assertFalse(self.dest.exists())
        self.install(listing=True)
        self.assertFalse(self.dest.exists())

    def test_dry_run_never_updates_existing_manifest(self):
        self.install()
        self.skill('new')
        before = self.snapshot()
        self.install(preview=True)
        self.assertEqual(before, self.snapshot())

    def test_more_than_one_component_does_not_exit_early(self):
        self.skill('second')
        self.install()
        self.assertEqual(len(list((self.dest / 'skills').iterdir())), 2)

    def test_root_formats_and_legacy_layouts(self):
        for prefix in ('.claude', '.codex', '.opencode', '.agents'):
            self.skill(prefix[1:], prefix)
        self.install()
        self.assertEqual(len(list((self.dest / 'skills').iterdir())), 5)

    def test_conflicting_frontmatter_and_duplicate_skill_fail(self):
        self.skill('hello', '.codex')
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Duplicate skills'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_fix_names_normalizes_mcp_and_agent_names(self):
        self.skill('My Skill')
        self.json(self.source / '.mcp.json', {'mcpServers': {'GitLab': {'command': 'glab'}}})
        self.install(fix=True)
        self.assertTrue((self.dest / 'skills/demo-my-skill').is_symlink())
        config = json.loads((self.dest / 'opencode.json').read_text())
        self.assertIn('demo-gitlab', config['mcp'])

    def test_fix_names_absent_still_fails(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'GitLab': {'command': 'glab'}}})
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Invalid name'):
            self.install()
        self.assertFalse(self.dest.exists())

    def agent(self, name, extra=''):
        path = self.source / 'agents' / f'{name}.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'---\nname: {name}\ndescription: Example agent\n{extra}---\nagent\n')
        return path

    def test_skip_unsupported_imports_remaining(self):
        self.skill('guarded', extra='allowed-tools: [Bash]\n')
        self.agent('aliased', 'model: sonnet\n')
        with mock.patch.object(im, 'warn') as warned:
            self.install(skip=True)
        installed = sorted(p.name for p in (self.dest / 'skills').iterdir())
        self.assertEqual(installed, ['demo-hello'])
        self.assertFalse((self.dest / 'agents').exists())
        messages = ' '.join(str(c) for c in warned.call_args_list)
        self.assertIn('guarded', messages)
        self.assertIn('aliased', messages)

    def test_skip_unsupported_disabled_still_fails(self):
        self.skill('guarded', extra='allowed-tools: [Bash]\n')
        with self.assertRaisesRegex(im.ImportErrorDetail, 'invocation/tool restrictions'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_manual_mode_prints_script_and_skips_writes(self):
        self.agent('reviewer')
        self.json(self.source / '.mcp.json', {'mcpServers': {'local': {'command': 'glab'}}})
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.install(manual=True)
        printed = output.getvalue()
        self.assertIn('DEST="${1:-$HOME/.config/opencode}"', printed)
        self.assertIn('cp -R', printed)
        self.assertIn('skills/demo-hello', printed)
        self.assertIn('agents/demo-reviewer.md', printed)
        self.assertIn('#   demo-local', printed)
        self.assertFalse(self.dest.exists())

    def test_manual_mode_ignores_dry_run_prompt(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.install(manual=True, preview=True)
        printed = output.getvalue()
        self.assertIn('cp -R', printed)
        self.assertNotIn('Dry run:', printed)
        self.assertFalse(self.dest.exists())

    def test_failure_prints_manual_migration_list(self):
        # Sorted so the transferable skill is converted before the failing one aborts the run.
        self.skill('z-guarded', extra='allowed-tools: [Bash]\n')
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            status = im.main([str(self.source), '--config-dir', str(self.dest)])
        self.assertEqual(status, 1)
        printed = errors.getvalue()
        self.assertIn('Manual migration list', printed)
        self.assertIn(str(self.source / 'skills/hello'), printed)
        self.assertIn('demo-hello', printed)
        self.assertFalse(self.dest.exists())

    def test_skip_unsupported_keeps_other_mcp_servers(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {
            'broken': {'command': 'glab', 'unsupportedField': 1},
            'working': {'command': 'glab'}}})
        with mock.patch.object(im, 'warn'):
            self.install(skip=True)
        config = json.loads((self.dest / 'opencode.json').read_text())
        self.assertEqual(sorted(config['mcp']), ['demo-working'])

    def test_multiple_plugins_require_explicit_selection(self):
        nested = self.source / 'plugins/other'
        self.json(nested / 'plugin.json', {'name': 'other'})
        (nested / 'skills/x').mkdir(parents=True)
        (nested / 'skills/x/SKILL.md').write_text('---\nname: x\ndescription: X\n---\nX')
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Multiple plugins'):
            self.install()
        self.install(selected_plugin='other')
        self.assertTrue((self.dest / 'skills/other-x').is_dir())
        self.assertFalse((self.dest / 'skills/demo-hello').exists())

    def test_manifest_custom_paths(self):
        (self.source / 'skills').rename(self.source / 'custom-skills')
        self.json(self.source / '.claude-plugin/plugin.json', {'name': 'demo', 'skills': './custom-skills'})
        self.install()
        self.assertTrue((self.dest / 'skills/demo-hello').exists())

    def test_mcp_conversion_and_preserve_unrelated_settings(self):
        self.json(self.dest / 'opencode.json', {'model': 'example/model', 'mcp': {'unrelated': {'type': 'remote', 'url': 'https://example.com'}}})
        self.json(self.source / '.mcp.json', {'mcpServers': {
            'local': {'type': 'stdio', 'command': 'node', 'args': ['${CLAUDE_PLUGIN_ROOT}/server.js'], 'env': {'TOKEN': '${TOKEN}'}},
            'remote': {'serverUrl': 'https://example.org/mcp', 'headers': {'Authorization': 'Bearer ${API_KEY}'}, 'oauth': False}}})
        self.install()
        config = im.read_json(self.dest / 'opencode.json')
        self.assertEqual(config['model'], 'example/model')
        self.assertIn('unrelated', config['mcp'])
        self.assertEqual(config['mcp']['demo-local']['type'], 'local')
        self.assertEqual(config['mcp']['demo-local']['environment'], {'TOKEN': '{env:TOKEN}'})
        self.assertIn(str(self.dest / '.plugin-importer/sources/demo'), config['mcp']['demo-local']['command'][1])
        self.assertEqual(config['mcp']['demo-remote']['type'], 'remote')
        self.assertFalse(config['mcp']['demo-remote']['oauth'])

    def test_jsonc_and_comments_inside_strings(self):
        self.dest.mkdir()
        (self.dest / 'opencode.jsonc').write_text('{// hi\n"model":"https://a/*b*/", "mcp":{},}')
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'command': ['echo', 'test']}}})
        self.install()
        self.assertEqual(im.read_json(self.dest / 'opencode.jsonc')['model'], 'https://a/*b*/')
        self.assertFalse((self.dest / 'opencode.json').exists())

    def test_codex_toml_mcp(self):
        folder = self.source / '.codex'
        folder.mkdir()
        (folder / 'config.toml').write_text('[mcp_servers.search]\nurl="https://example.com/mcp"\nbearer_token_env_var="TOKEN"\n')
        self.install(kinds={'mcp'})
        entry = im.read_json(self.dest / 'opencode.json')['mcp']['demo-search']
        self.assertEqual(entry['headers']['Authorization'], 'Bearer {env:TOKEN}')
        self.assertFalse((self.dest / 'skills').exists())

    def test_invalid_mcp_aborts_all_components(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'bad': {'command': 'node', 'cwd': '/tmp'}}})
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Unsupported MCP fields'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_unsupported_skill_restriction_is_not_silently_lost(self):
        self.skill('hello', extra='allowed-tools: Read\n')
        with self.assertRaisesRegex(im.ImportErrorDetail, 'restrictions'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_agent_tool_allowlist_and_denials(self):
        path = self.source / 'agents/reviewer.md'
        path.parent.mkdir()
        path.write_text('---\nname: reviewer\ndescription: Review\ntools: [Read, Bash, Edit]\ndisallowedTools: [Bash]\nmodel: inherit\n---\nReview')
        self.install()
        meta, _ = im.markdown(self.dest / 'agents/demo-reviewer.md')
        self.assertEqual(meta['permission'], {'*': 'deny', 'read': 'allow', 'edit': 'allow', 'bash': 'deny'})
        self.assertEqual(meta['mode'], 'subagent')
        self.assertNotIn('model', meta)

    def test_force_prunes_only_selected_owned_components(self):
        self.skill('gone')
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'command': 'echo'}}})
        self.install()
        (self.dest / 'skills/unrelated').mkdir()
        shutil.rmtree(self.source / 'skills/gone')
        (self.source / '.mcp.json').unlink()
        self.install()
        self.assertTrue((self.dest / 'skills/demo-gone').exists())
        self.install(mode='force', kinds={'skills'})
        self.assertFalse((self.dest / 'skills/demo-gone').exists())
        self.assertTrue((self.dest / 'skills/unrelated').exists())
        self.assertIn('demo-x', im.read_json(self.dest / 'opencode.json')['mcp'])
        self.install(mode='force', kinds={'mcp'})
        self.assertNotIn('demo-x', im.read_json(self.dest / 'opencode.json')['mcp'])

    def test_partial_update_keeps_unselected_skill_resources(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'command': 'echo'}}})
        self.install()
        before = (self.dest / 'skills/demo-hello/SKILL.md').read_text()
        self.skill('hello', body='changed')
        self.install(kinds={'mcp'})
        self.assertEqual(before, (self.dest / 'skills/demo-hello/SKILL.md').read_text())

    def test_interactive_decline_does_not_write(self):
        self.install(mode='interactive', ask=lambda _: 'n')
        self.assertFalse(self.dest.exists())
        self.install()
        before = self.snapshot()
        self.skill('hello', body='updated')
        self.install(mode='interactive', ask=lambda _: 'n')
        self.assertEqual(before, self.snapshot())

    def test_interactive_remove(self):
        self.skill('gone')
        self.install()
        shutil.rmtree(self.source / 'skills/gone')
        self.install(mode='interactive', ask=lambda _: 'y')
        self.assertFalse((self.dest / 'skills/demo-gone').exists())

    def test_unmanaged_export_not_overwritten_even_with_force(self):
        path = self.dest / 'skills/demo-hello'
        path.mkdir(parents=True)
        (path / 'mine').write_text('keep')
        before = self.snapshot()
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Unmanaged'):
            self.install(mode='force')
        self.assertEqual(before, self.snapshot())

    def test_local_edits_protected(self):
        self.install()
        (self.dest / 'skills/demo-hello/SKILL.md').write_text('local edit')
        before = self.snapshot()
        with self.assertRaisesRegex(im.ImportErrorDetail, 'modified'):
            self.install(mode='force')
        self.assertEqual(before, self.snapshot())

    def test_local_mcp_edits_protected(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'command': 'echo'}}})
        self.install()
        config = im.read_json(self.dest / 'opencode.json')
        config['mcp']['demo-x']['enabled'] = False
        self.json(self.dest / 'opencode.json', config)
        with self.assertRaisesRegex(im.ImportErrorDetail, 'locally modified MCP'):
            self.install()

    def test_external_symlink_rejected(self):
        (self.source / 'secret').symlink_to(self.base)
        with self.assertRaisesRegex(im.ImportErrorDetail, 'external symlink'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_destination_parent_symlink_rejected(self):
        self.dest.mkdir()
        outside = self.base / 'outside'
        outside.mkdir()
        (self.dest / 'skills').symlink_to(outside)
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Unsafe destination parent'):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])

    def test_internal_file_symlink_rebased(self):
        (self.source / 'shared').write_text('reference')
        (self.source / 'skills/hello/ref').symlink_to(self.source / 'shared')
        self.install()
        shutil.rmtree(self.source)
        self.assertEqual((self.dest / 'skills/demo-hello/ref').read_text(), 'reference')

    def test_namespace_cannot_take_over_other_source(self):
        self.install()
        other = self.base / 'other'
        shutil.copytree(self.source, other)
        with self.assertRaisesRegex(im.ImportErrorDetail, 'different source'):
            self.install(source=str(other), mode='force')

    def test_legacy_manifest_is_preserved(self):
        self.json(self.dest / '.plugin-manifest.json', {'plugins': {}})
        before = self.snapshot()
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Legacy'):
            self.install()
        self.assertEqual(before, self.snapshot())

    def test_transaction_rolls_back_after_replacing_export(self):
        self.install()
        before = self.snapshot()
        self.skill('hello', body='changed')
        replace = os.replace
        fired = False

        def broken(source, target):
            nonlocal fired
            if not fired and str(target).endswith(im.STATE):
                fired = True
                raise OSError('simulated disk failure')
            return replace(source, target)

        with mock.patch.object(im.os, 'replace', side_effect=broken):
            with self.assertRaisesRegex(OSError, 'simulated'):
                self.install()
        self.assertTrue(fired)
        self.assertEqual(before, self.snapshot())

    def test_fresh_install_failure_removes_new_directories(self):
        replace = os.replace
        fired = False

        def broken(source, target):
            nonlocal fired
            if not fired and str(target).endswith(im.STATE):
                fired = True
                raise OSError('simulated')
            return replace(source, target)

        with mock.patch.object(im.os, 'replace', side_effect=broken):
            with self.assertRaises(OSError):
                self.install()
        self.assertFalse(self.dest.exists())

    def test_git_ref_does_not_modify_original_checkout(self):
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.source), *args], text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.com', 'commit', '-qm', 'fixture')
        revision = git('rev-parse', 'HEAD')
        self.skill('hello', body='uncommitted')
        before = git('status', '--porcelain')
        self.install(ref=revision)
        self.assertEqual(before, git('status', '--porcelain'))
        self.assertNotIn('uncommitted', (self.dest / 'skills/demo-hello/SKILL.md').read_text())
        self.assertEqual(im.read_json(self.dest / im.STATE)['plugins']['demo']['revision'], revision)

    def test_duplicate_yaml_fields_rejected(self):
        self.skill('hello', extra='name: other\n')
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Duplicate YAML'):
            self.install()

    def test_custom_single_skill_folder(self):
        (self.source / 'skills').rename(self.source / 'custom')
        self.json(self.source / '.claude-plugin/plugin.json', {'name': 'demo', 'skills': './custom/hello'})
        self.install()
        self.assertTrue((self.dest / 'skills/demo-hello/SKILL.md').exists())

    def test_jsonc_original_backed_up(self):
        self.dest.mkdir()
        content = '{// preserve original comments\n"mcp": {},}'
        (self.dest / 'opencode.jsonc').write_text(content)
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'command': 'echo'}}})
        self.install()
        backups = list((self.dest / '.plugin-importer/backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), content)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_conflicting_mcp_aliases_rejected(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {
            'command': 'node', 'env': {'X': 'a'}, 'environment': {'X': 'b'}}}})
        with self.assertRaisesRegex(im.ImportErrorDetail, 'Conflicting MCP fields'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_native_disabled_mcp_entry(self):
        self.json(self.source / 'opencode.json', {'mcp': {'x': {'enabled': False}}})
        self.install()
        self.assertEqual(im.read_json(self.dest / 'opencode.json')['mcp']['demo-x'], {'enabled': False})

    def test_manifest_path_escape_rejected(self):
        self.json(self.source / '.claude-plugin/plugin.json', {'name': 'demo', 'skills': '../outside'})
        with self.assertRaisesRegex(im.ImportErrorDetail, 'within the plugin'):
            self.install()
        self.assertFalse(self.dest.exists())

    def test_interactive_eof_is_non_mutating(self):
        def closed(_):
            raise EOFError()
        with self.assertRaisesRegex(im.ImportErrorDetail, 'nothing was written'):
            self.install(mode='interactive', ask=closed)
        self.assertFalse(self.dest.exists())

    def test_cli_wrapper_help_and_dry_run(self):
        env = dict(os.environ)
        env['PATH'] = str(Path(__import__('sys').executable).parent) + os.pathsep + env['PATH']
        wrapper = SCRIPT.with_name('install-plugin.sh')
        help_result = subprocess.run(['bash', str(wrapper), '--help'], env=env, capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        result = subprocess.run(['bash', str(wrapper), str(self.source), '--config-dir', str(self.dest), '--dry-run'],
                                env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.dest.exists())

    def test_equivalent_cross_host_mcp_definitions_deduplicated(self):
        self.json(self.source / '.mcp.json', {'mcpServers': {'x': {'type': 'stdio', 'command': 'echo'}}})
        self.json(self.source / 'mcp_config.json', {'mcpServers': {'x': {'type': 'command', 'command': 'echo'}}})
        self.install()
        self.assertEqual(list(im.read_json(self.dest / 'opencode.json')['mcp']), ['demo-x'])

    def test_development_dependencies_not_copied(self):
        (self.source / '.venv').mkdir()
        (self.source / '.venv/python').symlink_to('/usr/bin/python3')
        self.install()
        snapshot = (self.dest / 'skills/demo-hello').resolve().parents[1]
        self.assertFalse((snapshot / '.venv').exists())

    def test_nested_external_plugin_symlink_rejected(self):
        outside = self.base / 'outside-plugin'
        self.json(outside / 'plugin.json', {'name': 'outside'})
        (self.source / 'plugins').mkdir()
        (self.source / 'plugins/evil').symlink_to(outside)
        with self.assertRaisesRegex(im.ImportErrorDetail, 'External symlink'):
            self.install(listing=True)
        self.assertFalse(self.dest.exists())

    def test_git_url_fallback_name_is_repository_name(self):
        (self.source / '.claude-plugin/plugin.json').unlink()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.source), *args], text=True).strip()
        git('init', '-q')
        git('add', '.')
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.com', 'commit', '-qm', 'fixture')
        self.install(source=self.source.as_uri())
        self.assertTrue((self.dest / 'skills/sample-hello').is_dir())


if __name__ == '__main__':
    unittest.main()
