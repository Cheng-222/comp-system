import os
import sys
from pathlib import Path

# 添加backend目录到Python路径
sys.path.insert(0, str(Path(__file__).resolve().parent / 'backend'))

from app import create_app
from app.extensions import db
from app.models import SysUser
from app.security import password_hash

# 创建应用实例
app = create_app()

with app.app_context():
    # 获取所有用户
    users = SysUser.query.all()
    
    print(f"找到 {len(users)} 个用户，开始更新密码哈希...")
    
    for user in users:
        # 生成新的密码哈希
        # 注意：这里我们假设所有用户的密码都是其用户名（这是一个临时解决方案）
        # 在实际生产环境中，你应该使用正确的密码
        if user.username == 'admin':
            new_hash = password_hash('Admin123!')
        else:
            # 对于学生用户，使用默认密码
            new_hash = password_hash('Demo123!')
        
        # 更新密码哈希
        user.password_hash = new_hash
        
        print(f"更新用户 {user.username} 的密码哈希")
    
    # 提交更改
    db.session.commit()
    print("所有用户的密码哈希已更新完成！")
