.PHONY: help install backend frontend test backend-test frontend-typecheck \
        migrate seed init recompute-overview reconcile reset docker-build \
        docker-up docker-down clean

# 可重复的本地开发 / 构建 / 部署入口。数据库默认 backend/data/app.db。

help: ## 列出可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  %-22s %s\n", $$1, $$2}'

install: ## 一次性安装前后端依赖
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install

backend: ## 启动后端（自动迁移、补样例，--reload）
	cd backend && ./run.sh

frontend: ## 启动前端 dev server（/api 代理到 8000）
	cd frontend && npm run dev

# ---- 数据库 / 数据口径（在 backend/ 下执行等价 python -m app.cli 命令） ----
migrate: ## 执行数据库迁移（幂等）
	cd backend && .venv/bin/python -m app.cli migrate

seed: ## 事务内补写样例（只补缺失，运行数据优先，幂等）
	cd backend && .venv/bin/python -m app.cli seed

init: ## 迁移 + 播种 + 概览回填（启动同款流程）
	cd backend && .venv/bin/python -m app.cli init

recompute-overview: ## 按原始业务记录重算并回填概览快照
	cd backend && .venv/bin/python -m app.cli recompute-overview

reconcile: ## 概览快照与业务明细对账（不一致退出码 1）
	cd backend && .venv/bin/python -m app.cli reconcile

reset: ## 清空全部运行数据（需 RESET=1 确认，可加 --seed）
	cd backend && .venv/bin/python -m app.cli reset $(if $(RESET),--yes) $(if $(SEED),--seed)

# ---- 测试与构建 ----
test: backend-test frontend-typecheck ## 跑后端测试 + 前端类型检查

backend-test:
	cd backend && .venv/bin/python -m pytest tests/ -q

frontend-typecheck:
	cd frontend && npm run typecheck

docker-build: ## 构建前后端镜像
	docker compose build

docker-up: ## 构建并启动（前端 8080、后端 8000，数据落卷）
	docker compose up --build -d

docker-down: ## 停止容器（数据卷保留）
	docker compose down

clean: ## 删除本地库与构建产物（不动代码）
	rm -rf backend/data frontend/dist
