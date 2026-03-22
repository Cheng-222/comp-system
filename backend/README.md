# backend 目录说明

本目录已落地 Flask 后端首版可运行工程。

## 当前实现
- `run.py`：后端启动入口
- `app/__init__.py`：应用工厂、蓝图注册、异常处理、自动建表与种子数据
- `app/models.py`：系统、学生、赛事、报名、材料、流转、通知等核心表模型
- `app/blueprints/`：认证、系统、学生、赛事、报名、消息模块接口
- `requirements.txt`：后端依赖

## 主要能力
- 统一响应结构：`code + message + data + traceId`
- 统一异常处理与 404 / 500 返回
- Token 鉴权与角色权限控制
- 自动初始化演示角色、账号、示例学生与赛事
- 支持通过 `DATABASE_URL` 切换到 SQLite 做本地冒烟验证

## 启动方式
```bash
python3 -m pip install --target .deps -r requirements.txt
PYTHONPATH=.deps:. python3 run.py
```

## 演示账号
- `admin / Admin123!`
- `teacher / Demo123!`
- `reviewer / Demo123!`
- `20260001 / Demo123!`
