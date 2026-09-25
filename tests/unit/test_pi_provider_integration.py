"""Offline CLI/HTTP integration against the installed Pi; no provider credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[2]
PI = shutil.which('pi')


# Exercises the unlanded anthropic-subscription.ts provider override; with current
# pi it fails model resolution ("No API key found for openrouter"). Opt in explicitly.
@unittest.skipUnless(PI, 'Pi installation required')
@unittest.skipUnless(os.environ.get('PI_PROVIDER_INTEGRATION') == '1',
                     'anthropic-subscription.ts not landed; set PI_PROVIDER_INTEGRATION=1 to run')
class ProviderIntegration(unittest.TestCase):
    def test_anthropic_route_and_deepseek_isolation(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path, dict(self.headers), body))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                if 'messages' in self.path:
                    events = [
                        {'type': 'message_start', 'message': {'id': 'msg_test', 'type': 'message', 'role': 'assistant', 'model': body['model'], 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 2, 'output_tokens': 0}}},
                        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
                        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'MOCK_OK'}},
                        {'type': 'content_block_stop', 'index': 0},
                        {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 2}},
                        {'type': 'message_stop'},
                    ]
                    wire = ''.join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
                else:
                    event = {'id': 'test', 'object': 'chat.completion.chunk', 'model': body['model'], 'choices': [{'index': 0, 'delta': {'role': 'assistant', 'content': 'MOCK_OK'}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 2, 'completion_tokens': 2, 'total_tokens': 4}}
                    wire = f'data: {json.dumps(event)}\n\ndata: [DONE]\n\n'
                self.wfile.write(wire.encode())

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                agent = Path(directory)
                endpoint = f'http://127.0.0.1:{server.server_port}'
                (agent / 'auth.json').write_text(json.dumps({'deepseek': {'type': 'api_key', 'key': 'fake-deepseek-only'}}))
                (agent / 'settings.json').write_text(json.dumps({'retry': {'enabled': False}}))
                (agent / 'models.json').write_text(json.dumps({'providers': {'deepseek': {'baseUrl': endpoint}}}))
                env = {k: v for k, v in os.environ.items() if not k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_', 'DEEPSEEK_', 'PI_DOTFILES_'))}
                env.update(PI_CODING_AGENT_DIR=directory, PI_OFFLINE='1', PI_ANTHROPIC_PROXY_URL=endpoint)
                args = [PI, '--no-extensions', '-e', str(ROOT / 'config/pi/extensions/anthropic-subscription.ts'),
                        '--no-session', '--no-context-files', '--no-skills', '--no-tools', '--thinking', 'off', '-p']
                for model in ('anthropic/claude-haiku-4-5', 'deepseek/deepseek-v4-flash'):
                    result = subprocess.run(args + ['--model', model, 'Reply MOCK_OK'], env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn('MOCK_OK', result.stdout)
                self.assertEqual(len(received), 2)
                a_path, a_headers, a_body = received[0]
                d_path, d_headers, d_body = received[1]
                self.assertIn('/v1/messages', a_path)
                self.assertIn('proxy-injects', next(v for k, v in a_headers.items() if k.lower() == 'authorization'))
                self.assertEqual(len(a_body['system']), 1)
                self.assertIn('You are an expert', str(a_body['messages']))
                self.assertEqual(next(v for k, v in d_headers.items() if k.lower() == 'authorization'), 'Bearer fake-deepseek-only')
                self.assertNotIn("Anthropic's official CLI", str(d_body))
                # A malformed remote route fails without issuing another request.
                env['PI_ANTHROPIC_PROXY_URL'] = 'https://example.com'
                failed = subprocess.run(args + ['--model', 'anthropic/claude-haiku-4-5', 'Reply MOCK_OK'], env=env, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn('loopback', failed.stderr + failed.stdout)
                self.assertEqual(len(received), 2)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
