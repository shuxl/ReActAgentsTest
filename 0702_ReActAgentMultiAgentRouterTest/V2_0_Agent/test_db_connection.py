"""
数据库连接测试脚本
测试PostgreSQL数据库连接池是否正常工作
"""
import asyncio
import sys
import os

# 添加当前目录到路径（utils在当前目录下）
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.database import get_db_pool
from utils.config import Config


async def test_database_connection():
    """测试数据库连接"""
    print("=" * 50)
    print("数据库连接测试")
    print("=" * 50)
    
    try:
        # 获取数据库连接池
        db_pool = get_db_pool()
        print(f"✓ 数据库连接池创建成功")
        print(f"  - 数据库URI: {Config.DB_URI}")
        print(f"  - 最小连接数: {Config.MIN_SIZE}")
        print(f"  - 最大连接数: {Config.MAX_SIZE}")
        
        # 创建连接池
        await db_pool.create_pool()
        print(f"✓ 连接池初始化成功")
        
        # 测试连接：执行简单查询
        print("\n测试数据库连接...")
        pool = db_pool.pool
        if pool:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # 使用显式列名，因为dict_row返回字典
                    await cur.execute("SELECT 1 AS test_value")
                    result = await cur.fetchone()
                    # dict_row返回字典，需要使用列名访问
                    if result and result.get('test_value') == 1:
                        print("✓ 数据库连接测试成功")
                    else:
                        print(f"✗ 数据库连接测试失败：返回结果异常 {result}")
                        return False
            
            # 测试数据库版本查询
            print("\n测试数据库版本查询...")
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT version() AS version")
                    version = await cur.fetchone()
                    if version:
                        # dict_row返回字典，需要使用列名访问
                        print(f"✓ 数据库版本: {version.get('version')}")
            
            # 测试连接池状态
            print(f"\n连接池状态:")
            print(f"  - 连接池已创建")
            print(f"  - 最小连接数: {Config.MIN_SIZE}")
            print(f"  - 最大连接数: {Config.MAX_SIZE}")
        
        # 关闭连接池
        await db_pool.close()
        print("\n✓ 连接池已关闭")
        
        print("\n" + "=" * 50)
        print("✓ 所有测试通过！")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\n✗ 数据库连接测试失败: {str(e)}")
        print("\n" + "=" * 50)
        print("✗ 测试失败！")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_database_connection())
    sys.exit(0 if success else 1)

