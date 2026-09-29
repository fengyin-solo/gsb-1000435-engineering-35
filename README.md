# 冷链物流温控管理平台

面向冷链运输的车辆调度、温控监测、冷库作业、签收回单、异常报警与冷链断链追溯的综合物流管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python），
业务数据落在 SQLite（零外部依赖，克隆即可起）。前后端各自独立启动，前端 dev server
已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面；Dashboard.vue 是运营概览
│   ├── Dockerfile            多阶段构建：vite build -> nginx 静态部署 + /api 反代
│   └── nginx.conf
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则（公共逻辑在 base.py，模块只绑定名字）
│   ├── app/registry.py       18 个模块的口径登记表（状态/必填/关键字/日期字段）
│   ├── app/store.py          SQLite 仓库：明细是事实来源，概览是同事务重算的快照
│   ├── app/cli.py            init / rebuild / reconcile / reset 运维命令
│   ├── app/seed.py           样例数据（只在 local 幂等补齐）
│   └── tests/                pytest（每用例独立内存库）
├── docker-compose.yml        backend + frontend，数据落命名卷
├── Makefile                  常用一键命令
└── .env.example             compose 用环境变量样例
```

## 本地开发（可重复流程）

首次：

```bash
make install          # backend/.venv 装 requirements-dev.txt；frontend npm install
```

之后日常只需要两个终端：

```bash
make backend          # 建表 + 幂等初始化 + 起 uvicorn（127.0.0.1:8000）
make frontend         # vite dev server（127.0.0.1:5173，/api 代理到后端）
```

健康检查：`curl http://127.0.0.1:8000/api/health`
（返回里的 `overview_consistent` 表示概览快照与业务明细是否对得上。）

也可以不用 Make：

```bash
cd backend && ./run.sh
cd frontend && npm run dev
```

### 环境变量

- 后端复制 `backend/.env.example` 为 `backend/.env`（已 gitignore）；调用方显式 export
  的同名变量优先级更高，方便临时换端口/库文件：`APP_PORT=8012 ./run.sh`。
- 前端读 `frontend/.env.development`（dev）与 `.env.production`（build）。
- 根目录 `.env.example` 供 docker compose 使用。

关键变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `local` | `local` 启动幂等补样例；`prod` 只建表不碰样例 |
| `APP_DATABASE_URL` | `sqlite:///data/app.db` | 落库文件；`:memory:` 仅测试 |
| `APP_SEED_ON_STARTUP` | local=true / prod=false | 显式控制是否补样例 |
| `APP_OVERVIEW_TODAY` | 空（取当天） | 概览“当日新增”的参考自然日，验收可固定 `2026-09-02` |
| `APP_CORS_ORIGINS` | 本地两个 5173 来源 | 逗号分隔 |

## 样例数据与运行数据的口径优先级

**运行数据 > 样例数据。** 具体规则：

1. 启动与 `python -m app.cli init` 只做 `INSERT OR IGNORE` 式补齐：库为空时写入 54 条样例；
   同 `(module, id)` 已有记录（无论是 API 登记的还是动作流转过的）一律保留，**样例永不覆盖**。
2. 全部初始化写入在**一个事务**里完成，中途失败整体回滚；重复执行结果相同（幂等，返回 `inserted: 0`）。
3. `make reset` / `cli reset` 清库重灌纯样例，仅供本地演示；`prod` 环境直接拒绝执行。
4. 迁移或回填后用 `make rebuild` 按**原始业务记录**整体重算概览，再用 `make reconcile` 只读核对。

## 运营概览与运单明细的一致性

- 列表、详情、动作读写的是 `business_rows`（原始业务记录）；运营概览 `overview_snap`
  只允许在写明细的**同一事务**内对全表明细扫描重算，外部代码不直接改它。
- 每次新增/状态动作，相关模块概览随事务提交一起刷新；要么都成功要么都回滚。
- 跨天（参考日变化）或历史快照漂移时，读概览会自动按明细重算；
  `GET /api/overview` 返回 `ref_date`，`GET /api/health` 返回一致性结论。
- 统计口径（全部以明细行上的标记逐行累加，可逐条回溯）：
  - **在册总量**：该模块全部业务记录数
  - **当日新增**：模块 `date_field` 取值等于参考自然日的记录数（车辆/司机/线路/机组/月台/包装/断链
    这类资源档案没有“当日新增”口径，展示为 `—`，不计入卡片“当日新增”）
  - **待处理**：明细 `pending=true` 的条数（未到状态序列终态）
  - **异常量**：明细 `abnormal=true` 的条数（如油料“驳回记录”）
- 模块的字段与状态口径统一登记在 `app/registry.py`，前后端展示名、筛选字段、
  必填字段都从这里取，不允许在概览侧另写一套。

## 运维命令（构建/迁移/回填/部署）

```bash
make test          # 后端 19 个用例（事务回滚、幂等、运行数据优先、概览对账、端到端）
make build         # 前端生产构建（vue-tsc 类型检查 + vite build -> frontend/dist）
make rebuild       # 迁移/回填：按原始业务记录在一个事务里整体重算概览
make reconcile     # 只读核对概览与明细，对得上退出码 0，有漂移退出码 2
make reset         # 仅本地：清库重灌样例
make docker-build  # 构建镜像
make up            # compose 起后端（含健康检查、数据卷）+ 前端（nginx:80/5173）
make down          # 停服（保留数据卷 backend_data）
```

直接用 CLI 也可以：

```bash
cd backend
.venv/bin/python -m app.cli init        # 建表+幂等初始化（可重复执行）
.venv/bin/python -m app.cli rebuild     # 回填重算
.venv/bin/python -m app.cli reconcile   # 一致性核对
.venv/bin/python -m app.cli reset       # 本地演示重灌
```

部署示例（不写样例、用真实库文件）：

```bash
APP_ENV=prod \
APP_SEED_ON_STARTUP=false \
APP_DATABASE_URL=sqlite:////data/coldchain/app.db \
APP_CORS_ORIGINS=https://ops.example.com \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
# 首次部署或迁移后：python -m app.cli init && python -m app.cli rebuild
```

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 发运单管理 | `shipment` | 发运单 | 运单编号、发货方、收货方 |
| 温控监测 | `temp_monitor` | 温度记录 | 记录编号、运单编号、当前温度 |
| 车辆调度 | `vehicle` | 冷藏车辆 | 车辆编号、车牌号、车型类别 |
| 司机管理 | `driver` | 驾驶人员 | 司机编号、姓名、驾驶证号 |
| 冷库运营 | `cold_storage` | 冷库库区 | 库区编号、库区名称、设定温度 |
| 装卸作业 | `loading` | 装卸记录 | 记录编号、运单编号、装卸类型 |
| 报警管理 | `alert` | 报警记录 | 报警编号、报警类型、关联设备 |
| 线路规划 | `route` | 运输线路 | 线路编号、始发地、到达地 |
| 制冷机组 | `reefer_unit` | 制冷设备 | 机组编号、所属车辆、机组型号 |
| 油料管理 | `fuel` | 加油记录 | 记录编号、车辆编号、油料类型 |
| 签收回单 | `delivery` | 签收记录 | 签收编号、运单编号、签收人 |
| 断链追溯 | `break_chain` | 断链事件 | 事件编号、运单编号、断链环节 |
| 月台管理 | `dock` | 装卸月台 | 月台编号、月台类型、温层分区 |
| 包装管理 | `package` | 保温包装 | 包装编号、包装类型、保温材料 |
| 通行费用 | `toll` | 过路记录 | 记录编号、车辆编号、收费站名称 |
| 车辆消杀 | `sanitation` | 消杀记录 | 消杀编号、车辆编号、消杀方式 |
| 承运合同 | `contract` | 运输合同 | 合同编号、托运方、承运方 |
| 货运保险 | `insurance` | 保险单 | 保单编号、运单编号、投保险种 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 状态序列、必填字段、关键字段、日期字段等口径统一登记在 `app/registry.py`，
  service 基类 `app/services/base.py` 据此实现筛选/登记/流转，不在各模块复制。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断；任何写操作都经 store 事务，
  概览随事务刷新。
