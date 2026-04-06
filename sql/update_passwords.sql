-- 更新所有用户的密码哈希，使用统一的算法
-- 注意：这个脚本需要在Supabase的SQL Editor中执行

-- 1. 首先，创建一个函数来生成密码哈希
CREATE OR REPLACE FUNCTION generate_password_hash(password TEXT) RETURNS TEXT AS $$
BEGIN
    -- 使用PostgreSQL的crypt函数生成密码哈希
    -- 这里使用bcrypt算法，成本因子为10
    RETURN crypt(password, gen_salt('bf', 10));
END;
$$ LANGUAGE plpgsql;

-- 2. 更新admin用户的密码哈希
UPDATE sys_user 
SET password_hash = generate_password_hash('Admin123!') 
WHERE username = 'admin';

-- 3. 更新其他用户的密码哈希（使用默认密码Demo123!）
UPDATE sys_user 
SET password_hash = generate_password_hash('Demo123!') 
WHERE username != 'admin';

-- 4. 验证更新结果
SELECT username, LEFT(password_hash, 20) || '...' as password_hash_prefix 
FROM sys_user;

-- 5. 清理临时函数
DROP FUNCTION IF EXISTS generate_password_hash(TEXT);

-- 执行完成后，所有用户的密码哈希将使用统一的bcrypt算法
-- admin用户的密码：Admin123!
-- 其他用户的密码：Demo123!
