# 数据洞察与自助分析平台

面向业务分析师的自助式数据洞察平台。覆盖数据集市构建、自助SQL查询、可视化拖拽分析、分析看板协作、指标异动归因、分析模型沉淀、查询优化建议与数据故事编排的完整洞察链路。

这是一个前后端分离的管理平台：前端 React + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 React + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 数据集市构建 | `mart` | 集市定义 | 集市编号、集市名称、数据源表 |
| 自助SQL查询 | `sqlpad` | 查询脚本 | 脚本编号、脚本名称、SQL语句 |
| 拖拽可视化 | `vizdrag` | 可视化方案 | 方案编号、方案名称、数据源绑定 |
| 看板协作管理 | `collab` | 协作看板 | 看板编号、看板名称、协作成员 |
| 指标异动归因 | `anomaly` | 异动记录 | 记录编号、指标名称、异动方向 |
| 分析模型沉淀 | `model` | 模型注册 | 模型编号、模型名称、模型类型 |
| 查询优化建议 | `opt` | 优化建议 | 建议编号、目标查询、优化类型 |
| 数据故事编排 | `story` | 故事模板 | 模板编号、故事标题、分析主题 |
| 数据准备流水线 | `etl` | 准备任务 | 任务编号、任务名称、输入源 |
| 数据目录检索 | `catalog` | 目录条目 | 条目编号、数据集名称、业务域 |
| 数据采样管理 | `sample` | 采样配置 | 配置编号、数据源名称、采样算法 |
| 同环比分析 | `compare` | 对比方案 | 方案编号、对比指标、基准周期 |
| 分析导出中心 | `export` | 导出任务 | 任务编号、数据源名称、导出格式 |
| 分析告警规则 | `alarm` | 告警规则 | 规则编号、监控指标、告警条件 |
| 数据定时刷新 | `refresh` | 刷新策略 | 策略编号、目标数据集、刷新周期 |
| 查询审计日志 | `audit` | 审计记录 | 记录编号、查询语句、执行人 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 数据故事分批编排与断点恢复

故事模板的图表序列按「分片」逐片校验，STOR-0002 的序列为
`bar、line、pie、kpi`，其中 `pie` 不在渲染白名单内，用于复现第 3 个图表失败。

- `POST /api/story/{id}/orchestration`：提交一个编排批次 `{ batch_id, shards }`，
  每个分片带 `position`（原序列完成位置）、`图表类型`、`叙述文本`。批次在首个
  失败分片中断，完成位置停在失败项之前；重试只能从失败项（下一项）恢复。
  同一 position 重复到达走幂等分支，不会追加第二份叙述文本快照。
- 同一模板同时只允许一个批次推进，争用返回 HTTP 409；分片 position 越界返回
  400；乱序提交作为批次校验失败返回 200 并在 `校验失败` 中给出恢复位置。
- 分片连续两次校验失败进入「异常隔离」，游标越过它继续处理后续分片；隔离分片
  不写入叙述快照，也不进入导出。
- `POST /api/story/{id}/orchestration/reset`：开启新一轮编排，历史叙述版本按原
  序列归档在 `叙述版本库`，新版本引用新一轮叙述；发布故事时记录
  `发布叙述版本` 与发布快照。
- `GET /api/story/{id}/orchestration`：查看分片状态、完成位置与叙述版本库。
- `GET /api/story/export`：数据故事清单只收录编排完整的故事，按原序列输出叙述
  分片并点名异常分片；没有完整故事时 `total=0`，`message` 与 `excluded`
  逐条说明缺失原因。

后端核对脚本（仅依赖标准库，含真实 uvicorn HTTP 链路）：

```bash
cd backend
.venv/bin/python -I tests/test_story_orchestration.py
```

领域：数据工程
子方向：数仓与数据湖
