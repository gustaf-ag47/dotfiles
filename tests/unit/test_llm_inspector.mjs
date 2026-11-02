import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { TABS, safe, age, originFrom, poolEnabled, fetchSnapshot, remaining, statusLine, renderPanel, registerInspectorStatus } from '../../config/pi/lib/llm-inspector.mjs';
import extension from '../../config/pi/extensions/llm-usage.ts';
const snapshot = () => ({ schema: 'llm-inspector.v1', host: 'test', generated_at: Date.now()/1000,
  accounts: [{ id: 'a', label: 'personal', auth: 'accepted', state: 'ROUTABLE', windows: [
    { name: '7d', remaining_percent: 64, source: 'header estimate', reset_at: 10**11, observed_at: 1000 }] }],
  session: { model: 'claude-opus', class: 'interactive', last_served: null },
  routing: { account_preview: { would_pick: 'a', ranking: [{fp:'a',eligible:true}] } }, config: {}, providers: {} });
const view = () => ({ snapshot: snapshot(), session: { model: 'claude-opus', provider: 'anthropic', pool: true }, extensions: {}, events: [] });

test('read-only fetch is loopback, bounded, rejects redirects and schema', async () => {
  let url, options;
  const s = await fetchSnapshot('http://127.0.0.1:8788', {id:'pi-test'}, async (u,o) => { url=u; options=o; return new Response(JSON.stringify(snapshot())); });
  assert.equal(s.host, 'test'); assert.match(url,/session=pi-test/); assert.equal(options.redirect,'error');
  await assert.rejects(fetchSnapshot('http://example.com', {}, () => { throw Error('must not fetch'); }), /loopback/);
  await assert.rejects(fetchSnapshot('http://localhost', {}, async () => new Response('{}')), /Invalid/);
  await assert.rejects(fetchSnapshot('http://localhost', {}, async () => new Response('x'.repeat(1024*1024+1))), /too large/);
});
test('safe text redacts secrets and terminal control sequences', () => {
  assert.equal(safe('sk-ant-oat-secret'), '[redacted]'); assert.ok(!safe('\x1b]0;bad\x07').includes('\x1b'));
  assert.equal(poolEnabled({PI_ANTHROPIC_POOL:'off'}),false);
  assert.throws(() => originFrom({PI_ANTHROPIC_PROXY_URL:'http://user:pass@localhost'}));
});
test('preview is never used as last-served attribution', () => {
  assert.match(statusLine(view()), /account unknown/);
  assert.ok(!statusLine(view()).includes('personal'));
  const v=view(); v.snapshot.session.last_served={account:'a',label:'personal',accepted_at:1000};
  assert.match(statusLine(v),/last: personal/);
});
test('unknown, expired and stale never become available quota', () => {
  assert.equal(remaining({remaining_percent:64,reset_at:1}), '?');
  assert.equal(remaining({}), '?'); assert.equal(age(null),'?');
  const v=view(); v.error='offline';
  assert.match(statusLine(v),/UNREACHABLE/);
  assert.match(renderPanel(v,'Accounts').join('\n'), /STALE/);
});
test('direct transport does not imply local proxy is serving session', () => {
  const v=view(); v.session.provider='openai-codex'; v.error='offline';
  assert.match(statusLine(v),/direct/); assert.ok(!statusLine(v).includes('proxy UNREACHABLE'));
});
test('account details expand only for the selected explicit account', () => {
  const v = { ...view(), accountSelection: 0 };
  assert.ok(!renderPanel(v, 'Accounts').join('\n').includes('64%'));
  assert.match(renderPanel({ ...v, expandedAccount: 'a' }, 'Accounts').join('\n'), /64%/);
});
test('all tabs handle initial and populated snapshots', () => {
  for (const tab of TABS) {
    assert.ok(Array.isArray(renderPanel(view(),tab)));
    assert.ok(Array.isArray(renderPanel({extensions:{}},tab)));
  }
});
test('fleet does not sum shared quota; stale host and config differences visible', () => {
  const v=view(); const a=snapshot(), b=snapshot();
  a.config={tables:{routes:{loaded_revision:'A'}}}; b.config={tables:{routes:{loaded_revision:'B'}}};
  v.fleet={local:{snapshot:a,fetched_at:100},remote:{snapshot:b,fetched_at:50,error:'offline'}};
  const out=renderPanel(v,'Fleet').join('\n');
  assert.match(out,/NOT additional quota/); assert.match(out,/DIFFERS/); assert.match(out,/STALE/);
});
function bus() { const emitter=new EventEmitter(); return { emit:(...args)=>emitter.emit(...args), on:(name,fn)=>{emitter.on(name,fn);return()=>emitter.off(name,fn);}, count:()=>emitter.listenerCount('llm:status-request') }; }
test('status publishers clean up and reattach on session lifecycle', () => {
  const handlers={}, events=bus(), reports=[];
  const pi={events,on:(name,fn)=>{handlers[name]=fn;}};
  events.on('llm:status',r=>reports.push(r));
  registerInspectorStatus(pi,'owner',()=>({mode:'local'}));
  assert.equal(events.count(),0); handlers.session_start(); assert.equal(events.count(),1);
  events.emit('llm:status-request',{}); assert.equal(reports.length,2);
  handlers.session_shutdown(); assert.equal(events.count(),0);
  handlers.session_start(); assert.equal(events.count(),1); handlers.session_shutdown();
});
test('extension factory starts no timer/network; lifecycle aborts fetch and removes statuses', async () => {
  const handlers={}, commands={}, events=bus(), statuses=[];
  extension({events,on:(name,fn)=>handlers[name]=fn,registerCommand:(name,opts)=>commands[name]=opts,exec:()=>{throw Error('unexpected command');}});
  assert.ok(commands.llm); assert.ok(commands.usage);
  const oldFetch=globalThis.fetch;
  let signal;
  globalThis.fetch=async (_url,opts)=>{signal=opts.signal; return new Response(JSON.stringify(snapshot()));};
  const ctx={mode:'tui',model:{provider:'anthropic',id:'claude-opus'},sessionManager:{getSessionId:()=> 'test'},ui:{setStatus:(...a)=>statuses.push(a)}};
  try {
    handlers.session_start({},ctx);
    await new Promise(r=>setTimeout(r,20));
    assert.ok(statuses.some(([k,v])=>k==='llm' && v));
    handlers.session_shutdown(); assert.equal(signal.aborted,true);
    assert.deepEqual(statuses.at(-1),['llm',undefined]);
  } finally { handlers.session_shutdown(); globalThis.fetch=oldFetch; }
});
test('noninteractive startup does not poll', () => {
  const handlers={}, events=bus(); let calls=0;
  extension({events,on:(n,f)=>handlers[n]=f,registerCommand:()=>{}});
  const old=globalThis.fetch; globalThis.fetch=()=>{calls++;throw Error();};
  try { handlers.session_start({}, {mode:'json'}); assert.equal(calls,0); handlers.session_shutdown(); }
  finally { globalThis.fetch=old; }
});
