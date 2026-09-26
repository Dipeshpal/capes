(() => {
  'use strict';

  const TABS = [
    ['overview', 'Overview'],
    ['connectors', 'Connectors'],
    ['tools', 'Tools'],
    ['activity', 'Activity'],
    ['connect', 'Connect a client'],
    ['settings', 'Settings'],
  ];
  const $ = (id) => document.getElementById(id);
  const app = { csrf: null, data: null, tab: 'overview', filter: { text: '', kind: '', connector: '' }, tests: {} };

  // ---- DOM helper: every value is inserted as text, so data can never become markup ----
  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      el.append(c.nodeType ? c : document.createTextNode(String(c)));
    }
    return el;
  }

  function toast(message) {
    const t = $('toast');
    t.textContent = message;
    t.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { t.hidden = true; }, 3500);
  }

  async function api(path, options = {}) {
    const headers = { Accept: 'application/json' };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (options.method && options.method !== 'GET' && app.csrf) headers['X-CSRF-Token'] = app.csrf;
    const res = await fetch('/dashboard/api' + path, {
      method: options.method || 'GET',
      headers,
      credentials: 'same-origin',
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (_) { /* empty body */ }
    if (res.status === 401) { showLogin(); throw new Error('Signed out'); }
    if (!res.ok) throw new Error((data && data.detail) || res.statusText || 'Request failed');
    return data;
  }

  // ---- login / session ----
  function showLogin() {
    app.csrf = null;
    $('shell').hidden = true;
    $('login').hidden = false;
    $('key').focus();
  }

  async function boot() {
    try {
      const s = await api('/session');
      if (s.authenticated) { app.csrf = s.csrf; await load(); } else showLogin();
    } catch (_) { showLogin(); }
  }

  $('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const err = $('login-error');
    err.hidden = true;
    try {
      const s = await api('/login', { method: 'POST', body: { key: $('key').value } });
      $('key').value = '';
      app.csrf = s.csrf;
      await load();
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    }
  });

  $('logout').addEventListener('click', async () => {
    try { await api('/logout', { method: 'POST', body: {} }); } catch (_) { /* already signed out */ }
    showLogin();
  });

  async function load() {
    app.data = await api('/state');
    $('login').hidden = true;
    $('shell').hidden = false;
    renderTabs();
    render();
  }

  // ---- navigation ----
  function renderTabs() {
    const nav = $('tabs');
    nav.replaceChildren(...TABS.map(([id, label]) => h('button', {
      class: 'tab', role: 'tab', type: 'button', 'aria-selected': String(app.tab === id),
      onclick: () => { app.tab = id; renderTabs(); render(); },
    }, label)));
  }

  function render() {
    const main = $('main');
    const views = { overview, connectors, tools, activity, connect, settings };
    main.replaceChildren();
    Promise.resolve(views[app.tab]()).then((node) => main.replaceChildren(node)).catch((ex) => main.replaceChildren(h('p', { class: 'error', text: ex.message })));
  }

  const badge = (text, cls) => h('span', { class: 'badge ' + (cls || ''), text });

  // ---- settings persistence ----
  function currentSettings() {
    const d = app.data;
    return {
      read_only: d.settings.read_only,
      disabled_tools: d.tools.filter((t) => t.disabled).map((t) => t.name),
      disabled_connectors: d.connectors.filter((c) => !c.enabled).map((c) => c.id),
    };
  }

  async function save(mutator) {
    const s = currentSettings();
    mutator(s);
    try {
      await api('/settings', { method: 'PUT', body: s });
      await load();
      toast('Saved');
    } catch (ex) {
      toast(ex.message);
      await load();
    }
  }

  const editHint = () => (app.data.settings.can_edit ? null : h('p', { class: 'muted small', text: 'Switches are locked here: limits come from environment variables (see Settings for how to set them).' }));

  // ---- views ----
  function overview() {
    const d = app.data;
    const configured = d.connectors.filter((c) => c.configured).length;
    const cards = h('div', { class: 'grid' },
      h('div', { class: 'card' }, h('div', { class: 'muted', text: 'Tools available to clients' }), h('div', { class: 'stat', text: `${d.server.tools_enabled} / ${d.server.tools_total}` })),
      h('div', { class: 'card' }, h('div', { class: 'muted', text: 'Connectors configured' }), h('div', { class: 'stat', text: `${configured} / ${d.connectors.length}` })),
      h('div', { class: 'card' }, h('div', { class: 'muted', text: 'Mode' }), h('div', { class: 'stat', text: d.settings.read_only ? 'Read-only' : 'Full access' }),
        h('p', { class: 'muted small', text: d.settings.read_only ? 'Tools that change things are hidden from clients.' : 'Clients can use write and destructive tools.' })),
    );
    const notes = [];
    if (d.settings.degraded) notes.push(h('div', { class: 'banner bad', text: 'Settings storage is unreachable. The server is using the last known settings, or read-only mode if there are none.' }));
    const missing = d.connectors.filter((c) => !c.configured);
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Overview' })),
      ...notes, cards,
      h('div', { class: 'card stack' },
        h('h3', { text: 'Your MCP endpoint' }),
        h('p', { class: 'muted', text: 'Point any MCP client here with the header Authorization: Bearer <your MCP_API_KEY>.' }),
        h('div', { class: 'row' }, h('code', { text: d.server.mcp_url }), h('button', { class: 'btn small', type: 'button', onclick: () => copy(d.server.mcp_url) }, 'Copy')),
      ),
      missing.length ? h('div', { class: 'card stack' }, h('h3', { text: 'Finish setting up' }),
        ...missing.map((c) => h('p', {}, `${c.name}: set ${c.missing_env.join(', ')} on Vercel. `, h('a', { href: c.guide, target: '_blank', rel: 'noopener noreferrer' }, 'Setup guide')))) : null,
    );
  }

  function connectors() {
    const d = app.data;
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Connectors' }), editHint()),
      h('div', { class: 'grid' }, d.connectors.map((c) => {
        const result = app.tests[c.id];
        return h('div', { class: 'card stack' },
          h('div', { class: 'row between' }, h('h3', { text: c.name }), badge(c.configured ? 'Configured' : 'Not configured', c.configured ? 'ok' : 'warn')),
          h('p', { class: 'muted', text: c.summary }),
          h('div', { class: 'row' }, badge(`${c.kinds.read} read`, 'read'), badge(`${c.kinds.write} write`, 'write'), badge(`${c.kinds.destructive} destructive`, 'destructive')),
          c.configured ? null : h('p', { class: 'small', text: 'Missing: ' + c.missing_env.join(', ') }),
          h('div', { class: 'row between' },
            h('label', { class: 'row', for: 'en-' + c.id }, h('input', {
              id: 'en-' + c.id, class: 'switch', type: 'checkbox', checked: c.enabled, disabled: !app.data.settings.can_edit || c.locked,
              onchange: (e) => save((s) => { s.disabled_connectors = s.disabled_connectors.filter((x) => x !== c.id); if (!e.target.checked) s.disabled_connectors.push(c.id); }),
            }), h('span', { text: c.locked ? 'Enabled (locked by environment)' : 'Enabled' })),
            h('div', { class: 'row' },
              h('button', { class: 'btn small', type: 'button', disabled: !c.configured, onclick: () => testConnector(c.id) }, 'Test connection'),
              h('a', { class: 'btn small', href: c.guide, target: '_blank', rel: 'noopener noreferrer' }, 'Guide'))),
          result ? h('p', { class: result.ok ? 'small' : 'small error', text: (result.ok ? 'OK: ' : 'Failed: ') + result.detail }) : null,
        );
      })),
    );
  }

  async function testConnector(id) {
    app.tests[id] = { ok: true, detail: 'Testing...' };
    render();
    try { app.tests[id] = await api('/test/' + id, { method: 'POST', body: {} }); } catch (ex) { app.tests[id] = { ok: false, detail: ex.message }; }
    render();
  }

  function tools() {
    const d = app.data;
    const f = app.filter;
    const filterBar = h('div', { class: 'row' },
      h('input', { type: 'text', placeholder: 'Filter tools', 'aria-label': 'Filter tools', value: f.text, oninput: (e) => { f.text = e.target.value; fillRows(); } }),
      h('select', { 'aria-label': 'Filter by kind', onchange: (e) => { f.kind = e.target.value; render(); } },
        ...[['', 'All kinds'], ['read', 'Read'], ['write', 'Write'], ['destructive', 'Destructive']].map(([v, l]) => h('option', { value: v, selected: f.kind === v }, l))),
      h('select', { 'aria-label': 'Filter by connector', onchange: (e) => { f.connector = e.target.value; render(); } },
        h('option', { value: '', selected: !f.connector }, 'All connectors'),
        ...d.connectors.map((c) => h('option', { value: c.id, selected: f.connector === c.id }, c.name))));
    const tbody = h('tbody');
    function fillRows() {
      const shown = d.tools.filter((t) =>
        (!f.kind || t.kind === f.kind) && (!f.connector || t.connector === f.connector) &&
        (!f.text || (t.name + ' ' + t.description).toLowerCase().includes(f.text.toLowerCase())));
      tbody.replaceChildren(...shown.map((t) => h('tr', { class: t.enabled ? '' : 'off' },
        h('td', {}, h('input', {
          class: 'switch', type: 'checkbox', checked: !t.disabled, 'aria-label': 'Enable ' + t.name, disabled: !d.settings.can_edit || t.locked,
          onchange: (e) => save((s) => { s.disabled_tools = s.disabled_tools.filter((x) => x !== t.name); if (!e.target.checked) s.disabled_tools.push(t.name); }),
        })),
        h('td', {}, h('code', { text: t.name }), t.blocked_reason ? h('div', { class: 'muted small', text: t.blocked_reason }) : null),
        h('td', {}, badge(t.kind, t.kind)),
        h('td', { class: 'muted', text: t.description }),
        h('td', {}, t.kind === 'read' ? h('button', { class: 'btn small', type: 'button', disabled: !t.enabled, onclick: () => openTry(t) }, 'Try') : null))));
      count.textContent = `${shown.length} of ${d.tools.length} tools`;
    }
    const count = h('span', { class: 'muted' });
    fillRows();
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Tools' }), count, editHint()),
      filterBar,
      h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { text: 'On' }), h('th', { text: 'Tool' }), h('th', { text: 'Kind' }), h('th', { text: 'What it does' }), h('th', { text: '' }))), tbody)),
      h('p', { class: 'muted small', text: 'Try runs read-only tools with your real credentials. Write and destructive tools cannot be run from the dashboard.' }),
    );
  }

  async function activity() {
    const a = await api('/activity');
    const note = a.source === 'kv' ? 'Stored in Redis (last 100 calls).' : 'Kept in memory on the server instance only (resets on cold start). Add Redis for a durable log.';
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Activity' }), h('button', { class: 'btn small', type: 'button', onclick: render }, 'Refresh')),
      h('p', { class: 'muted', text: note + ' Only tool names, times and outcomes are recorded, never arguments or results.' }),
      a.entries.length ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Time (UTC)', 'Tool', 'Source', 'Result', 'ms'].map((x) => h('th', { text: x })))),
        h('tbody', {}, a.entries.map((e) => h('tr', {}, h('td', { class: 'mono', text: e.ts.replace('T', ' ').replace('+00:00', '') }), h('td', {}, h('code', { text: e.tool })), h('td', { text: e.source }),
          h('td', {}, e.ok ? badge('ok', 'ok') : badge('error', 'bad'), e.error ? h('div', { class: 'muted small', text: e.error }) : null), h('td', { text: String(e.ms) })))))) : h('p', { class: 'muted', text: 'No calls recorded yet.' }),
    );
  }

  function snippet(title, text) {
    return h('div', { class: 'stack' }, h('h3', { text: title }), h('div', { class: 'snippet' }, h('pre', {}, h('code', { text })), h('button', { class: 'btn small', type: 'button', onclick: () => copy(text) }, 'Copy')));
  }

  function connect() {
    const url = app.data.server.mcp_url;
    const desktop = JSON.stringify({ mcpServers: { pulse: { command: 'npx', args: ['-y', 'mcp-remote', url, '--header', 'Authorization:${AUTH_HEADER}'], env: { AUTH_HEADER: 'Bearer YOUR_MCP_API_KEY' } } } }, null, 2);
    const cursor = JSON.stringify({ mcpServers: { pulse: { url, headers: { Authorization: 'Bearer YOUR_MCP_API_KEY' } } } }, null, 2);
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Connect a client' })),
      h('p', { class: 'muted', text: 'Replace YOUR_MCP_API_KEY with your key. The dashboard never displays it. Restart the client afterwards.' }),
      snippet('Claude Code', `claude mcp add --scope user --transport http pulse ${url} --header "Authorization: Bearer YOUR_MCP_API_KEY"`),
      snippet('Claude Desktop (claude_desktop_config.json, needs Node.js)', desktop),
      snippet('Cursor (~/.cursor/mcp.json)', cursor),
      snippet('Codex', `codex mcp add pulse --url ${url} --bearer-token-env-var PULSE_MCP_API_KEY`),
    );
  }

  function settings() {
    const d = app.data;
    return h('div', { class: 'stack' },
      h('div', { class: 'section-head' }, h('h1', { text: 'Settings' })),
      h('div', { class: 'card stack' },
        h('h3', { text: 'Read-only mode' }),
        h('p', { class: 'muted', text: 'Hides every tool that sends, changes or deletes something. Clients can only read. Useful when you want an assistant to look but never act.' }),
        h('label', { class: 'row', for: 'ro' }, h('input', {
          id: 'ro', class: 'switch', type: 'checkbox', checked: d.settings.read_only, disabled: !d.settings.can_edit || d.settings.read_only_locked,
          onchange: (e) => save((s) => { s.read_only = e.target.checked; }),
        }), h('span', { text: d.settings.read_only_locked ? 'On (locked by PULSE_READ_ONLY)' : d.settings.read_only ? 'On' : 'Off' }))),
      h('div', { class: 'card stack' },
        h('h3', { text: 'Where settings live' }),
        d.settings.can_edit
          ? h('p', { text: 'A Redis database is connected, so switches on this page are saved and take effect within about 10 seconds.' })
          : h('div', { class: 'stack' },
            h('p', { text: 'No database needed. This server stores nothing: your credentials and limits are Vercel environment variables. To restrict what assistants can do, set any of these on Vercel and redeploy:' }),
            h('div', { class: 'snippet' }, h('pre', {}, h('code', { text: 'PULSE_READ_ONLY=1\nPULSE_DISABLED_CONNECTORS=discord\nPULSE_DISABLED_TOOLS=gmail_trash,discord_delete_channel' }))),
            h('p', { class: 'muted small', text: 'Optional: connect a free Redis database (vercel integration add upstash) only if you want to flip switches from this page without redeploying.' }))),
      h('div', { class: 'card stack' },
        h('h3', { text: 'Security' }),
        h('p', { class: 'muted', text: `You stay signed in for ${d.settings.session_hours} hours, then you sign in again with your key. You never need to change the key on a schedule; change it only if you think it leaked (that also signs everyone out). Anyone with the key controls your connected accounts, so keep it private.` }),
        h('button', { class: 'btn', type: 'button', onclick: () => $('logout').click() }, 'Sign out')),
    );
  }

  // ---- try a read-only tool ----
  function openTry(t) {
    $('try-title').textContent = t.name;
    $('try-desc').textContent = t.description;
    const form = $('try-form');
    const out = $('try-output');
    out.hidden = true;
    const props = t.schema.properties || {};
    const required = new Set(t.schema.required || []);
    const fields = Object.entries(props).map(([name, spec]) => {
      const id = 'f-' + name;
      let input;
      if (spec.enum) input = h('select', { id, name }, h('option', { value: '' }, '(default)'), ...spec.enum.map((v) => h('option', { value: v }, v)));
      else if (spec.type === 'boolean') input = h('input', { id, name, type: 'checkbox' });
      else if (spec.type === 'integer') input = h('input', { id, name, type: 'number' });
      else if (spec.type === 'array' || spec.type === 'object') input = h('textarea', { id, name, placeholder: 'JSON' });
      else input = h('input', { id, name, type: 'text', autocomplete: 'off' });
      return h('div', {}, h('label', { for: id, text: name + (required.has(name) ? ' *' : '') }), input, spec.description ? h('div', { class: 'muted small', text: spec.description }) : null);
    });
    form.replaceChildren(...fields, h('button', { class: 'btn primary', type: 'submit' }, 'Run'));
    form.onsubmit = async (e) => {
      e.preventDefault();
      const args = {};
      for (const [name, spec] of Object.entries(props)) {
        const el = form.elements[name];
        if (!el) continue;
        if (spec.type === 'boolean') { if (el.checked) args[name] = true; continue; }
        if (el.value === '') continue;
        if (spec.type === 'integer') args[name] = Number(el.value);
        else if (spec.type === 'array' || spec.type === 'object') {
          try { args[name] = JSON.parse(el.value); } catch (_) { toast(`${name} must be valid JSON`); return; }
        } else args[name] = el.value;
      }
      out.hidden = false;
      out.textContent = 'Running...';
      try {
        const r = await api('/run', { method: 'POST', body: { tool: t.name, arguments: args } });
        out.textContent = (r.ok ? '' : 'Error: ') + r.output + (r.truncated ? '\n\n[output truncated]' : '');
        await refreshQuiet();
      } catch (ex) { out.textContent = 'Error: ' + ex.message; }
    };
    $('try-dialog').showModal();
  }

  async function refreshQuiet() { try { app.data = await api('/state'); } catch (_) { /* ignore */ } }

  async function copy(text) {
    try { await navigator.clipboard.writeText(text); toast('Copied'); } catch (_) { toast('Copy failed: select the text manually'); }
  }

  boot();
})();
