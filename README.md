# 竞赛管理系统

本项目面向校内外竞赛组织与管理场景，围绕赛事配置、学生报名、材料提交、资格审核、状态流转、消息通知与赛后归档构建平台内闭环的竞赛管理系统。

## 技术栈
- 前端：Vue 3 + Vite + Element Plus
- 后端：Flask + SQLAlchemy
- 数据库：MySQL 8.0（开发验证支持通过 `DATABASE_URL` 切换到 SQLite）
- 部署：Docker Compose

## 目录结构
```text
竞赛管理系统/
├── backend/                 Flask 后端
├── frontend/                Vue 管理端
├── docs/                    规划与设计文档
├── sql/                     初始化与索引脚本
├── scripts/                 冒烟验证脚本
├── deploy/                  部署相关目录
├── uploads/                 上传目录
├── logs/                    日志目录
├── .env.example             环境变量模板
└── docker-compose.yml       本地/Windows 环境启动编排
```

## 快速启动
### 1. 后端启动
```bash
python3 -m pip install --target backend/.deps -r backend/requirements.txt
PYTHONPATH=backend/.deps:backend python3 backend/run.py
```

### 2. 前端启动
```bash
cd frontend
npm install
npm run dev
```

如本地后端不使用 `5000` 端口，可在 `frontend/.env.development` 中修改 `VITE_PROXY_TARGET`。

### 3. Docker Compose 启动
```bash
docker compose up
```

## 演示账号
- 管理员：`admin / Admin123!`
- 竞赛教师：`teacher / Demo123!`
- 审核人员：`reviewer / Demo123!`
- 学生用户：`20260001 / Demo123!`

## 已实现功能范围
- 认证与权限：登录、当前用户、菜单加载、按管理员/教师/审核人/学生控制可见范围与操作权限
- 系统基础：工作台统计、字典数据
- 学生管理：列表、详情、新增、编辑、启停，展示最近报名与赛后结果
- 赛事管理：列表、详情、新增、编辑、发布、状态流转、负责人/审核人分配
- 报名管理：列表、详情、创建、编辑、批量导入、导出、材料提交、材料下载、审核、补正、退赛、换人、补录、流转日志
- 材料与资格：审核队列处理、通过/补正/驳回、资格状态调整、有效名单与历史变更查看
- 通知中心：消息列表、创建、编辑、发送、取消、已读，支持按赛事、角色、状态定向触达，目标角色支持多选
- 赛后管理：成绩列表、详情、新增、编辑、批量导入、证书上传、证书下载、归档导出
- 统计报表：统计概览、获奖分析、未获奖名单、报表导出
- 附件能力：报名材料真实上传下载、成绩导入/报名导入/证书上传统一支持拖拽或点击上传

## 验证方式
```bash
python3 -m pip install --target backend/.deps -r backend/requirements.txt
PYTHONPATH=backend/.deps:backend python3 scripts/smoke_test.py
```
