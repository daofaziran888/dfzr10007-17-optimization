import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/story'
const columns = [
  "模板编号",
  "故事标题",
  "分析主题",
  "图表序列",
  "叙述文本",
  "交互流程",
  "发布渠道",
  "模板状态"
]
const actions = [
  "发布故事",
  "归档故事",
  "删除故事"
]
const statuses = [
  "草稿",
  "编排中",
  "已发布",
  "已归档"
]
const stats = [
  {
    "label": "故事模板总数",
    "value": 0
  },
  {
    "label": "已发布故事",
    "value": 0
  },
  {
    "label": "已归档故事",
    "value": 0
  }
]
const CHART_OPTIONS = ['bar', 'line', 'pie', 'kpi', 'area', 'scatter', 'table']

type Row = Record<string, string | number | null>

type ShardState = {
  position: number
  图表类型: string
  状态: string
  失败次数: number
  叙述快照: string | null
  最近错误: string | null
}

type NarrativeVersion = {
  版本号: number
  故事标题: string | null
  序列顺序: string[]
  叙述快照: { position: number; 图表类型: string; 状态: string; 叙述文本: string | null }[]
  异常分片: number[]
  已发布: boolean
}

type OrchestrationDetail = {
  模板编号: string
  故事标题: string
  完成位置: number
  编排完成: boolean
  叙述版本号: number
  发布叙述版本: number | null
  占用批次: string | null
  叙述分段: string[]
  编排进度: ShardState[]
  叙述版本库: NarrativeVersion[]
}

type BatchResult = {
  模板编号: string
  批次号: string
  完成位置: number
  序列长度: number
  编排完成: boolean
  中断: boolean
  本批通过: { position: number; 图表类型: string; 叙述文本: string }[]
  幂等忽略: { position: number; 图表类型: string; 原因: string }[]
  校验失败: { position: number; 图表类型: string; 原因: string }[]
  封存版本: NarrativeVersion | null
  叙述版本号: number
}

type ExportItem = {
  模板编号: string
  故事标题: string
  分析主题: string
  引用叙述版本: number
  发布叙述版本: number | null
  故事状态: string
  图表序列: string[]
  叙述分片: { position: number; 图表类型: string; 叙述文本: string | null }[]
  异常分片位置: number[]
  缺失说明: string
}

type ExcludedStory = { 模板编号: string; 原因: string }

type ExportPayload = {
  module: string
  total: number
  items: ExportItem[]
  excluded: ExcludedStory[]
  message: string
}

const SHARD_BADGE: Record<string, string> = {
  待校验: 'badge pending',
  已通过: 'badge valid',
  待重试: 'badge rejected',
  异常隔离: 'badge abnormal',
}

function nextBatchId() {
  return `B-${Date.now()}-${Math.floor(Math.random() * 1000)}`
}

export default function StoryView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const [activeRowId, setActiveRowId] = useState<number | null>(null)
  const [detail, setDetail] = useState<OrchestrationDetail | null>(null)
  const [batchMessage, setBatchMessage] = useState('')
  const [batchChart, setBatchChart] = useState('bar')
  const [batchNarrative, setBatchNarrative] = useState('')
  const [exportPayload, setExportPayload] = useState<ExportPayload | null>(null)

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('故事模板列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据故事编排列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  const loadDetail = useCallback(async (rowId: number) => {
    setBatchMessage('')
    const response = await request(`${ENDPOINT}/${rowId}/orchestration`)
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body.detail ?? '编排进度读取失败')
    }
    const data: OrchestrationDetail = await response.json()
    setDetail(data)
    const nextShard = data.编排进度.find((shard) => shard.状态 === '待校验' || shard.状态 === '待重试')
    if (nextShard) {
      setBatchChart(nextShard.图表类型)
      setBatchNarrative(data.叙述分段?.[nextShard.position] ?? '')
    }
  }, [])

  const openPanel = useCallback(async (rowId: number) => {
    setActiveRowId(rowId)
    await loadDetail(rowId)
  }, [loadDetail])

  const closePanel = useCallback(() => {
    setActiveRowId(null)
    setDetail(null)
    setBatchMessage('')
  }, [])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      const body = await response.json()
      if (!response.ok || !body.ok) {
        throw new Error(body.message ?? body.detail ?? '数据故事编排动作未生效，请稍后重试')
      }
      await reload()
      if (activeRowId === Number(row.id)) {
        await loadDetail(Number(row.id))
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据故事编排操作失败')
    }
  }

  async function submitBatch() {
    if (activeRowId === null || detail === null) {
      return
    }
    const nextShard = detail.编排进度.find((shard) => shard.状态 === '待校验' || shard.状态 === '待重试')
    if (!nextShard) {
      setBatchMessage('全序列已处理，没有可提交的分片；可开启新一轮编排')
      return
    }
    setBatchMessage('')
    try {
      const response = await request(`${ENDPOINT}/${activeRowId}/orchestration`, {
        method: 'POST',
        body: JSON.stringify({
          batch_id: nextBatchId(),
          shards: [{
            position: nextShard.position,
            图表类型: batchChart,
            叙述文本: batchNarrative,
          }],
        }),
      })
      const body = await response.json()
      if (response.status === 409) {
        setBatchMessage(`批次争用被拒：${body.detail}（同一模板只允许一个批次推进）`)
        return
      }
      if (!response.ok || !body.ok) {
        setBatchMessage(body.detail ?? body.message ?? '编排批次提交失败')
        return
      }
      const result = body.entry as BatchResult
      const notes: string[] = [body.message]
      if (result.本批通过.length) {
        notes.push(`通过位置：${result.本批通过.map((item) => item.position).join('、')}`)
      }
      if (result.幂等忽略.length) {
        notes.push(`幂等忽略：${result.幂等忽略.map((item) => `位置${item.position}（${item.原因}）`).join('；')}`)
      }
      if (result.校验失败.length) {
        notes.push(`校验失败：${result.校验失败.map((item) => `位置${item.position} ${item.图表类型}：${item.原因}`).join('；')}`)
      }
      if (result.封存版本) {
        notes.push(`已封存叙述版本 v${result.封存版本.版本号}`)
      }
      setBatchMessage(notes.join('。'))
      await Promise.all([loadDetail(activeRowId), reload()])
    } catch (error) {
      setBatchMessage(error instanceof Error ? error.message : '编排批次请求未送达')
    }
  }

  async function startNewRound() {
    if (activeRowId === null) {
      return
    }
    setBatchMessage('')
    try {
      const response = await request(`${ENDPOINT}/${activeRowId}/orchestration/reset`, {
        method: 'POST',
        body: JSON.stringify({ batch_id: nextBatchId() }),
      })
      const body = await response.json()
      if (response.status === 409) {
        setBatchMessage(`批次争用被拒：${body.detail}`)
        return
      }
      if (!response.ok || !body.ok) {
        setBatchMessage(body.detail ?? body.message ?? '新一轮编排开启失败')
        return
      }
      setBatchMessage(`${body.message}，下一轮版本号 v${body.entry.下一轮版本号}`)
      await Promise.all([loadDetail(activeRowId), reload()])
    } catch (error) {
      setBatchMessage(error instanceof Error ? error.message : '新一轮编排请求未送达')
    }
  }

  async function loadExport() {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/export`)
      if (!response.ok) {
        throw new Error('数据故事清单导出读取失败')
      }
      setExportPayload(await response.json())
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据故事清单读取失败')
    }
  }

  const nextShard = detail?.编排进度.find((shard) => shard.状态 === '待校验' || shard.状态 === '待重试') ?? null

  return (
    <section className="page" data-module="story">
      <header className="page-head">
        <div>
          <h2>数据故事编排管理</h2>
          <p className="page-desc">图表序列分批校验、失败分片断点恢复，叙述文本按版本留存；异常分片隔离后不进入导出清单。</p>
        </div>
        <div className="page-actions">
          <button className="btn primary" type="button" onClick={() => setErrorMessage('故事模板登记入口尚未接入审批流')}>
            登记故事模板
          </button>
          <button className="btn" type="button" onClick={() => void loadExport()}>
            读取数据故事清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>编排进度</th>
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td>
                <button className="link" type="button" onClick={() => void openPanel(Number(row.id))}>
                  分批校验/恢复
                </button>
              </td>
              <td className="row-actions">
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 2}>
                暂无数据故事编排数据：当前过滤条件下没有故事模板，可先登记故事模板或重置查询条件
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {activeRowId !== null && detail !== null && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h3>分批编排 · {detail.模板编号} · {detail.故事标题}</h3>
              <p className="page-desc">
                完成位置 {detail.完成位置} / {detail.编排进度.length - 1}
                {detail.编排完成 ? '，全序列已处理' : '，中断后只能从失败项（下一项）恢复'}
                {detail.占用批次 ? `，当前占用批次：${detail.占用批次}` : ''}
                ，当前叙述版本 v{detail.叙述版本号}
                {detail.发布叙述版本 ? `，发布引用 v${detail.发布叙述版本}` : '，尚未发布'}
              </p>
            </div>
            <button className="btn ghost" type="button" onClick={closePanel}>关闭面板</button>
          </div>

          <table className="data-table">
            <thead>
              <tr>
                <th>完成位置</th>
                <th>图表类型</th>
                <th>分片状态</th>
                <th>失败次数</th>
                <th>叙述文本快照</th>
                <th>最近错误</th>
              </tr>
            </thead>
            <tbody>
              {detail.编排进度.map((shard) => (
                <tr key={shard.position}>
                  <td>{shard.position}</td>
                  <td>{shard.图表类型}</td>
                  <td><span className={SHARD_BADGE[shard.状态] ?? 'badge'}>{shard.状态}</span></td>
                  <td>{shard.失败次数}</td>
                  <td>{shard.叙述快照 ?? '—'}</td>
                  <td>{shard.最近错误 ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="batch-form">
            <div>
              <span className="form-title">
                {nextShard
                  ? `下一批次提交分片：位置 ${nextShard.position}（${nextShard.状态 === '待重试' ? '失败项重试' : '断点继续'}）`
                  : '全序列已处理'}
              </span>
              <div className="form-row">
                <label className="filter-item">
                  <span>图表类型</span>
                  <select value={batchChart} onChange={(event) => setBatchChart(event.target.value)}>
                    {CHART_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}
                  </select>
                </label>
                <label className="filter-item narrative-input">
                  <span>叙述文本快照（同位置重复到达不会追加第二份）</span>
                  <input value={batchNarrative} onChange={(event) => setBatchNarrative(event.target.value)} />
                </label>
                <button className="btn primary" type="button" disabled={nextShard === null} onClick={() => void submitBatch()}>
                  提交校验批次
                </button>
                <button className="btn" type="button" onClick={() => void startNewRound()}>
                  开启新一轮（历史版本保留）
                </button>
              </div>
            </div>
          </div>
          {batchMessage && <p className="batch-message">{batchMessage}</p>}

          {detail.叙述版本库.length > 0 && (
            <div className="version-box">
              <h4>叙述版本库（历史版本按原图表序列保留）</h4>
              {detail.叙述版本库.map((version) => (
                <article key={version.版本号} className="version-card">
                  <strong>v{version.版本号}</strong>
                  <span>序列：{version.序列顺序.join(' → ')}</span>
                  <span>异常分片位置：{version.异常分片.length ? version.异常分片.join('、') : '无'}</span>
                  <ol className="snapshot-list">
                    {version.叙述快照.map((item) => (
                      <li key={item.position}>
                        位置{item.position} · {item.图表类型} · {item.状态}：{item.叙述文本 ?? '（无快照）'}
                      </li>
                    ))}
                  </ol>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

      {exportPayload !== null && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h3>数据故事清单（导出读取链路）</h3>
              <p className="page-desc">{exportPayload.message}</p>
            </div>
            <button className="btn ghost" type="button" onClick={() => setExportPayload(null)}>关闭清单</button>
          </div>
          {exportPayload.items.length === 0 ? (
            <p className="empty-state">暂无数据：没有编排完整的故事可导出，缺失原因见下方说明</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>模板编号</th>
                  <th>故事标题</th>
                  <th>故事状态</th>
                  <th>引用叙述版本</th>
                  <th>原图表序列</th>
                  <th>导出叙述分片</th>
                  <th>异常分片与缺失说明</th>
                </tr>
              </thead>
              <tbody>
                {exportPayload.items.map((item) => (
                  <tr key={item.模板编号}>
                    <td>{item.模板编号}</td>
                    <td>{item.故事标题}</td>
                    <td>{item.故事状态}</td>
                    <td>v{item.引用叙述版本}{item.发布叙述版本 ? `（发布 v${item.发布叙述版本}）` : ''}</td>
                    <td>{item.图表序列.join(' → ')}</td>
                    <td>
                      <ol className="snapshot-list">
                        {item.叙述分片.map((part) => (
                          <li key={part.position}>位置{part.position} · {part.图表类型}：{part.叙述文本 ?? '—'}</li>
                        ))}
                      </ol>
                    </td>
                    <td>{item.缺失说明 || '无异常分片'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {exportPayload.excluded.length > 0 && (
            <div className="excluded-box">
              <h4>未进入导出的故事及缺失原因（异常分片不进入导出）</h4>
              <ul>
                {exportPayload.excluded.map((item) => (
                  <li key={item.模板编号}>{item.模板编号}：{item.原因}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      <footer className="page-foot">
        <span>共 {total} 条数据故事编排记录</span>
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
