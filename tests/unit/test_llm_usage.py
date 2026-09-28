import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import llm_usage

class WeeklyReportTests(unittest.TestCase):
    def test_weekly_metrics_and_missing_class_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'usage.json'; log=root/'routing.log'
            state.write_text(json.dumps({'acct':{'input_tokens':100,'cache_read_input_tokens':300,'cache_creation_input_tokens':100}}))
            log.write_text('')
            payload={'usage_state_file':str(state),'routing_log':str(log),'tokens':[{'forecast':{'7d':{'forecast':'waste','projected_at_reset':.6}},'counters':{'input_tokens':100,'cache_read_input_tokens':300,'cache_creation_input_tokens':100}}], 'providers':{'openai-codex':{'forecast':{}}},'routing':{'starved':0}}
            with patch.object(llm_usage,'get_json',return_value=payload):
                result=llm_usage.weekly_report({})
            self.assertEqual(result['P1_starved_requests'],0)
            self.assertEqual(result['P2_weekly_waste_percent']['anthropic:7d'],'~40.0%')
            self.assertEqual(result['P4_opus_fable_token_share_percent'],'n/a')
            self.assertEqual(result['cache_hit_percent'],60)

if __name__ == '__main__': unittest.main()
