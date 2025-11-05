"""
Redis连接测试脚本
测试Redis连接是否正常工作
"""
import asyncio
import sys
import os

# 添加当前目录到路径（utils在当前目录下）
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.redis_manager import get_redis_manager
from utils.config import Config


async def test_redis_connection():
    """测试Redis连接"""
    print("=" * 50)
    print("Redis连接测试")
    print("=" * 50)
    
    try:
        # 获取Redis管理器
        redis_manager = get_redis_manager()
        print(f"✓ Redis管理器创建成功")
        print(f"  - Redis主机: {Config.REDIS_HOST}")
        print(f"  - Redis端口: {Config.REDIS_PORT}")
        print(f"  - Redis数据库: {Config.REDIS_DB}")
        
        # 测试连接：PING命令
        print("\n测试Redis连接...")
        ping_result = await redis_manager.ping()
        if ping_result:
            print("✓ Redis连接测试成功 (PING响应正常)")
        else:
            print("✗ Redis连接测试失败：PING无响应")
            return False
        
        # 测试基本操作：SET/GET
        print("\n测试基本操作...")
        test_key = "test:connection"
        test_value = "test_value_123"
        
        # SET操作
        set_result = await redis_manager.set(test_key, test_value, ex=60)
        if set_result:
            print(f"✓ SET操作成功: {test_key} = {test_value}")
        else:
            print("✗ SET操作失败")
            return False
        
        # GET操作
        get_result = await redis_manager.get(test_key)
        if get_result == test_value:
            print(f"✓ GET操作成功: {test_key} = {get_result}")
        else:
            print(f"✗ GET操作失败：期望值={test_value}, 实际值={get_result}")
            return False
        
        # EXISTS操作
        exists_result = await redis_manager.exists(test_key)
        if exists_result:
            print(f"✓ EXISTS操作成功: {test_key} 存在")
        else:
            print(f"✗ EXISTS操作失败: {test_key} 不存在")
            return False
        
        # DELETE操作
        delete_count = await redis_manager.delete(test_key)
        if delete_count == 1:
            print(f"✓ DELETE操作成功: 删除了 {delete_count} 个键")
        else:
            print(f"✗ DELETE操作失败: 删除了 {delete_count} 个键")
            return False
        
        # 验证删除
        exists_after_delete = await redis_manager.exists(test_key)
        if not exists_after_delete:
            print(f"✓ 删除验证成功: {test_key} 已不存在")
        else:
            print(f"✗ 删除验证失败: {test_key} 仍存在")
            return False
        
        # 关闭连接
        await redis_manager.close()
        print("\n✓ Redis连接已关闭")
        
        print("\n" + "=" * 50)
        print("✓ 所有测试通过！")
        print("=" * 50)
        return True
        
    except Exception as e:
        print(f"\n✗ Redis连接测试失败: {str(e)}")
        print("\n" + "=" * 50)
        print("✗ 测试失败！")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_redis_connection())
    sys.exit(0 if success else 1)

