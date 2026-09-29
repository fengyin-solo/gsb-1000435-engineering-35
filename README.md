# 冷链物流温控管理平台

面向冷链运输的车辆调度、温控监测、冷库作业、签收回单、异常报警与冷链断链追溯的综合物流管理后台。

前后端分离：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python），数据落在 SQLite（标准库 `sqlite3`，无需额外服务）。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端（nginx 镜像用于生产部署）
│   ├── src/views/            每个业务模块一个页面，Dashboard 为运营概览
│   ├── src/api/              统一请求封装
│   └── nginx.conf            生产镜像：SPA 回退 + /api 反代
├── backend/                  FastAPI 后端
│   ├── app/config.py         环境变量配置（按需读取）
│   ├── app/db.py             SQLite 连接、事务、版本迁移
│   ├── app/modules.py        18 个业务模块的唯一口径注册表（字段/状态/动作）
│   ├── app/seed.py           样例数据与事务化初始化（只补缺失，幂等）
│   ├── app/services/         业务规则；overview.py 负责概览重算/回填/对账
│   ├── app/routers/          接口（_factory.py 统一生成）
│   ├── app/cli.py            migrate / seed / recompute-overview / reconcile / reset
│   └── tests/                pytest：事务回滚、幂等、口径对账、API
├── Makefile                  可重复的一键入口
├── docker-compose.yml        一键起前后端（后端数据落命名卷）
└── .env.example              全部环境变量样例
```

## 数据口径（先读这节）

平台只有**一张原始业务表 `records`**，概览和明细都从它取数：

| 口径 | 来源 | 说明 |
| --- | --- | --- |
| 运行数据 `runtime` | 接口登记/流转写入 `records` 的记录 | **权威口径**，概览与明细只认它 |
| 样例数据 `sample` | `app/seed.py` 的 `SEED_ROWS` | 仅首次初始化时落库，`source` 列标记为 `sample` |

优先级规则：

1. **运行数据 > 样例数据**。初始化播种对已存在的 `(module, id)` 一律跳过，永不覆盖；
   重复执行任意次结果一致（幂等）。
2. `pending` / `abnormal` 不允许样例自带，统一由 `app/modules.py` 的状态机推导
   （非终态即待处理；负向动作的目标状态即异常），保证样例、接口流转、概览三处同口径。
3. 概览指标 = 对 `records` 的聚合，与各模块列表接口查的是同一张表。
   `GET /api/overview`（默认实时）返回 `source: runtime`；`?view=snapshot` 返回迁移/回填时保存的快照。
4. 迁移或回填后用对账核对：快照必须与明细聚合逐模块相等，不一致可用重算修复。

## 本地开发（可重复）

需要 Python 3.11+（需 `venv` 模块；Debian/Ubuntu 缺包时 `sudo apt install python3-venv`）和 Node 20+。

```bash
make install          # 建后端 .venv 装依赖 + 前端 npm install
make backend          # 启动后端：自动迁移 -> 补样例 -> 回填概览，--reload
make frontend         # 启动前端 dev server（/api 代理到 127.0.0.1:8000）
```

- 后端：http://127.0.0.1:8000 ，健康检查 `curl http://127.0.0.1:8000/api/health`
- 前端：http://127.0.0.1:5173/ （dev server 不会自动开浏览器）
- 本地数据库默认 `backend/data/app.db`（已在 .gitignore），删除即可回到全新状态。

## 环境变量

复制根目录 `.env.example` 按需导出（或在容器里注入）：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `local` | 环境标识 |
| `APP_HOST` / `APP_PORT` | `127.0.0.1` / `8000` | 后端监听 |
| `DATABASE_URL` | `backend/data/app.db` | SQLite 文件路径，容器内为 `/data/app.db` |
| `MIGRATE_ON_START` | `1` | 启动时执行幂等迁移 |
| `SEED_ON_START` | `1` | 启动时补写样例；**生产必须设 `0`** |
| `APP_ALLOWED_ORIGINS` | 本地两个 5173 源 | CORS 白名单，逗号分隔 |
| `VITE_API_BASE` / `VITE_PROXY_TARGET` | 空 / `http://127.0.0.1:8000` | 前端基址与代理目标 |

## 数据库迁移、播种与概览回填

所有命令都在 `backend/` 下，幂等可重复执行；也可用 `make <命令>`：

```bash
python -m app.cli init                 # 迁移 + 播种 + 概览回填（与启动流程完全一致）
python -m app.cli migrate              # 只跑版本迁移（schema_migrations 记录版本）
python -m app.cli seed                 # 单事务补样例：只补缺失，不覆盖运行数据
python -m app.cli recompute-overview   # 按原始业务记录重算概览快照（迁移/回填场景）
python -m app.cli reconcile            # 概览快照 vs 明细同口径对账，不一致退出码 1
python -m app.cli reset --yes [--seed] # 危险：清空全部运行数据（需显式 --yes）
```

事务保证：

- **初始化播种是单个事务**：任何一条样例非法或写入失败，整批回滚，不留半成品（有测试覆盖）。
- **概览回填是单个事务**：先清空快照再整批写入，与外层迁移/播种可以同事务，失败一起回滚。
- 接口的每次登记/状态流转也各自是一个事务，并在**同一事务内**刷新概览快照，
  因此正常运行中快照天然与明细一致；`reconcile` 主要用于迁移后核对与异常排查。

## 接口约定

- 列表：`GET /api/<module>?keyword=&status=&page=&size=` → `{ items, total, page, size }`，`size` 上限 200
- 详情：`GET /api/<module>/{id}`；导出：`GET /api/<module>/export`
- 登记：`POST /api/<module>`，body `{ "values": { ... } }`
- 流转：`POST /api/<module>/{id}/actions`，body `{ "values": { "action": "动作名" } }`
- 概览：`GET /api/overview[?view=live|snapshot]`
- 运维：`GET /api/admin/reconcile`、`POST /api/admin/recompute-overview`

动作结果统一 `{ ok, message, entry? }`；业务字段、状态序列、动作与实体称谓全部定义在
`backend/app/modules.py`，路由、服务、概览、样例共用，不存在第二份口径。

## 测试

```bash
make test               # 后端 pytest + 前端 vue-tsc 类型检查
# 或只跑后端（每个用例独立临时库）：
cd backend && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

覆盖点：迁移幂等、播种单事务回滚、重复播种不覆盖运行数据、标志位跟随状态机、
概览与明细逐模块对账、回填随事务回滚、API 契约。

## 构建与部署

### 前端生产构建

```bash
cd frontend
npm run build           # vue-tsc 类型检查 + vite 打包到 dist/
npm run preview         # 本地预览构建产物
```

### Docker Compose（推荐的一键部署形态）

```bash
docker compose up --build -d
# 前端（nginx + API 反代）：http://127.0.0.1:8080
# 后端：http://127.0.0.1:8000
```

- 后端数据在命名卷 `backend-data`（容器内 `/data/app.db`），重建镜像不丢运行数据；
- 后端带 healthcheck，前端容器等后端健康后再启动；
- **生产部署**把 compose 里 `SEED_ON_START` 改为 `0`（样例只用于本地/演示）。

### 升级流程（新增迁移时）

1. 在 `app/db.py` 的 `MIGRATIONS` 追加新版本 SQL（不要改旧版本）；
2. 部署后启动会自动迁移，随后执行 `python -m app.cli recompute-overview` 回填概览；
3. 执行 `python -m app.cli reconcile`，退出码 0 即「概览与明细对得上」。

## 业务模块

发运单管理、温控监测、车辆调度、司机管理、冷库运营、装卸作业、报警管理、线路规划、
制冷机组、油料管理、签收回单、断链追溯、月台管理、包装管理、通行费用、车辆消杀、
承运合同、货运保险（口径见 `app/modules.py`）。
