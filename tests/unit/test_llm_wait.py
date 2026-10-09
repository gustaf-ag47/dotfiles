import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import sys
import unittest

from tests.unit._helpers import stub_http

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'bin/llm-wait'

class WaitHTTPTests(unittest.TestCase):
    def run_wait(self, predicate, ready, max_time='1s', failures=False, provider='anthropic'):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if failures:
                    self.send_error(500); return
                if self.path.startswith('/_route'):
                    body = {'candidates':[{'provider':provider,'routable':ready}]}
                else:
                    body = {'tokens':[], 'providers':{}}
                raw=json.dumps(body).encode(); self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        with stub_http(Handler) as srv:
            import os
            env=os.environ.copy(); env['PI_ANTHROPIC_PROXY_URL']=f'http://127.0.0.1:{srv.server_port}'
            return subprocess.run([sys.executable,str(SCRIPT),'--until',predicate,'--model','claude-sonnet-5','--poll','.05','--max',max_time],capture_output=True,text=True,env=env,timeout=8)
    def test_routable_returns_zero(self):
        result=self.run_wait('anthropic.routable',True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_grok_routable_uses_oracle_and_contributes_to_any(self):
        for predicate in ('grok.routable', 'any.routable'):
            result = self.run_wait(predicate, True, provider='grok-build')
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_grok_candidate_is_not_ready(self):
        result = self.run_wait('grok.routable', True, max_time='.1s')
        self.assertEqual(result.returncode, 2, result.stderr)

    def test_timeout_returns_two_and_wait_message(self):
        result=self.run_wait('anthropic.routable',False)
        self.assertEqual(result.returncode,2); self.assertIn('waiting for',result.stdout)
    def test_unreachable_returns_three_after_consecutive_failures(self):
        class Down(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.send_error(500)
        with stub_http(Down) as srv:
            import os
            env=os.environ.copy(); env['PI_ANTHROPIC_PROXY_URL']=f'http://127.0.0.1:{srv.server_port}'
            r=subprocess.run([sys.executable,str(SCRIPT),'--until','any.routable','--poll','.05','--max','5s'],capture_output=True,text=True,env=env,timeout=5)
            self.assertEqual(r.returncode,3,r.stderr)

if __name__ == '__main__': unittest.main()
