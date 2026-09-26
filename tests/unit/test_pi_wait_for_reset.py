"""Real pi against a fake proxy: pool-exhausted 503s past pi's retries, then 200.

llm-failover must wait for the reset the 503 body names, drop the failed attempt
from the model context and continue the same run. No provider credentials.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

ROOT = Path(__file__).resolve().parents[2]
PI = shutil.which('pi')
MODEL = 'claude-haiku-4-5'


def exhausted_body(reset: datetime) -> dict:
    message = (f'Claude subscription request unavailable: no OAuth account can serve {MODEL} right now.\n'
               'Account status:\n'
               f'- 82a293204226 (gs@example.test): cooldown until {reset.isoformat()} for {MODEL}; weekly 78% (header)\n'
               'Run `claude-usage` for the full account report and reset times.')
    return {'type': 'error', 'error': {'type': 'overloaded_error', 'message': message}}


def ok_stream(model: str) -> bytes:
    events = [
        {'type': 'message_start', 'message': {'id': 'msg_test', 'type': 'message', 'role': 'assistant', 'model': model,
                                              'content': [], 'stop_reason': None, 'usage': {'input_tokens': 2, 'output_tokens': 0}}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': 'MOCK_OK'}},
        {'type': 'content_block_stop', 'index': 0},
        {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': 2}},
        {'type': 'message_stop'},
    ]
    return ''.join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


@unittest.skipUnless(PI, 'Pi installation required')
class WaitForReset(unittest.TestCase):
    def run_pi(self, failures: int, env_extra: dict) -> tuple[subprocess.CompletedProcess, list, list]:
        posts, routes = [], []
        reset = datetime.now(timezone.utc) + timedelta(seconds=2)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                routes.append(self.path)
                routable = datetime.now(timezone.utc) >= reset
                body = {'model': MODEL, 'candidates': [
                    {'provider': 'anthropic', 'model': MODEL, 'routable': routable,
                     'reason': None if routable else 'cooldown', 'reset_at': None if routable else reset.isoformat()}],
                    'first_routable': None}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                posts.append(body)
                if len(posts) <= failures:
                    data = json.dumps(exhausted_body(reset)).encode()
                    self.send_response(503)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(ok_stream(body['model']))

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                agent = Path(directory)
                (agent / 'auth.json').write_text(json.dumps({'anthropic': {'type': 'api_key', 'key': 'fake-proxy-only'}}))
                (agent / 'settings.json').write_text(json.dumps({'retry': {'enabled': True, 'maxRetries': 1, 'baseDelayMs': 10}}))
                env = {k: v for k, v in os.environ.items()
                       if not k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_', 'DEEPSEEK_', 'PI_DOTFILES_', 'PI_FAILOVER_'))}
                env.update(PI_CODING_AGENT_DIR=directory, PI_OFFLINE='1',
                           PI_ANTHROPIC_PROXY_URL=f'http://127.0.0.1:{server.server_port}', PI_FAILOVER_POLL_SECONDS='0.5')
                env.update(env_extra)
                args = [PI, '--no-extensions', '-e', str(ROOT / 'config/pi/anthropic-token-proxy.ts'),
                        '-e', str(ROOT / 'config/pi/extensions/llm-failover.ts'), '--no-session', '--no-context-files',
                        '--no-skills', '--no-tools', '--thinking', 'off', '--model', f'anthropic/{MODEL}', '-p', 'Reply MOCK_OK']
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=60)
                return result, posts, routes
        finally:
            server.shutdown()
            server.server_close()

    def test_waits_for_reset_then_resumes_the_same_run(self):
        result, posts, routes = self.run_pi(failures=2, env_extra={})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('MOCK_OK', result.stdout)
        self.assertIn('waiting until', result.stdout + result.stderr)
        self.assertIn('anthropic pool recovered', result.stdout + result.stderr)
        self.assertEqual(len(posts), 3, 'initial + one pi retry fail, the resumed request succeeds')
        self.assertTrue(routes)
        # Same prompt, and the failed attempts never reach the model context.
        self.assertEqual(posts[2]['messages'], posts[0]['messages'])

    def test_opt_out_keeps_the_old_failure(self):
        result, posts, _ = self.run_pi(failures=2, env_extra={'PI_FAILOVER_WAIT': '0'})
        self.assertNotIn('MOCK_OK', result.stdout)
        self.assertEqual(len(posts), 2)


if __name__ == '__main__':
    unittest.main()
