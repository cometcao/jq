/**
 * Host half of @local/dsh-market-state.
 *
 * Serves the six-ring state parsed from `reports/<as-of>-market-state.md` and
 * `reports/<as-of>-sector-<target>-state.md` on an exact route of the shared
 * web server, and rebuilds those reports with `scripts/state.py` when the
 * panel asks for a refresh. Data and scripts stay in the workspace: this
 * plugin only reads them.
 */
import { readdir, readFile } from 'node:fs/promises'
import { spawn } from 'node:child_process'
import { join } from 'node:path'

/** Exact route the panel fetches; distinct from every host route. */
const ROUTE_PATH = '/dsh-market-state/state'

/** Workspace holding reports/, scripts/ and data/; override without editing the package. */
const WORKSPACE = process.env.DSH_MARKET_STATE_WORKSPACE ?? 'C:\\Users\\comet\\git\\jq\\chan_py\\system'

/** Interpreter that can run scripts/state.py; `python` is not on PATH on this machine. */
const PYTHON = process.env.DSH_MARKET_STATE_PYTHON ?? 'C:\\miniconda3\\envs\\py311\\python.exe'

/** A rebuild reads stored facts only, but a cold start can be slow; never hang a request. */
const REFRESH_TIMEOUT_MS = 120_000

/** Layers in display order. */
const LAYERS = ['market', 'sector']

/** Report basenames per layer; the newest by ISO date prefix wins. */
const REPORT_PATTERNS = {
  market: /^(\d{4}-\d{2}-\d{2})-market-state\.md$/u,
  sector: /^(\d{4}-\d{2}-\d{2})-sector-(.+)-state\.md$/u,
}

/**
 * One evidence line, mirroring the shape `scripts/state.py` itself parses:
 * `C3 短端变贵｜依据：…｜边界：…` with an optional data period before 依据.
 */
const RING_LINE = /^(C[1-6]) (.+?)(?:（(\d{4}-\d{2}-\d{2})\*?）)?｜依据：(.+?)｜边界：(.+)$/u

/** Panel copy per language, served with the payload so the client hardcodes no text. */
const LABELS = {
  zh: {
    title: '市场状态',
    refresh: '刷新',
    refreshing: '刷新中…',
    loading: '读取中…',
    failed: '读取失败',
    market: '市场',
    sector: '板块',
    evidence: '依据',
    boundary: '边界',
    empty: '该环无证据',
    noReport: '未找到报告',
    updated: '生成于',
    rebuilt: '已重建',
    rebuildFailed: '重建失败',
  },
  en: {
    title: 'Market state',
    refresh: 'Refresh',
    refreshing: 'Refreshing…',
    loading: 'Loading…',
    failed: 'Could not load',
    market: 'Market',
    sector: 'Sector',
    evidence: 'Evidence',
    boundary: 'Boundary',
    empty: 'No evidence for this ring',
    noReport: 'No report found',
    updated: 'Generated',
    rebuilt: 'Rebuilt',
    rebuildFailed: 'Rebuild failed',
  },
}

/**
 * Panel copy for one request language.
 * @param header - the request's `accept-language` value.
 * @returns the matching label table, English when the request asks for neither.
 */
function labelsFor(header) {
  return /(^|,|\s)zh\b/iu.test(header ?? '') ? LABELS.zh : LABELS.en
}

/**
 * Newest report file of one layer.
 * @param layer - `market` or `sector`.
 * @returns the basename, or `undefined` when the layer has no report yet.
 */
async function latestReport(layer) {
  const pattern = REPORT_PATTERNS[layer]
  let entries
  try {
    entries = await readdir(join(WORKSPACE, 'reports'))
  } catch {
    return undefined
  }
  const names = entries.filter(name => pattern.test(name)).sort()
  return names.length === 0 ? undefined : names[names.length - 1]
}

/**
 * Parse one report body into as-of, optional sector target, and ring rows.
 * @param text - the report file text.
 * @returns the parsed report; `rows` are in file order.
 */
function parseReport(text) {
  let asOf
  let target
  const rows = []
  for (const raw of text.split(/\r?\n/u)) {
    const line = raw.trim()
    if (line === '' || line.startsWith('```')) continue
    const head = /^as-of (\d{4}-\d{2}-\d{2})/u.exec(line)
    if (head !== null) {
      asOf ??= head[1]
      target ??= /目标板块：([^；;]+)/u.exec(line)?.[1]
      continue
    }
    const match = RING_LINE.exec(line)
    if (match === null) continue
    rows.push({
      ring: match[1],
      state: match[2],
      period: match[3] ?? null,
      evidence: match[4],
      boundary: match[5],
    })
  }
  return { asOf: asOf ?? null, target: target ?? null, rows }
}

/**
 * Read one layer's newest report.
 * @param layer - `market` or `sector`.
 * @returns the layer payload, with `file: null` when no report exists.
 */
async function collectLayer(layer) {
  const file = await latestReport(layer)
  if (file === undefined) return { layer, file: null, asOf: null, target: null, rows: [] }
  const text = await readFile(join(WORKSPACE, 'reports', file), 'utf8')
  const parsed = parseReport(text)
  return { layer, file: `reports/${file}`, ...parsed }
}

/**
 * Read both layers; one unreadable layer does not hide the other.
 * @returns the payload the panel renders.
 */
async function collect() {
  const errors = []
  const layers = []
  for (const layer of LAYERS) {
    try {
      layers.push(await collectLayer(layer))
    } catch (error) {
      errors.push(`${layer}: ${error instanceof Error ? error.message : String(error)}`)
      layers.push({ layer, file: null, asOf: null, target: null, rows: [], error: String(error) })
    }
  }
  return { ok: errors.length === 0, generatedAt: new Date().toISOString(), workspace: WORKSPACE, layers, errors }
}

/**
 * Rebuild one layer by running `scripts/state.py --layer <layer> --write`.
 * @param layer - `market` or `sector`.
 * @param stdio - child stdio modes; `ignore` for every stream drops the captured diagnostics.
 * @returns exit status plus captured diagnostics.
 */
function rebuild(layer, stdio) {
  return new Promise(resolve => {
    let settled = false
    const done = result => {
      if (settled) return
      settled = true
      resolve(result)
    }
    let child
    try {
      child = spawn(PYTHON, [join(WORKSPACE, 'scripts', 'state.py'), '--layer', layer, '--write'], {
        cwd: WORKSPACE,
        windowsHide: true,
        stdio,
      })
    } catch (error) {
      done({ layer, ok: false, error: error instanceof Error ? error.message : String(error) })
      return
    }
    let stdout = ''
    let stderr = ''
    child.stdout?.setEncoding('utf8')
    child.stderr?.setEncoding('utf8')
    child.stdout?.on('data', chunk => { stdout += chunk })
    child.stderr?.on('data', chunk => { stderr += chunk })
    const timer = setTimeout(() => {
      child.kill()
      done({ layer, ok: false, error: `timed out after ${REFRESH_TIMEOUT_MS} ms` })
    }, REFRESH_TIMEOUT_MS)
    child.once('error', error => {
      clearTimeout(timer)
      done({ layer, ok: false, error: error.message })
    })
    child.once('close', code => {
      clearTimeout(timer)
      done({
        layer,
        ok: code === 0,
        code,
        stdout: stdout.trim().slice(-4000),
        stderr: stderr.trim().slice(-4000),
      })
    })
  })
}

/**
 * Rebuild one layer, retrying without captured stdio when this host refuses a
 * piped child process: a confined process reports `spawn EPERM` before the
 * child starts, while the exit code and the regenerated report are unaffected.
 * @param layer - `market` or `sector`.
 * @returns the exit status, with `fallback` set when the retry produced it.
 */
async function rebuildLayer(layer) {
  const piped = await rebuild(layer, ['ignore', 'pipe', 'pipe'])
  if (piped.code !== undefined) return piped
  const silent = await rebuild(layer, ['ignore', 'ignore', 'ignore'])
  if (silent.code === undefined) return silent
  return { ...silent, fallback: true, firstError: piped.error }
}

/**
 * Collect the request body, bounded.
 * @param req - the incoming request.
 * @returns the parsed JSON body, or `{}` for an absent or unusable body.
 */
function readJsonBody(req) {
  return new Promise(resolve => {
    let size = 0
    const chunks = []
    req.on('data', chunk => {
      size += chunk.length
      if (size > 64 * 1024) {
        req.destroy()
        resolve({})
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8').trim()
      if (text === '') {
        resolve({})
        return
      }
      try {
        const parsed = JSON.parse(text)
        resolve(typeof parsed === 'object' && parsed !== null ? parsed : {})
      } catch {
        resolve({})
      }
    })
    req.on('error', () => resolve({}))
  })
}

/**
 * Answer one panel request: `GET` returns the current state, `POST` rebuilds
 * the requested layers first and returns the result plus per-layer status.
 * @param req - the incoming request.
 * @param res - the response this handler ends.
 */
async function handle(req, res) {
  const send = (status, body) => {
    const text = JSON.stringify(body)
    res.writeHead(status, {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      'content-length': Buffer.byteLength(text),
    })
    res.end(text)
  }
  try {
    const method = req.method ?? 'GET'
    if (method === 'GET' || method === 'HEAD') {
      const payload = await collect()
      send(200, { ...payload, labels: labelsFor(req.headers['accept-language']) })
      return
    }
    if (method === 'POST') {
      const body = await readJsonBody(req)
      const wanted = Array.isArray(body.layers)
        ? body.layers.filter(layer => LAYERS.includes(layer))
        : LAYERS
      const results = []
      for (const layer of wanted) results.push(await rebuildLayer(layer))
      const payload = await collect()
      send(200, {
        ...payload,
        refresh: { requested: wanted, results },
        labels: labelsFor(req.headers['accept-language']),
      })
      return
    }
    res.writeHead(405, { allow: 'GET, HEAD, POST' })
    res.end()
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    try {
      send(500, { ok: false, errors: [message], layers: [], labels: labelsFor() })
    } catch {
      res.destroy()
    }
  }
}

/**
 * Register the panel route when this profile mounts a web server.
 * @param ctx - the plugin context.
 */
export function apply(ctx) {
  ctx.inject(['webServer'], webCtx => {
    webCtx.effect(
      () => webCtx.webServer.register({ kind: 'exact', path: ROUTE_PATH, handler: handle }),
      'market-state.route',
    )
  })
}
