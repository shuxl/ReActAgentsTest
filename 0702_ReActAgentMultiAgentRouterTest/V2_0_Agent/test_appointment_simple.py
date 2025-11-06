"""
简化版复诊预约测试
只测试新增预约功能，并验证数据库中的记录
"""
import asyncio
import sys
import os
import logging
from langchain_core.messages import HumanMessage

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from utils.config import Config
from utils.database import get_db_pool
from utils.router_graph import create_router_agent
from utils.logging_config import setup_logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

# 设置统一的日志配置
setup_logging()

logger = logging.getLogger(__name__)


async def ensure_appointment_table_exists(pool):
    """
    确保appointments表存在
    如果表不存在，则创建表结构
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                # 检查表是否存在
                await cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'appointments'
                    )
                """)
                table_exists = await cur.fetchone()
                
                if not table_exists or not table_exists.get('exists'):
                    # 表不存在，创建表
                    print("正在创建appointments表...")
                    await cur.execute("""
                        CREATE TABLE IF NOT EXISTS appointments (
                            id SERIAL PRIMARY KEY,
                            user_id VARCHAR(255) NOT NULL,
                            department VARCHAR(255) NOT NULL,
                            doctor_id VARCHAR(255),
                            doctor_name VARCHAR(255),
                            appointment_date TIMESTAMP NOT NULL,
                            status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled')),
                            notes TEXT,
                            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    print("✓ 表创建成功")
                    
                    # 创建索引（如果不存在）
                    indexes = [
                        "CREATE INDEX IF NOT EXISTS idx_appointments_user_id ON appointments(user_id)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_appointment_date ON appointments(appointment_date)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status)",
                        "CREATE INDEX IF NOT EXISTS idx_appointments_user_status ON appointments(user_id, status)"
                    ]
                    for index_sql in indexes:
                        try:
                            await cur.execute(index_sql)
                        except Exception as e:
                            print(f"⚠ 索引创建警告: {str(e)}")
                else:
                    print("✓ 表结构验证通过")
                
    except Exception as e:
        print(f"⚠ 表结构检查/创建失败: {str(e)}")
        import traceback
        traceback.print_exc()


async def query_appointments_from_db(pool, user_id: str):
    """
    直接从数据库查询预约记录
    
    Args:
        pool: 数据库连接池
        user_id: 用户ID
        
    Returns:
        list: 预约记录列表
    """
    try:
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT id, user_id, department, doctor_id, doctor_name, 
                           appointment_date, status, notes, created_at, updated_at
                    FROM appointments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                rows = await cur.fetchall()
                return rows
    except Exception as e:
        logger.error(f"查询数据库失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


async def test_appointment_booking():
    """
    测试创建复诊预约功能
    """
    print("=" * 60)
    print("简化版复诊预约测试")
    print("=" * 60)
    
    # 初始化数据库连接池
    db_pool = get_db_pool()
    await db_pool.create_pool()
    
    # 确保表结构正确
    await ensure_appointment_table_exists(db_pool.pool)
    
    # 初始化checkpointer和store
    checkpointer = AsyncPostgresSaver(db_pool.pool)
    await checkpointer.setup()
    
    store = AsyncPostgresStore(db_pool.pool)
    await store.setup()
    
    # 创建路由智能体（需要传递pool）
    router_agent = await create_router_agent(checkpointer=checkpointer, pool=db_pool.pool, store=store)
    
    # 测试用户ID和会话ID
    user_id = "test_user_appt_simple_001"
    session_id = "test_session_appt_simple_001"
    
    config = {"configurable": {"thread_id": session_id, "recursion_limit": 50}}
    
    print("\n[步骤1] 查询测试前的数据库记录")
    print("-" * 60)
    rows_before = await query_appointments_from_db(db_pool.pool, user_id)
    print(f"测试前数据库中的记录数: {len(rows_before)}")
    if rows_before:
        print("现有记录:")
        for idx, row in enumerate(rows_before, 1):
            print(f"  {idx}. ID={row['id']}, 科室={row['department']}, "
                  f"时间={row['appointment_date']}, 状态={row['status']}")
    else:
        print("  数据库中暂无记录")
    
    print("\n[步骤2] 调用智能体创建预约")
    print("-" * 60)
    print("用户输入: 我想预约复诊，科室是心内科，时间是明天下午2点")
    
    state_input = {
        "messages": [HumanMessage(content="我想预约复诊，科室是心内科，时间是明天下午2点")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result = await router_agent.ainvoke(state_input, config=config)
        messages = result.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                print(f"智能体回复: {last_msg.content}")
            else:
                print(f"智能体回复: {str(last_msg)}")
        
        print(f"\n状态信息:")
        print(f"  当前意图: {result.get('current_intent')}")
        print(f"  当前智能体: {result.get('current_agent')}")
        
        # 检查是否有工具调用
        tool_calls_found = False
        for msg in messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_calls_found = True
                print(f"\n检测到工具调用: {len(msg.tool_calls)} 个")
                for tc in msg.tool_calls:
                    print(f"  - 工具: {tc.get('name', 'unknown')}, 参数: {tc.get('args', {})}")
        
        if not tool_calls_found:
            print("\n⚠ 警告：未检测到工具调用")
        
        print("✓ 智能体调用完成")
    except Exception as e:
        print(f"✗ 智能体调用失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    # 等待一小段时间，确保数据库操作完成
    await asyncio.sleep(1)
    
    print("\n[步骤3] 查询测试后的数据库记录")
    print("-" * 60)
    rows_after = await query_appointments_from_db(db_pool.pool, user_id)
    print(f"测试后数据库中的记录数: {len(rows_after)}")
    
    if rows_after:
        print("\n数据库中的预约记录:")
        for idx, row in enumerate(rows_after, 1):
            print(f"\n记录 {idx}:")
            print(f"  ID: {row['id']}")
            print(f"  用户ID: {row['user_id']}")
            print(f"  科室: {row['department']}")
            print(f"  医生ID: {row['doctor_id']}")
            print(f"  医生姓名: {row['doctor_name']}")
            print(f"  预约时间: {row['appointment_date']}")
            print(f"  状态: {row['status']}")
            print(f"  备注: {row['notes']}")
            print(f"  创建时间: {row['created_at']}")
            print(f"  更新时间: {row['updated_at']}")
        
        # 对比记录数
        if len(rows_after) > len(rows_before):
            new_records = len(rows_after) - len(rows_before)
            print(f"\n✓ 成功！新增了 {new_records} 条预约记录")
        else:
            print(f"\n✗ 失败！记录数未增加（测试前: {len(rows_before)}, 测试后: {len(rows_after)}）")
    else:
        print("\n✗ 失败！数据库中未找到任何预约记录")
    
    # 清理资源
    await db_pool.close()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_appointment_booking())

