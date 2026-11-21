/**
 * Client half of @local/dsh-market-state: a compact row in the composer dock
 * that shows the six rings of the newest market-state report and rebuilds it
 * on demand through the Host route `/dsh-market-state/state`.
 *
 * The factory stays free of side effects; the slot registration is the only
 * resource and it lives on the injected context.
 */
window.__ModuleLoader__.load({
  id: '@local/dsh-market-state',
  factory(require) {
    const React = require('react')
    const h = React.createElement

    const ENDPOINT = '/dsh-market-state/state'
    const RINGS = ['C1', 'C2', 'C3', 'C4', 'C5', 'C6']
    const LAYERS = ['market', 'sector']

    /** Copy used only before the payload arrives or when the route is unreachable. */
    const FALLBACK = {
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
      rebuilt: '已重建',
      rebuildFailed: '重建失败',
    }

    const muted = { opacity: 0.68 }
    const border = '1px solid rgba(127, 127, 127, 0.35)'
    const chip = {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '0 6px',
      border,
      borderRadius: 6,
      background: 'transparent',
      color: 'inherit',
      font: 'inherit',
      lineHeight: '18px',
      cursor: 'pointer',
    }

    /**
     * One layer payload.
     * @param {object} payload - the route response.
     * @param {string} layer - `market` or `sector`.
     * @returns {object|undefined} the layer entry.
     */
    function layerOf(payload, layer) {
      if (payload === undefined || !Array.isArray(payload.layers)) return undefined
      return payload.layers.find(entry => entry && entry.layer === layer)
    }

    /**
     * Rows of one ring in the chosen layer.
     * @param {object|undefined} layer - the layer entry.
     * @param {string} ring - `C1` … `C6`.
     * @returns {object[]} the rows, empty when the ring carries no evidence.
     */
    function rowsOf(layer, ring) {
      if (layer === undefined || !Array.isArray(layer.rows)) return []
      return layer.rows.filter(row => row.ring === ring)
    }

    function MarketStatePanel() {
      const [state, setState] = React.useState({ status: 'loading' })
      const [layer, setLayer] = React.useState('market')
      const [openRing, setOpenRing] = React.useState(null)
      const [busy, setBusy] = React.useState(false)
      const mounted = React.useRef(true)

      React.useEffect(() => {
        mounted.current = true
        return () => { mounted.current = false }
      }, [])

      React.useEffect(() => {
        const controller = typeof AbortController === 'function' ? new AbortController() : undefined
        fetch(ENDPOINT, { headers: { accept: 'application/json' }, signal: controller?.signal })
          .then(response => {
            if (!response.ok) throw new Error(`HTTP ${String(response.status)}`)
            return response.json()
          })
          .then(payload => { if (mounted.current) setState({ status: 'ready', payload }) })
          .catch(error => {
            if (mounted.current) setState({ status: 'error', error: String((error && error.message) || error) })
          })
        return () => controller?.abort()
      }, [])

      const labels = (state.payload && state.payload.labels) || FALLBACK
      const current = layerOf(state.payload, layer)

      async function refresh() {
        setBusy(true)
        try {
          const response = await fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'content-type': 'application/json', accept: 'application/json' },
            body: JSON.stringify({ layers: LAYERS }),
          })
          if (!response.ok) throw new Error(`HTTP ${String(response.status)}`)
          const payload = await response.json()
          if (mounted.current) setState({ status: 'ready', payload })
        } catch (error) {
          if (mounted.current) {
            setState({ status: 'error', error: String((error && error.message) || error) })
          }
        } finally {
          if (mounted.current) setBusy(false)
        }
      }

      const header = h('div', { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
        h('strong', { style: { fontWeight: 600 } }, labels.title),
        state.status === 'ready' && current !== undefined && current !== null
          ? h('span', { style: muted }, current.asOf ?? '—')
          : null,
        LAYERS.map(name => h('button', {
          key: name,
          type: 'button',
          onClick: () => { setLayer(name); setOpenRing(null) },
          style: { ...chip, opacity: name === layer ? 1 : 0.6 },
          'aria-pressed': name === layer,
        }, labels[name] ?? name)),
        h('span', { style: { flex: 1 } }),
        state.status === 'ready'
          ? h('span', { style: muted }, `${labels.updated} ${String(state.payload.generatedAt ?? '').slice(11, 19)}`)
          : null,
        h('button', {
          type: 'button',
          onClick: refresh,
          disabled: busy,
          style: { ...chip, opacity: busy ? 0.5 : 1, cursor: busy ? 'default' : 'pointer' },
        }, busy ? labels.refreshing : labels.refresh),
      )

      let body
      if (state.status === 'loading') {
        body = h('div', { style: muted }, labels.loading)
      } else if (state.status === 'error') {
        body = h('div', { style: { color: 'inherit', ...muted } },
          `${labels.failed}：${state.error}`,
          h('span', null, ' '),
          h('span', { style: { opacity: 0.8 } }, ENDPOINT),
        )
      } else if (current === undefined || current === null || current.file === null) {
        body = h('div', { style: muted }, labels.noReport)
      } else {
        body = h('div', { style: { display: 'flex', gap: 6, flexWrap: 'wrap' } },
          RINGS.map(ring => {
            const rows = rowsOf(current, ring)
            const text = rows.length === 0 ? `${ring} —` : `${ring} ${rows.map(row => row.state).join(' · ')}`
            return h('button', {
              key: ring,
              type: 'button',
              style: { ...chip, opacity: rows.length === 0 ? 0.55 : 1 },
              title: rows.map(row => `${row.state}｜${row.evidence}`).join('\n') || labels.empty,
              onClick: () => setOpenRing(openRing === ring ? null : ring),
              'aria-expanded': openRing === ring,
            }, text)
          }),
        )
      }

      let details = null
      if (openRing !== null && current !== undefined && current !== null) {
        const rows = rowsOf(current, openRing)
        details = h('ul', { style: { margin: 0, padding: '2px 0 0 16px', listStyle: 'disc' } },
          rows.map((row, index) => h('li', { key: `${openRing}-${String(index)}`, style: { marginBottom: 2 } },
            h('strong', null, `${row.ring} ${row.state}`),
            row.period ? h('span', { style: muted }, `（${row.period}）`) : null,
            h('div', null, `${labels.evidence}：${row.evidence}`),
            h('div', { style: muted }, `${labels.boundary}：${row.boundary}`),
          )),
        )
      }

      const refreshStatus = state.payload && state.payload.refresh
      const refreshLine = refreshStatus && Array.isArray(refreshStatus.results)
        ? h('div', { style: muted },
          refreshStatus.results
            .map(result => `${result.layer} ${result.ok ? labels.rebuilt : `${labels.rebuildFailed}：${result.error ?? `exit ${String(result.code)}`}`}`)
            .join(' ｜ '),
        )
        : null

      return h('div', {
        style: {
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          padding: '4px 8px',
          fontSize: 12,
          lineHeight: 1.45,
          color: 'inherit',
        },
      }, header, body, details, refreshLine)
    }

    return {
      inject: ['slots'],
      apply(ctx) {
        ctx.slots.inject('conversation.composer.dock', () => ctx.slots.register({
          name: 'conversation.composer.dock',
          id: 'market-state',
          order: 5,
        }, MarketStatePanel))
      },
    }
  },
})
