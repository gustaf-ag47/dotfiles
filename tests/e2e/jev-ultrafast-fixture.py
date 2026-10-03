#!/usr/bin/env python3
"""Opt-in live integration check on an OWNED about:blank tab with fixed synthetic HTML.

Run with the pinned upstream venv, BU_CDP_URL/BU_CDP_WS pointing to an explicitly
chosen automation browser, and --allow-model-calls. Uses real Jev + Pi typing;
never navigates an account/site or submits a network form. Ordinary skill runs
retain their human approval gate; this test authorizes only its own fixture nodes.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

HTML = '''<!doctype html><html><head><title>Dotfiles Jev integration fixture</title></head>
<body><h1>Synthetic city verification</h1><p>Enter the requested city, then verify it.</p>
<label for="city">City</label><input id="city" name="city" type="text" autocomplete="off">
<button id="verify" type="button">Verify city</button><p id="result">Not verified</p>
<script>document.querySelector('#verify').onclick=()=>{
 document.querySelector('#result').textContent='Verified city: '+document.querySelector('#city').value;
};</script></body></html>'''
GOAL = 'Enter London in the City field, click Verify city, and finish only when the page says Verified city: London.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-model-calls', action='store_true')
    args = parser.parse_args()
    if not args.allow_model_calls:
        print('SKIP: explicit --allow-model-calls required; no browser or API accessed.')
        return 0
    if os.environ.get('BU_BROWSER_ID') or not (os.environ.get('BU_CDP_URL') or os.environ.get('BU_CDP_WS')):
        raise SystemExit('Choose an explicit CDP automation browser; cloud/default browser discovery is disabled.')
    root = Path(os.environ.get('DOTFILES', str(Path(__file__).resolve().parents[2])))
    sys.path.insert(0, str(root / 'config/pi/skills/jev-ultrafast/scripts'))
    from run import resolve_typesafe_key
    from _text_backend import resolve_text_backend
    from _pi_text import configure_text_backend
    if resolve_text_backend(os.environ)['status'] != 'pi_configured':
        raise SystemExit('Pi typing must be explicitly configured before this test.')
    key = resolve_typesafe_key(os.environ)
    if not key:
        raise SystemExit('TypeSafe credential unavailable; no browser opened.')
    os.environ['TYPESAFE_API_KEY'] = key
    name = 'dotfiles-e2e-' + uuid.uuid4().hex[:10]
    os.environ['BU_NAME'] = name
    os.environ['BH_UPDATE_CHECK'] = '0'
    from browser_harness.admin import ensure_daemon, restart_daemon
    import jev_ultrafast.agent as module
    configure_text_backend(module)
    original_text = module.field_text
    text_count = 0
    def checked_text(context):
        nonlocal text_count
        text_count += 1
        if text_count > 2:
            raise RuntimeError('typing_call_budget_exceeded')
        text, metadata = original_text(context)
        if text != 'London':
            raise RuntimeError('unexpected_synthetic_value')
        return text, metadata
    module.field_text = checked_text
    def timeout(_signum, _frame):
        raise TimeoutError('test_deadline')
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(75)
    agent = None
    started = time.monotonic()
    operations = []
    passed = False
    cleanup_ok = True
    try:
        ensure_daemon(wait=15)
        agent = module.Agent('about:blank', GOAL)
        frame = agent.browser.call('Page.getFrameTree')['frameTree']['frame']['id']
        agent.browser.call('Page.setDocumentContent', frameId=frame, html=HTML)
        agent.state['page'] = agent.browser.observe(screenshot=False)
        for _ in range(6):
            agent.command('predict')
            decision = agent.state['decision']
            op = decision['operation']
            operations.append(op)
            if op == 'DONE':
                actual = agent.browser.evaluate("({value:document.querySelector('#city').value,result:document.querySelector('#result').textContent})")
                if actual != {'value': 'London', 'result': 'Verified city: London'}:
                    raise RuntimeError('done_without_independent_evidence')
            elif op == 'BLOCKED':
                raise RuntimeError('fixture_blocked')
            else:
                action = next(a for a in agent.state['page']['actions'] if a['id'] == decision['choice'])
                if action['kind'] != 'wait':
                    node = action.get('node')
                    if type(node) is not int or action['kind'] not in ('click', 'fill'):
                        raise RuntimeError('unexpected_fixture_action')
                    element_id = agent.browser.evaluate(f"window.__jevFast.nodes.get({node})?.id")
                    if element_id not in ('city', 'verify') or (action['kind'] == 'fill' and element_id != 'city'):
                        raise RuntimeError('action_outside_fixture')
            agent.command('act', {'fingerprint': agent.state['page']['fingerprint']})
            if agent.state['status'] == 'done':
                passed = True
                break
        if not passed:
            raise RuntimeError('fixture_step_budget_exceeded')
    except Exception as error:
        # Do not print provider bodies, field values, or credentials on failure.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'operations': operations}))
    finally:
        signal.alarm(0)
        if agent is not None:
            try: agent.close()
            except Exception: cleanup_ok = False
        try: restart_daemon(name)
        except Exception: cleanup_ok = False
    if passed:
        print(json.dumps({'status': 'pass', 'independent_dom_verified': True,
                          'operations': operations, 'jev_calls': len(operations), 'pi_text_calls': text_count,
                          'elapsed_ms': round((time.monotonic() - started) * 1000),
                          'owned_tab_and_daemon_closed': cleanup_ok}))
    return 0 if passed and cleanup_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
