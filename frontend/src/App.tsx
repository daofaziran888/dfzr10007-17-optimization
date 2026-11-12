import { useState } from 'react'
import { Link, Route, Routes } from 'react-router-dom'

import Overview from './views/Overview'
import MartView from './views/mart'
import SqlpadView from './views/sqlpad'
import VizdragView from './views/vizdrag'
import CollabView from './views/collab'
import AnomalyView from './views/anomaly'
import ModelView from './views/model'
import OptView from './views/opt'
import StoryView from './views/story'
import EtlView from './views/etl'
import CatalogView from './views/catalog'
import SampleView from './views/sample'
import CompareView from './views/compare'
import ExportView from './views/export'
import AlarmView from './views/alarm'
import RefreshView from './views/refresh'
import AuditView from './views/audit'

const navItems = [{ label: "运营概览", path: "/" }, { label: "数据集市构建", path: "/mart" }, { label: "自助SQL查询", path: "/sqlpad" }, { label: "拖拽可视化", path: "/vizdrag" }, { label: "看板协作管理", path: "/collab" }, { label: "指标异动归因", path: "/anomaly" }, { label: "分析模型沉淀", path: "/model" }, { label: "查询优化建议", path: "/opt" }, { label: "数据故事编排", path: "/story" }, { label: "数据准备流水线", path: "/etl" }, { label: "数据目录检索", path: "/catalog" }, { label: "数据采样管理", path: "/sample" }, { label: "同环比分析", path: "/compare" }, { label: "分析导出中心", path: "/export" }, { label: "分析告警规则", path: "/alarm" }, { label: "数据定时刷新", path: "/refresh" }, { label: "查询审计日志", path: "/audit" }]

export default function App() {
  const [operator] = useState('值班管理员')

  return (
    <div className="app-shell">
      <aside className="app-side">
        <h1 className="app-title">数据洞察与自助分析平台</h1>
        <nav className="nav-list">
          {navItems.map((item) => (
            <Link key={item.path} to={item.path} className="nav-item">
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="app-main">
        <header className="app-head">
          <span className="head-desc">面向业务分析师的自助式数据洞察平台。覆盖数据集市构建、自助SQL查询、可视化拖拽分析、分析看板协作、指标异动归因、分析模型沉淀、查询优化建议与数据故事编排的完整洞察链路。</span>
          <span className="head-user">当前值班：{operator}</span>
        </header>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/mart" element={<MartView />} />
          <Route path="/sqlpad" element={<SqlpadView />} />
          <Route path="/vizdrag" element={<VizdragView />} />
          <Route path="/collab" element={<CollabView />} />
          <Route path="/anomaly" element={<AnomalyView />} />
          <Route path="/model" element={<ModelView />} />
          <Route path="/opt" element={<OptView />} />
          <Route path="/story" element={<StoryView />} />
          <Route path="/etl" element={<EtlView />} />
          <Route path="/catalog" element={<CatalogView />} />
          <Route path="/sample" element={<SampleView />} />
          <Route path="/compare" element={<CompareView />} />
          <Route path="/export" element={<ExportView />} />
          <Route path="/alarm" element={<AlarmView />} />
          <Route path="/refresh" element={<RefreshView />} />
          <Route path="/audit" element={<AuditView />} />
        </Routes>
      </main>
    </div>
  )
}
