// Isolated real Pi SDK worker, with a loopback-only deterministic model. No credentials.
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as net from 'node:net';
import * as http from 'node:http';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
let duplicate;
process.title = 'pi';
const [root, label, sdkPath, initialFile] = process.argv.slice(2);
const sdk = await import(pathToFileURL(sdkPath));
const { createAgentSessionServices, createAgentSessionFromServices, createAgentSessionRuntime, SessionManager, SettingsManager } = sdk;
const cwd = path.join(root, 'cwd'), agentDir = path.join(root, label);
fs.mkdirSync(agentDir, { recursive: true });
const modelServer = http.createServer((req, res) => {
  let body = '';
  req.on('data', chunk => { body += chunk; });
  req.on('end', () => {
    res.writeHead(200, { 'content-type': 'text/event-stream' });
    const frame = (delta, finish_reason = null) => res.write('data: ' + JSON.stringify({ id: 'fixture', object: 'chat.completion.chunk', choices: [{ index: 0, delta, finish_reason }] }) + '\n\n');
    frame({ role: 'assistant', content: 'fixture ACK' });
    const last = JSON.parse(body).messages?.at(-1)?.content;
    const hold = last === 'HOLD_FIXTURE' || (Array.isArray(last) && last.some(x => x.text === 'HOLD_FIXTURE'));
    if (!hold) { frame({}, 'stop'); res.end('data: [DONE]\n\n'); }
  });
});
await new Promise(resolve => modelServer.listen(0, '127.0.0.1', resolve));
fs.writeFileSync(path.join(agentDir, 'models.json'), JSON.stringify({ providers: { fixture: {
  baseUrl: `http://127.0.0.1:${modelServer.address().port}/v1`, api: 'openai-completions', apiKey: 'test',
  models: [{ id: 'fixture', name: 'fixture', reasoning: false, input: ['text'], contextWindow: 32000, maxTokens: 100,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } }],
} } }));
const records = [];
const create = async ({ sessionManager, sessionStartEvent }) => {
  const services = await createAgentSessionServices({ cwd, agentDir,
    settingsManager: SettingsManager.inMemory({ defaultProvider: 'fixture', defaultModel: 'fixture', compaction: { enabled: false }, retry: { enabled: false } }),
    resourceLoaderOptions: { noExtensions: false, noSkills: true, noPromptTemplates: true, noThemes: true,
      additionalExtensionPaths: [path.resolve('config/pi/extensions/delegate-mailbox.ts'), path.resolve('config/pi/extensions/tmux-pane-session.ts')] },
  });
  // Persist a header for brand-new sessions without making any model request.
  if (!fs.existsSync(sessionManager.getSessionFile())) sessionManager.appendMessage({ role: 'user', content: 'fixture seed', timestamp: Date.now() });
  const result = await createAgentSessionFromServices({ services, sessionManager, sessionStartEvent, tools: [], thinkingLevel: 'off' });
  if (result.extensionsResult.errors.length) throw new Error(JSON.stringify(result.extensionsResult.errors));
  return { ...result, services };
};
const runtime = await createAgentSessionRuntime(create, { cwd, agentDir,
  sessionManager: initialFile ? SessionManager.open(initialFile) : SessionManager.create(cwd, path.join(root, 'sessions')),
});
async function bind() {
  runtime.session.subscribe(event => {
    if (event.type === 'message_start' && event.message.role === 'custom') {
      records.push({ session: runtime.session.sessionId, recipient: event.message.details?.recipient_session_id, record: event.message.details?.record });
    }
  });
  await runtime.session.bindExtensions({});
}
await bind();
const state = () => ({ id: runtime.session.sessionId, file: runtime.session.sessionFile, records, busy: runtime.session.isStreaming });
const control = net.createServer(socket => {
  let input = '';
  socket.on('data', async data => {
    input += data;
    if (!input.includes('\n')) return;
    try {
      const cmd = JSON.parse(input.trim());
      if (cmd.op === 'new') { await runtime.newSession(); await bind(); }
      if (cmd.op === 'resume') { await runtime.switchSession(cmd.file); await bind(); }
      if (cmd.op === 'fork') {
        const entry = runtime.session.sessionManager.appendCustomEntry('fork-point', {});
        await runtime.fork(entry, { position: 'at' }); await bind();
      }
      if (cmd.op === 'busy') void runtime.session.prompt('HOLD_FIXTURE').catch(() => {});
      if (cmd.op === 'duplicate') duplicate = spawn(process.execPath, [cmd.file], { stdio: 'inherit' });
      if (cmd.op === 'settle') await runtime.session.waitForIdle();
      socket.end(JSON.stringify(state()) + '\n');
      if (cmd.op === 'quit') {
        duplicate?.kill();
        await runtime.dispose(); control.close(); modelServer.closeAllConnections(); modelServer.close();
      }
    } catch (error) { socket.end(JSON.stringify({ error: String(error.stack) }) + '\n'); }
  });
});
control.listen(path.join(root, label + '.sock'), () => fs.writeFileSync(path.join(root, label + '.ready'), 'ready'));
