# scripts 目录说明

## 当前脚本
- `smoke_test.py`：后端首版闭环冒烟验证脚本

## 验证内容
- 登录鉴权
- 学生创建
- 赛事创建与发布
- 报名提交
- 材料提交
- 审核通过
- 通知创建、发送、已读
- 工作台统计检查

## 运行方式
```bash
python3 -m pip install --target backend/.deps -r backend/requirements.txt
PYTHONPATH=backend/.deps:backend python3 scripts/smoke_test.py
```
