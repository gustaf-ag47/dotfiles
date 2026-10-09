"""Offline Pi typing adapter checks. Fake credentials/SDK fixtures only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'config/pi/skills/jev-ultrafast/scripts'
sys.path.insert(0, str(SCRIPTS))
import _text_backend as backend
import _pi_text as adapter


def context():
    return {'goal': 'Enter London', 'field': {'label': 'Destination', 'role': 'textbox', 'value': ''},
            'page': {'title': 'Fixture', 'text': 'Destination'}, 'recent_actions': []}


class PiTypingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.env = {'HOME': str(self.home), 'PATH': os.environ.get('PATH', ''),
                    'XDG_CONFIG_HOME': str(self.home / 'config'),
                    'TEXT_MODEL_BACKEND': 'pi', 'PI_TEXT_MODEL': 'openai-codex/test-model'}

    def test_selection_is_explicit_and_saved_config_is_supported(self):
        self.assertEqual(backend.resolve_text_backend({'HOME': str(self.home)})['status'], 'unset')
        cfg = backend.config_path(self.env)
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({'backend': 'pi', 'model': 'anthropic/claude-haiku-4-5'}))
        saved_env = {k: v for k, v in self.env.items() if k not in ('TEXT_MODEL_BACKEND', 'PI_TEXT_MODEL')}
        self.assertEqual(backend.resolve_text_backend(saved_env)['model'], 'anthropic/claude-haiku-4-5')
        self.assertEqual(backend.resolve_text_backend(self.env)['model'], 'openai-codex/test-model')
        self.assertEqual(backend.resolve_text_backend(dict(self.env, TEXT_MODEL_BACKEND='none'))['status'], 'unset')

    def test_api_backend_contract_preserved_and_mixed_config_rejected(self):
        self.assertEqual(backend.resolve_text_backend(dict(self.env, TEXT_MODEL_API_KEY='test'))['reason'], 'mixed_backends')
        api = {'HOME': str(self.home), 'TEXT_MODEL_API_KEY': 'test'}
        self.assertEqual(backend.resolve_text_backend(api)['status'], 'partial')
        api.update(TEXT_MODEL_BASE_URL='https://example.com/v1', TEXT_MODEL='example')
        self.assertEqual(backend.resolve_text_backend(api)['status'], 'configured')

    def test_bad_config_and_bounds_fail_closed(self):
        for value in ('nan', 'inf', '-1', '0', '61'):
            self.assertEqual(backend.resolve_text_backend(dict(self.env, PI_TEXT_TIMEOUT_SECONDS=value))['status'], 'invalid_config')
        for model in ('anthropic', 'unknown/model', 'anthropic/a;echo', 'openai-codex/../../x'):
            self.assertEqual(backend.resolve_text_backend(dict(self.env, PI_TEXT_MODEL=model))['status'], 'invalid_config')
        cfg = backend.config_path(self.env)
        cfg.parent.mkdir(parents=True)
        cfg.write_text('{malformed')
        saved_env = {k: v for k, v in self.env.items() if k not in ('TEXT_MODEL_BACKEND', 'PI_TEXT_MODEL')}
        self.assertEqual(backend.resolve_text_backend(saved_env)['status'], 'invalid_config')

    def test_worker_gets_stdin_not_prompt_argv_and_no_unrelated_credentials(self):
        observed = []
        credential = 'private-fixture'
        env = dict(self.env, TYPESAFE_API_KEY=credential, OPENAI_API_KEY=credential,
                   NODE_OPTIONS='unwanted', PI_DELEGATE_GOAL='unrelated task', DEBUG='*')
        def runner(cmd, payload, **opts):
            observed.append((cmd, payload, opts))
            data = json.loads(payload)
            self.assertEqual(data['context'], context())
            self.assertTrue(data['piDir'].endswith('/config/pi'))
            self.assertEqual(data['agentDir'], str(self.home / '.pi/agent'))
            return 0, json.dumps({'ok': True, 'text': 'London', 'model': env['PI_TEXT_MODEL'], 'usage': None}).encode()
        with patch.object(adapter, 'find_pi_sdk', return_value=Path('/fixture/sdk')), \
             patch.object(adapter.shutil, 'which', return_value='/fixture/node'):
            text, meta = adapter.pi_field_text(context(), env=env, runner=runner)
        self.assertEqual(text, 'London')
        self.assertEqual(meta['model'], 'openai-codex/test-model')
        cmd, payload, options = observed[0]
        self.assertNotIn('London', ' '.join(cmd))
        self.assertNotIn('private-fixture', payload.decode())
        for key in ('TYPESAFE_API_KEY', 'OPENAI_API_KEY', 'NODE_OPTIONS', 'DEBUG', 'PI_DELEGATE_GOAL'):
            self.assertNotIn(key, options['env'])

    def test_bad_provider_output_is_not_typed_or_echoed(self):
        outputs = [b'PRIVATE_RAW_ERROR', b'{"ok":false,"error":"PRIVATE_RAW_ERROR"}',
                   b'{"ok":true,"text":null}', b'{"ok":true,"text":"x","model":"other/model"}']
        with patch.object(adapter, 'find_pi_sdk', return_value=Path('/fixture/sdk')), \
             patch.object(adapter.shutil, 'which', return_value='/fixture/node'):
            for output in outputs:
                with self.assertRaises(adapter.PiTextError) as caught:
                    adapter.pi_field_text(context(), env=self.env, runner=lambda *a, **kw: (0, output))
                self.assertNotIn('PRIVATE_RAW_ERROR', str(caught.exception))

    def test_invalid_context_fails_before_runtime_or_credentials(self):
        with patch.object(adapter, 'find_pi_sdk', side_effect=AssertionError('must not resolve SDK')):
            for bad in ({}, dict(context(), cookie='private'), dict(context(), goal='x' * 32769)):
                with self.assertRaises(adapter.PiTextError):
                    adapter.pi_field_text(bad, env=self.env)

    def test_only_field_text_callback_is_replaced_and_selection_pinned(self):
        sentinel = object()
        module = types.SimpleNamespace(field_text=sentinel, Agent=sentinel)
        adapter.configure_text_backend(module, self.env)
        self.assertIs(module.Agent, sentinel)
        self.env['PI_TEXT_MODEL'] = 'anthropic/changed-after-start'
        with patch.object(adapter, 'pi_field_text', return_value=('London', {})) as call:
            self.assertEqual(module.field_text(context())[0], 'London')
            self.assertEqual(call.call_args.kwargs['env']['PI_TEXT_MODEL'], 'openai-codex/test-model')
        adapter.configure_text_backend(module, {'HOME': str(self.home), 'TEXT_MODEL_BACKEND': 'api',
                                               'TEXT_MODEL_API_KEY': 'test', 'TEXT_MODEL_BASE_URL': 'https://example.com/v1',
                                               'TEXT_MODEL': 'fixture'})
        self.assertIs(module.field_text, sentinel, 'an explicit API run must not retain a prior Pi callback')
        disabled = types.SimpleNamespace(field_text=sentinel)
        adapter.configure_text_backend(disabled, dict(self.env, TEXT_MODEL_BACKEND='none', TEXT_MODEL_API_KEY='test'))
        with self.assertRaisesRegex(adapter.PiTextError, 'typing_disabled'):
            disabled.field_text(context())

    def test_node_worker_timeout_and_output_cap(self):
        env = dict(os.environ)
        start = time.monotonic()
        with self.assertRaisesRegex(adapter.PiTextError, 'timeout'):
            adapter.run_worker([sys.executable, '-c', 'import time; time.sleep(30)'], b'{}', env=env, timeout=0.2)
        self.assertLess(time.monotonic() - start, 3)
        with self.assertRaisesRegex(adapter.PiTextError, 'output_too_large'):
            adapter.run_worker([sys.executable, '-c', 'import sys; sys.stdout.write("x"*1000000)'], b'{}', env=env, timeout=3)

    def test_saved_selection_is_frozen_for_driver(self):
        selection = backend.resolve_text_backend(self.env)
        pinned = backend.pin_backend_env(self.env, selection)
        self.assertEqual(pinned['TEXT_MODEL_BACKEND'], 'pi')
        self.assertEqual(pinned['PI_TEXT_MODEL'], selection['model'])


if __name__ == '__main__':
    unittest.main()
