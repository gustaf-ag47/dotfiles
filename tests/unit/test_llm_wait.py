import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'bin/llm-wait'

class WaitHTTPTests(unittest.TestCase):
    def run_wait(self, predicate, ready, max_time='1s', failures=False):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                if failures:
                    self.send_error(500); return
                if self.path.startswith('/_route'):
                    body = {'candidates':[{'provider':'anthropic','routable':ready}]}
                else:
                    body = {'tokens':[], 'providers':{}}
                raw=json.dumps(body).encode(); self.send_response(200); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
        srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        try:
            import os
            env=os.environ.copy(); env['PI_ANTHROPIC_PROXY_URL']=f'http://127.0.0.1:{srv.server_port}'
            return subprocess.run([sys.executable,str(SCRIPT),'--until',predicate,'--model','claude-sonnet-5','--poll','.05','--max',max_time],capture_output=True,text=True,env=env,timeout=8)
        finally: srv.shutdown(); srv.server_close()
    def test_routable_returns_zero(self):
        result=self.run_wait('anthropic.routable',True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_timeout_returns_two_and_wait_message(self):
        result=self.run_wait('anthropic.routable',False)
        self.assertEqual(result.returncode,2); self.assertIn('waiting for',result.stdout)
    def test_unreachable_returns_three_after_consecutive_failures(self):
        class Down(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self): self.send_error(500)
        srv=ThreadingHTTPServer(('127.0.0.1',0),Down); threading.Thread(target=srv.serve_forever,daemon=True).start()
        try:
            import os
            env=os.environ.copy(); env['PI_ANTHROPIC_PROXY_URL']=f'http://127.0.0.1:{srv.server_port}'
            r=subprocess.run([sys.executable,str(SCRIPT),'--until','any.routable','--poll','.05','--max','5s'],capture_output=True,text=True,env=env,timeout=5)
            self.assertEqual(r.returncode,3,r.stderr)
        finally: srv.shutdown(); srv.server_close()

if __name__ == '__main__': unittest.main()
