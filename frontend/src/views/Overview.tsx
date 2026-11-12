import { useEffect, useState } from 'react'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

const fallbackCards = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
const fallbackModules = [{"name": "数据集市构建", "created": 0, "pending": 0, "abnormal": 0}, {"name": "自助SQL查询", "created": 0, "pending": 0, "abnormal": 0}, {"name": "拖拽可视化", "created": 0, "pending": 0, "abnormal": 0}, {"name": "看板协作管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "指标异动归因", "created": 0, "pending": 0, "abnormal": 0}, {"name": "分析模型沉淀", "created": 0, "pending": 0, "abnormal": 0}, {"name": "查询优化建议", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据故事编排", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据准备流水线", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据目录检索", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据采样管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "同环比分析", "created": 0, "pending": 0, "abnormal": 0}, {"name": "分析导出中心", "created": 0, "pending": 0, "abnormal": 0}, {"name": "分析告警规则", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据定时刷新", "created": 0, "pending": 0, "abnormal": 0}, {"name": "查询审计日志", "created": 0, "pending": 0, "abnormal": 0}]

export default function Overview() {
  const [cards, setCards] = useState<Overview['cards']>(fallbackCards)
  const [moduleRows, setModuleRows] = useState<Overview['modules']>(fallbackModules)

  useEffect(() => {
    fetchJson<Overview>('/api/overview')
      .then((payload) => {
        setCards(payload.cards)
        setModuleRows(payload.modules)
      })
      .catch(() => undefined)
  }, [])

  return (
    <section className="page">
      <header className="page-head">
        <div>
          <h2>运营概览</h2>
          <p className="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
        </div>
      </header>
      <div className="stat-row">
        {cards.map((card) => (
          <article key={card.label} className="stat-card">
            <span className="stat-label">{card.label}</span>
            <strong className="stat-value">{card.value}</strong>
          </article>
        ))}
      </div>
      <table className="data-table">
        <thead>
          <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
        </thead>
        <tbody>
          {moduleRows.map((row) => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td>{row.created}</td>
              <td>{row.pending}</td>
              <td>{row.abnormal}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
