.PHONY: help install backend frontend test rebuild reconcile reset docker-build up down logs build

help: ## 列出常用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## 一键安装前后端依赖（可重复执行）
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd frontend && npm install

backend: ## 启动后端（自动建表+幂等初始化，默认 127.0.0.1:8000）
	cd backend && ./run.sh

frontend: ## 启动前端 dev server（默认 127.0.0.1:5173）
	cd frontend && npm run dev

test: ## 运行后端测试（内存库，互不污染）
	cd backend && .venv/bin/python -m pytest

rebuild: ## 迁移/回填：按原始业务记录整体重算运营概览
	cd backend && .venv/bin/python -m app.cli rebuild

reconcile: ## 只读核对概览与运单明细是否一致
	cd backend && .venv/bin/python -m app.cli reconcile

reset: ## 本地演示：清库重灌样例（prod 环境拒绝执行）
	cd backend && .venv/bin/python -m app.cli reset

build: ## 构建前端生产产物（输出 frontend/dist）
	cd frontend && npm run build

docker-build: ## 构建前后端容器镜像
	docker compose build

up: ## 一键起后端+前端（compose，数据落卷）
	docker compose up -d --build

down: ## 停掉 compose 服务（保留数据卷）
	docker compose down

logs: ## 查看 compose 日志
	docker compose logs -f
