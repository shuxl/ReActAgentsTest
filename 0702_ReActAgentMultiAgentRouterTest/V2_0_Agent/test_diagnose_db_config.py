"""
数据库连接配置诊断脚本
帮助用户检查数据库连接配置是否正确
"""
import sys
import os
from urllib.parse import urlparse, parse_qs

# 添加当前目录到路径（utils在当前目录下）
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.config import Config


def diagnose_database_config():
    """诊断数据库配置"""
    print("=" * 60)
    print("数据库连接配置诊断")
    print("=" * 60)
    
    print("\n1. 检查数据库URI配置...")
    db_uri = Config.DB_URI
    print(f"   数据库URI: {db_uri}")
    
    if not db_uri:
        print("   ✗ 数据库URI为空！")
        return False
    
    try:
        # 解析URI
        parsed = urlparse(db_uri)
        print(f"   ✓ URI格式正确")
        print(f"   - 协议: {parsed.scheme}")
        print(f"   - 用户名: {parsed.username}")
        print(f"   - 密码: {'*' * len(parsed.password) if parsed.password else '未设置'}")
        print(f"   - 主机: {parsed.hostname}")
        print(f"   - 端口: {parsed.port}")
        print(f"   - 数据库名: {parsed.path.lstrip('/')}")
        
        # 检查必需字段
        if not parsed.hostname:
            print("   ✗ 主机地址未设置")
            return False
        
        if not parsed.port:
            print("   ✗ 端口未设置")
            return False
        
        if not parsed.path or parsed.path == '/':
            print("   ✗ 数据库名未设置")
            return False
        
        if not parsed.username:
            print("   ✗ 用户名未设置")
            return False
        
        print("   ✓ 所有必需字段已设置")
        
    except Exception as e:
        print(f"   ✗ URI解析失败: {str(e)}")
        return False
    
    print("\n2. 检查连接池配置...")
    print(f"   - 最小连接数: {Config.MIN_SIZE}")
    print(f"   - 最大连接数: {Config.MAX_SIZE}")
    
    if Config.MIN_SIZE <= 0:
        print("   ✗ 最小连接数必须大于0")
        return False
    
    if Config.MAX_SIZE < Config.MIN_SIZE:
        print("   ✗ 最大连接数必须大于等于最小连接数")
        return False
    
    print("   ✓ 连接池配置正确")
    
    print("\n3. 检查环境变量...")
    env_vars = {
        "DB_URI": os.getenv("DB_URI"),
        "REDIS_HOST": os.getenv("REDIS_HOST"),
        "REDIS_PORT": os.getenv("REDIS_PORT"),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
    }
    
    for var_name, var_value in env_vars.items():
        if var_value:
            if var_name == "DEEPSEEK_API_KEY":
                print(f"   ✓ {var_name}: {'*' * 20} (已设置)")
            else:
                print(f"   ✓ {var_name}: {var_value}")
        else:
            print(f"   ⚠ {var_name}: 未设置（使用默认值）")
    
    print("\n4. 配置建议...")
    print("   如果连接失败，请检查以下事项：")
    print("   1. PostgreSQL服务是否正在运行")
    print("   2. 数据库主机地址和端口是否正确")
    print("   3. 数据库用户名和密码是否正确")
    print("   4. 数据库名称是否存在")
    print("   5. 防火墙是否允许连接")
    print("   6. PostgreSQL的pg_hba.conf是否允许该连接")
    
    print("\n5. 测试连接命令...")
    print("   可以使用以下命令测试数据库连接：")
    print(f"   psql -h {parsed.hostname} -p {parsed.port} -U {parsed.username} -d {parsed.path.lstrip('/')}")
    
    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = diagnose_database_config()
    sys.exit(0 if success else 1)

