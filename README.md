# 数据洞察分析工作台

面向多源数据接入、交互式查询分析、可视化看板搭建、分析报告生成与数据服务编排的数据洞察分析工作台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
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
| 交互查询 | `query` | 查询语句 | 语句编号、查询表达式、目标数据集 |
| 可视化图表 | `chart` | 图表配置 | 图表编号、图表名称、图表类型 |
| 数据源接入 | `source` | 接入配置 | 配置编号、连接类型、接入地址 |
| 聚合计算 | `aggregate` | 聚合方案 | 方案编号、聚合函数、目标字段 |
| 数据筛选 | `filter` | 筛选规则 | 规则编号、目标数据集、筛选字段 |
| 报告生成 | `reportgen` | 报告模板 | 模板编号、模板名称、包含图表 |
| 异常检测 | `anomaly` | 检测规则 | 规则编号、监控指标、基线均值 |
| 多维下钻 | `drill` | 下钻路径 | 路径编号、起点维度、下钻层数 |
| 对比分析 | `compare` | 对比方案 + 成对差异矩阵 | 方案编号、基准数据集、对照数据集、字段映射 |
| 分析流水线 | `pipeline` | 流水线节点 | 节点编号、节点类型、输入源 |
| 数据集管理 | `datastore` | 数据集定义 | 数据集编号、数据集名称、来源表名、字段定义 |
| 趋势预测 | `forecast` | 预测模型 | 模型编号、模型类型、训练数据集 |
| 数据分片 | `segment` | 分片规则 | 规则编号、目标数据集、分片字段 |
| 调度管理 | `scheduler` | 调度配置 | 配置编号、关联任务、调度表达式 |
| 通知分发 | `notify` | 通知规则 | 规则编号、触发条件、通知渠道 |
| 查询缓存 | `cache` | 缓存策略 | 策略编号、目标查询、缓存键规则 |
| 数据标签 | `tag` | 标签定义 | 标签编号、标签名称、计算表达式 |
| 数据分享 | `share` | 分享链接 | 链接编号、目标数据集、访问密码 |

## 对比分析：成对样本差异矩阵

对比分析页在方案列表下方提供两阶段工作台：

1. **字段映射**：从数据集管理里选两条已生效数据集（`GET /api/compare/mapping-preview`），
   把业务键与数值字段一一对应；确认后写回方案（`PUT /api/compare/plans/{id}/mapping`）。
2. **差异矩阵**：启动轮次（`POST /api/compare/plans/{id}/rounds`）后封存两侧数据集定义、
   字段映射与阈值；`POST /rounds/{id}/complete` 生成矩阵，`GET /rounds/{id}/matrix` 分页取数。

关键规则：

- 配对只认业务键；任一侧同键多行即整组进入隔离区，必须显式选择两侧记录后才能确认配对，
  不会按输入顺序自动配对（`POST /rounds/{id}/quarantine/{group}`）。
- 格子颜色区分数值差（超阈值）、阈值内、缺行、空值；空字符串与 `null` 不会折算成数字 `0`。
- 双击格子打开样本证据（`GET /rounds/{id}/cells/{cell_id}/evidence`），展示两侧原始记录与
  对应交互查询语句，可跳转到交互查询页面定位语句。
- 启动时封存的字段身份与阈值随轮次保留；重算与左右交换各自开启新轮次，旧轮次不变。
  左右交换后差值方向相反。
- 计算期间任一侧数据集被废弃（含“废弃后又恢复”），轮次转「已阻断」，拒绝结论签认。

前端代码在 `frontend/src/views/compare/`（`MappingPanel`、`MatrixWorkspace`、`MatrixGrid`、
`EvidenceDialog`），后端规则在 `backend/app/services/compare_matrix.py`，样本数据在
`backend/app/sample_data.py`。

后端测试：

```bash
cd backend && .venv/bin/python -m unittest tests.test_compare_matrix -v
```

前端冒烟（需要后端已启动；jsdom / @vue/test-utils / vite-node 为临时依赖，未写入 package.json）：

```bash
cd frontend
npm install --no-save --no-package-lock jsdom@25 @vue/test-utils@2 vite-node@2
NODE_OPTIONS="--import ./scripts/smoke-preload.mjs" npx vite-node scripts/smoke-compare.mjs
```

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用
