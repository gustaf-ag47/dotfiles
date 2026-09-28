import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from importlib.machinery import SourceFileLoader

proxy=SourceFileLoader('proxy_no_starvation',str(Path(__file__).parents[2]/'bin/claude-token-proxy')).load_module()

class SpendTests(unittest.TestCase):
 def setUp(self):
  self.old=proxy.DEEPSEEK_SPEND.copy()
  proxy.DEEPSEEK_SPEND.update(month='2026-09',start_balance=None,min_balance=None)
 def tearDown(self): proxy.DEEPSEEK_SPEND=self.old
 def test_spend_topup_and_month_rollover(self):
  proxy.update_deepseek_spend(10,datetime(2026,9,1,tzinfo=timezone.utc))
  proxy.update_deepseek_spend(4,datetime(2026,9,10,tzinfo=timezone.utc))
  self.assertEqual(proxy.deepseek_month_spend(),6)
  proxy.update_deepseek_spend(12,datetime(2026,9,11,tzinfo=timezone.utc))
  self.assertEqual(proxy.deepseek_month_spend(),0)
  proxy.update_deepseek_spend(9,datetime(2026,10,1,tzinfo=timezone.utc))
  self.assertEqual(proxy.deepseek_month_spend(),0)
  self.assertEqual(proxy.DEEPSEEK_SPEND['month'],'2026-10')
 def test_cap_blocks_candidate_and_fallback(self):
  old_cap=proxy.DEEPSEEK_MONTHLY_CAP
  proxy.DEEPSEEK_MONTHLY_CAP=5
  proxy.DEEPSEEK_SPEND.update(month='2026-09',start_balance=10,min_balance=4)
  state={'status':'ok','available':True,'balances':[{'currency':'USD','total_balance':'4'}]}
  with mock.patch.object(proxy,'DEEPSEEK_FALLBACK',True),mock.patch.object(proxy,'deepseek_key',return_value='key'),mock.patch.dict(proxy.PROVIDER_STATE,{'deepseek':state}),mock.patch.dict(proxy.ROUTES,{'claude-sonnet-5':[('deepseek','deepseek-v4-pro')]}):
   self.assertEqual(proxy.deepseek_candidate('deepseek-v4-pro',state)['reason'],'monthly cap')
   self.assertIsNone(proxy.fallback_target('claude-sonnet-5')[0])
  proxy.DEEPSEEK_MONTHLY_CAP=old_cap

class StarvationTests(unittest.TestCase):
 def test_counter_only_when_alternative_is_routable(self):
  old=(proxy.STARVED_COUNT,proxy.STARVED_LAST)
  try:
   with tempfile.TemporaryDirectory() as d:
    proxy.CONTROL_DIR=Path(d); proxy.USAGE_STATE_FILE=Path(d)/'usage.json'; proxy.ROUTING_LOG=Path(d)/'routing.log'
    proxy.STARVED_COUNT=0; proxy.STARVED_LAST=None
    with mock.patch.object(proxy,'route_payload',return_value={'first_routable':{'provider':'openai-codex'}}): proxy.record_starvation('claude-sonnet-5')
    self.assertEqual(proxy.STARVED_COUNT,1)
    self.assertEqual(proxy.STARVED_LAST['provider'],'openai-codex')
    self.assertEqual(json.loads(proxy.ROUTING_LOG.read_text())['kind'],'starved')
  finally: proxy.STARVED_COUNT,proxy.STARVED_LAST=old

if __name__=='__main__': unittest.main()
