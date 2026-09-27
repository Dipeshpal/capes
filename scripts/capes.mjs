#!/usr/bin/env node
// capes installer. No dependencies; needs Node 18+.
//   node scripts/capes.mjs install    deploy to your Vercel account, then connect your clients
//   node scripts/capes.mjs connect    connect clients to an existing deployment
//   node scripts/capes.mjs env        add or update service credentials on an existing deployment (never touches MCP_API_KEY)
// Flags: --name --discord --apify --gmail --gmail-password --telegram --url --key --clients desktop,claude-code,cursor,codex,none
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { createInterface } from 'node:readline/promises';

const WIN = process.platform === 'win32';
// View/Send/Threads/Embeds/Attach/History/Reactions + Manage Messages/Pin Messages/Channels/Roles/Threads/Webhooks, Audit Log, Invites, Kick/Ban/Timeout
const DISCORD_PERMISSIONS = '2253295267998935';
const SAVED = new URL('../.capes.local.json', import.meta.url);
const [cmd, ...rest] = process.argv.slice(2);
const flags = {};
for (let i = 0; i < rest.length; i++) if (rest[i].startsWith('--')) flags[rest[i].slice(2)] = rest[++i];

const rl = createInterface({ input: process.stdin, output: process.stdout });
const ask = async (q, def = '') => ((await rl.question(def ? `${q} [${def}]: ` : `${q}: `)).trim() || def);
const log = (m = '') => console.log(m);
const q = (s) => (WIN ? `"${s}"` : s);

function run(bin, args, opts = {}) {
  return spawnSync(bin, args, { encoding: 'utf8', shell: WIN, ...opts });
}
const has = (bin) => run(bin, ['--version']).status === 0;

// ---------------------------------------------------------------- env (add credentials to an existing deployment)
async function addEnv() {
  const vercel = has('vercel') ? ['vercel'] : ['npx', '-y', 'vercel'];
  const vc = (args, opts) => run(vercel[0], [...vercel.slice(1), ...args], opts);

  log('\ncapes: add or update service credentials on an existing deployment\n');
  log('This never touches MCP_API_KEY, so any client already connected keeps working.\n');
  if (vc(['whoami']).status !== 0) {
    log('Log in to Vercel (a browser window will open)...');
    if (vc(['login'], { stdio: 'inherit' }).status !== 0) throw new Error('Vercel login failed');
  }

  const name = flags.name ?? (await ask('Vercel project name (from your Vercel dashboard, or the URL: https://<this>.vercel.app)', 'capes'));
  log('\nCredentials to add or replace (press Enter to skip any):');
  const discord = flags.discord ?? (await ask('Discord bot token'));
  const apify = flags.apify ?? (await ask('Apify token (for X/Twitter search)'));
  const gmail = flags.gmail ?? (await ask('Gmail address'));
  const gmailPass = gmail ? (flags['gmail-password'] ?? (await ask('Gmail app password (myaccount.google.com/apppasswords)'))) : '';
  const telegram = flags.telegram ?? (await ask('Telegram bot token (from @BotFather)'));

  const env = {
    ...(discord && { DISCORD_BOT_TOKEN: discord }),
    ...(apify && { APIFY_TOKEN: apify }),
    ...(gmail && gmailPass && { GMAIL_ADDRESS: gmail, GMAIL_APP_PASSWORD: gmailPass }),
    ...(telegram && { TELEGRAM_BOT_TOKEN: telegram }),
  };
  if (!Object.keys(env).length) {
    log('Nothing entered, nothing changed.');
    return;
  }

  log('\nLinking Vercel project...');
  const link = vc(['link', '--yes', '--project', name]);
  if (link.status !== 0) throw new Error(`vercel link failed:\n${link.stderr || link.stdout}`);

  for (const [k, v] of Object.entries(env)) {
    vc(['env', 'rm', k, 'production', '--yes']);
    const r = vc(['env', 'add', k, 'production'], { input: v });
    if (r.status !== 0) throw new Error(`Could not set ${k}:\n${r.stderr || r.stdout}`);
    log(`  set ${k}`);
  }

  log('\nRedeploying so the new credentials take effect (about a minute)...');
  const dep = vc(['deploy', '--prod', '--yes']);
  if (dep.status !== 0) throw new Error(`Deploy failed:\n${dep.stderr || dep.stdout}`);
  log('\nDone. MCP_API_KEY and your connected clients are unchanged.');
  log('Open your dashboard\'s Connectors tab and click Test connection to confirm.');
}

// ---------------------------------------------------------------- install
async function install() {
  const vercel = has('vercel') ? ['vercel'] : ['npx', '-y', 'vercel'];
  const vc = (args, opts) => run(vercel[0], [...vercel.slice(1), ...args], opts);

  log('\ncapes installer\n');
  if (vc(['whoami']).status !== 0) {
    log('Log in to Vercel (a browser window will open)...');
    if (vc(['login'], { stdio: 'inherit' }).status !== 0) throw new Error('Vercel login failed');
  }

  const name = flags.name ?? (await ask('Vercel project name', 'capes'));
  log('\nCredentials (press Enter to skip any you do not need yet):');
  const discord = flags.discord ?? (await ask('Discord bot token'));
  const apify = flags.apify ?? (await ask('Apify token (for X/Twitter search)'));
  const gmail = flags.gmail ?? (await ask('Gmail address (optional)'));
  const gmailPass = gmail ? (flags['gmail-password'] ?? (await ask('Gmail app password (myaccount.google.com/apppasswords)'))) : '';
  const telegram = flags.telegram ?? (await ask('Telegram bot token (from @BotFather, optional)'));
  const key = randomBytes(32).toString('base64url');

  log('\nLinking Vercel project...');
  const link = vc(['link', '--yes', '--project', name]);
  if (link.status !== 0) throw new Error(`vercel link failed:\n${link.stderr || link.stdout}`);

  const env = {
    MCP_API_KEY: key,
    ...(discord && { DISCORD_BOT_TOKEN: discord }),
    ...(apify && { APIFY_TOKEN: apify }),
    ...(gmail && gmailPass && { GMAIL_ADDRESS: gmail, GMAIL_APP_PASSWORD: gmailPass }),
    ...(telegram && { TELEGRAM_BOT_TOKEN: telegram }),
  };
  for (const [k, v] of Object.entries(env)) {
    vc(['env', 'rm', k, 'production', '--yes']);
    const r = vc(['env', 'add', k, 'production'], { input: v });
    if (r.status !== 0) throw new Error(`Could not set ${k}:\n${r.stderr || r.stdout}`);
    log(`  set ${k}`);
  }

  log('\nDeploying (about a minute)...');
  const dep = vc(['deploy', '--prod', '--yes']);
  const out = `${dep.stdout}\n${dep.stderr}`;
  if (dep.status !== 0) throw new Error(`Deploy failed:\n${out}`);
  const depUrl = out.match(/https:\/\/[a-z0-9-]+\.vercel\.app/g)?.pop();
  const insp = vc(['inspect', depUrl]);
  const aliases = `${insp.stdout}\n${insp.stderr}`.match(/https:\/\/[a-z0-9-]+\.vercel\.app/g) ?? [];
  const url = aliases.find((a) => a === `https://${name}.vercel.app`) ?? aliases.sort((a, b) => a.length - b.length)[0] ?? depUrl;

  log(`Waiting for ${url} ...`);
  await verify(url, key);
  writeFileSync(SAVED, JSON.stringify({ url, key }, null, 2), { mode: 0o600 });
  log(`\nDeployed: ${url}`);
  log(`Dashboard: ${url}/dashboard  (sign in with your MCP API key)`);
  log('Optional, free: run `vercel integration add upstash` then `vercel deploy --prod` so the dashboard can save switches.');
  log(`Your MCP API key (also saved to .capes.local.json, which is git-ignored):\n  ${key}\n`);
  if (discord) {
    const seg = discord.split('.')[0];
    const clientId = Buffer.from(seg + '='.repeat((4 - (seg.length % 4)) % 4), 'base64').toString();
    log('Add your bot to a Discord server (or re-authorize it to grant these permissions).');
    log('Open this link as the server owner and click Authorize:');
    log(`  https://discord.com/oauth2/authorize?client_id=${clientId}&scope=bot&permissions=${DISCORD_PERMISSIONS}\n`);
  }
  await connect(url, key);
}

async function verify(url, key) {
  for (let i = 0; i < 12; i++) {
    try {
      const r = await fetch(`${url}/mcp`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }),
      });
      if (r.ok) {
        const t = (await r.json()).result.tools.map((x) => x.name);
        log(`Server is live. Tools: ${t.join(', ')}`);
        return;
      }
      if (r.status === 401 && i > 3) throw new Error('Got 401: turn off Vercel Deployment Protection for production (Project > Settings > Deployment Protection).');
    } catch (e) {
      if (String(e.message).startsWith('Got 401')) throw e;
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
  throw new Error('Server did not become healthy in time. Check `vercel logs`.');
}

// ---------------------------------------------------------------- connect
const readJson = (p) => (existsSync(p) ? JSON.parse(readFileSync(p, 'utf8').replace(/^\ufeff/, '')) : {});
function writeJson(p, obj) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(obj, null, 2) + '\n');
}

function desktopConfigPath() {
  if (flags['desktop-config']) return flags['desktop-config'];
  if (WIN) return join(process.env.APPDATA, 'Claude', 'claude_desktop_config.json');
  if (process.platform === 'darwin') return join(homedir(), 'Library', 'Application Support', 'Claude', 'claude_desktop_config.json');
  return join(homedir(), '.config', 'Claude', 'claude_desktop_config.json');
}

const CLIENTS = {
  desktop(url, key) {
    const p = desktopConfigPath();
    const cfg = readJson(p);
    cfg.mcpServers = {
      ...cfg.mcpServers,
      capes: {
        command: 'npx',
        args: ['-y', 'mcp-remote', `${url}/mcp`, '--header', 'Authorization:${AUTH_HEADER}'],
        env: { AUTH_HEADER: `Bearer ${key}` },
      },
    };
    writeJson(p, cfg);
    return `Claude Desktop: updated ${p}. Fully quit and reopen Claude Desktop.`;
  },
  'claude-code'(url, key) {
    if (!has('claude')) return 'Claude Code: `claude` not found. Run:\n  claude mcp add --scope user --transport http capes ' + `${url}/mcp --header "Authorization: Bearer ${key}"`;
    run('claude', ['mcp', 'remove', 'capes', '--scope', 'user']);
    const r = run('claude', ['mcp', 'add', '--scope', 'user', '--transport', 'http', 'capes', `${url}/mcp`, '--header', q(`Authorization: Bearer ${key}`)]);
    return r.status === 0 ? 'Claude Code: added "capes" (user scope).' : `Claude Code: failed\n${r.stderr || r.stdout}`;
  },
  cursor(url, key) {
    const p = join(homedir(), '.cursor', 'mcp.json');
    const cfg = readJson(p);
    cfg.mcpServers = { ...cfg.mcpServers, capes: { url: `${url}/mcp`, headers: { Authorization: `Bearer ${key}` } } };
    writeJson(p, cfg);
    return `Cursor: updated ${p}. Reload Cursor.`;
  },
  codex(url, key) {
    if (!has('codex')) return 'Codex: `codex` not found. Run:\n  codex mcp add capes --url ' + `${url}/mcp --bearer-token-env-var CAPES_MCP_API_KEY`;
    run('codex', ['mcp', 'remove', 'capes']);
    const r = run('codex', ['mcp', 'add', 'capes', '--url', `${url}/mcp`, '--bearer-token-env-var', 'CAPES_MCP_API_KEY']);
    if (r.status !== 0) return `Codex: failed\n${r.stderr || r.stdout}`;
    if (WIN) run('setx', ['CAPES_MCP_API_KEY', key]);
    return `Codex: added "capes".` + (WIN ? ' Set CAPES_MCP_API_KEY for your user; open a new terminal.' : `\n  Add to your shell profile:  export CAPES_MCP_API_KEY=${key}`);
  },
};

async function connect(url, key) {
  if (!url || !key) {
    const saved = existsSync(SAVED) ? JSON.parse(readFileSync(SAVED, 'utf8')) : {};
    url = flags.url ?? saved.url ?? (await ask('Server URL (https://<project>.vercel.app)'));
    key = flags.key ?? saved.key ?? (await ask('MCP API key'));
  }
  url = url.replace(/\/+$/, '').replace(/\/mcp$/, '');
  const pick = flags.clients ?? (await ask('Connect which clients? desktop,claude-code,cursor,codex (or none)', 'desktop,claude-code'));
  for (const c of pick.split(',').map((s) => s.trim()).filter((c) => c && c !== 'none')) {
    if (!CLIENTS[c]) log(`Unknown client: ${c}`);
    else log('\n' + CLIENTS[c](url, key));
  }
  log('\nDone. Try: "List my Discord channels"');
}

try {
  if (cmd === 'install') await install();
  else if (cmd === 'connect') await connect(flags.url, flags.key);
  else if (cmd === 'env') await addEnv();
  else log('Usage: node scripts/capes.mjs <install|connect|env>');
} catch (e) {
  console.error(`\nError: ${e.message}`);
  process.exitCode = 1;
} finally {
  rl.close();
}
