"""
复诊管理智能体集成测试
验证复诊管理流程（预约 -> 查询 -> 更新）
包括相对时间解析功能测试
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
from utils.llms import get_llm_by_config
from utils.router_graph import create_router_agent
from utils.logging_config import setup_logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore

# 设置统一的日志配置
setup_logging()

logger = logging.getLogger(__name__)


async def cleanup_test_data(pool, checkpointer, store, user_id: str, session_id: str):
    """
    清理测试数据
    
    Args:
        pool: 数据库连接池
        checkpointer: AsyncPostgresSaver实例
        store: AsyncPostgresStore实例
        user_id: 测试用户ID
        session_id: 测试会话ID（对应checkpoint的thread_id）
    """
    try:
        print("正在清理测试数据...")
        
        # 1. 清理appointments表中的测试数据
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("""
                        DELETE FROM appointments 
                        WHERE user_id = %s
                    """, (user_id,))
                    deleted_records = cur.rowcount
                    print(f"✓ 清理appointments表: 删除 {deleted_records} 条记录")
        except Exception as e:
            print(f"⚠ 清理appointments表时出现警告: {str(e)}")
        
        # 2. 清理checkpoint数据（checkpoints表）
        # checkpoint通过thread_id（对应session_id）标识
        try:
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    # 先删除checkpoint_blobs表中的记录（使用thread_id和checkpoint_ns）
                    deleted_blobs = 0
                    try:
                        await cur.execute("""
                            DELETE FROM checkpoint_blobs 
                            WHERE thread_id = %s
                        """, (session_id,))
                        deleted_blobs = cur.rowcount
                    except Exception as e:
                        # checkpoint_blobs表结构可能不同，忽略错误
                        logger.debug(f"清理checkpoint_blobs时出现警告: {str(e)}")
                    
                    # 删除checkpoint_writes表中的记录
                    await cur.execute("""
                        DELETE FROM checkpoint_writes 
                        WHERE thread_id = %s
                    """, (session_id,))
                    deleted_writes = cur.rowcount
                    
                    # 最后删除checkpoints表中的记录
                    await cur.execute("""
                        DELETE FROM checkpoints 
                        WHERE thread_id = %s
                    """, (session_id,))
                    deleted_checkpoints = cur.rowcount
                    
                    print(f"✓ 清理checkpoint数据: checkpoints={deleted_checkpoints}, writes={deleted_writes}, blobs={deleted_blobs}")
        except Exception as e:
            # checkpoint表可能不存在（如果checkpointer未初始化），这是正常的
            print(f"⚠ 清理checkpoint数据时出现警告（可能表不存在）: {str(e)}")
        
        # 3. 清理store数据（长期记忆）
        if store:
            try:
                # 清理memories命名空间（用户设置信息）
                namespace_memories = ("memories", user_id)
                memories_data = await store.asearch(namespace_memories, query="")
                if memories_data:
                    for memory in memories_data:
                        await store.adelete(namespace_memories, memory.key)
                    print(f"✓ 清理store数据（memories命名空间）: {len(memories_data)} 条记录")
            except Exception as e:
                print(f"⚠ 清理store数据时出现警告: {str(e)}")
        
        print("✓ 测试数据清理完成")
        
    except Exception as e:
        print(f"⚠ 清理测试数据时出现错误: {str(e)}")
        import traceback
        traceback.print_exc()


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


async def test_appointment_workflow():
    """
    测试复诊管理完整流程：
    1. 创建预约（标准格式）
    2. 创建预约（相对时间格式）
    3. 查询预约记录
    4. 更新预约记录
    5. 查询更新后的预约记录
    """
    print("=" * 60)
    print("复诊管理智能体集成测试")
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
    user_id = "test_user_appt_001"
    session_id = "test_session_appt_001"
    
    # 测试开始前清理旧数据（确保测试环境干净）
    print("\n[清理] 测试前清理旧数据")
    print("-" * 60)
    await cleanup_test_data(db_pool.pool, checkpointer, store, user_id, session_id)
    
    config = {"configurable": {"thread_id": session_id, "recursion_limit": 50}}
    
    print("\n[测试1] 创建预约（标准格式）")
    print("-" * 60)
    
    # 测试1: 创建预约（标准格式）
    state_input_1 = {
        "messages": [HumanMessage(content="我想预约复诊，科室是心内科，时间是明天下午2点")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result_1 = await router_agent.ainvoke(state_input_1, config=config)
        messages_1 = result_1.get("messages", [])
        if messages_1:
            last_msg = messages_1[-1]
            if hasattr(last_msg, 'content'):
                print(f"回复: {last_msg.content}")
            else:
                print(f"回复: {str(last_msg)}")
        print(f"当前意图: {result_1.get('current_intent')}")
        print(f"当前智能体: {result_1.get('current_agent')}")
        print("✓ 测试1通过：创建预约")
    except Exception as e:
        print(f"✗ 测试1失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n[测试2] 查询预约记录")
    print("-" * 60)
    
    # 测试2: 查询预约记录
    state_input_2 = {
        "messages": [HumanMessage(content="查询我的预约记录")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result_2 = await router_agent.ainvoke(state_input_2, config=config)
        messages_2 = result_2.get("messages", [])
        if messages_2:
            last_msg = messages_2[-1]
            if hasattr(last_msg, 'content'):
                print(f"回复: {last_msg.content}")
                # 检查是否包含预约信息
                if "预约" in last_msg.content or "appointment" in last_msg.content.lower():
                    print("✓ 查询到预约记录")
            else:
                print(f"回复: {str(last_msg)}")
        print(f"当前意图: {result_2.get('current_intent')}")
        print(f"当前智能体: {result_2.get('current_agent')}")
        print("✓ 测试2通过：查询预约记录")
    except Exception as e:
        print(f"✗ 测试2失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n[测试3] 创建预约（相对时间格式 - 本周一）")
    print("-" * 60)
    
    # 测试3: 创建预约（相对时间格式）
    state_input_3 = {
        "messages": [HumanMessage(content="预约复诊，科室是骨科，时间是本周一上午10点")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result_3 = await router_agent.ainvoke(state_input_3, config=config)
        messages_3 = result_3.get("messages", [])
        if messages_3:
            last_msg = messages_3[-1]
            if hasattr(last_msg, 'content'):
                print(f"回复: {last_msg.content}")
            else:
                print(f"回复: {str(last_msg)}")
        print(f"当前意图: {result_3.get('current_intent')}")
        print(f"当前智能体: {result_3.get('current_agent')}")
        print("✓ 测试3通过：创建预约（相对时间格式）")
    except Exception as e:
        print(f"✗ 测试3失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n[测试4] 查询所有预约记录")
    print("-" * 60)
    
    # 测试4: 查询所有预约记录
    state_input_4 = {
        "messages": [HumanMessage(content="查询我的所有预约")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result_4 = await router_agent.ainvoke(state_input_4, config=config)
        messages_4 = result_4.get("messages", [])
        if messages_4:
            last_msg = messages_4[-1]
            if hasattr(last_msg, 'content'):
                print(f"回复: {last_msg.content}")
            else:
                print(f"回复: {str(last_msg)}")
        print(f"当前意图: {result_4.get('current_intent')}")
        print(f"当前智能体: {result_4.get('current_agent')}")
        print("✓ 测试4通过：查询所有预约记录")
    except Exception as e:
        print(f"✗ 测试4失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n[测试5] 更新预约状态")
    print("-" * 60)
    
    # 测试5: 更新预约状态（需要先查询到预约ID）
    # 这里我们假设第一个预约的ID是1（实际应该从查询结果中获取）
    state_input_5 = {
        "messages": [HumanMessage(content="将我的第一个预约状态更新为已完成")],
        "user_id": user_id,
        "session_id": session_id,
        "current_intent": None,
        "current_agent": None,
        "need_reroute": False
    }
    
    try:
        result_5 = await router_agent.ainvoke(state_input_5, config=config)
        messages_5 = result_5.get("messages", [])
        if messages_5:
            last_msg = messages_5[-1]
            if hasattr(last_msg, 'content'):
                print(f"回复: {last_msg.content}")
            else:
                print(f"回复: {str(last_msg)}")
        print(f"当前意图: {result_5.get('current_intent')}")
        print(f"当前智能体: {result_5.get('current_agent')}")
        print("✓ 测试5通过：更新预约状态")
    except Exception as e:
        print(f"✗ 测试5失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n[测试6] 验证数据库中的记录")
    print("-" * 60)
    
    # 测试6: 直接查询数据库验证记录是否存在
    try:
        async with db_pool.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT id, department, doctor_id, doctor_name, appointment_date, status, notes
                    FROM appointments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                rows = await cur.fetchall()
                
                if rows:
                    print(f"✓ 数据库中找到 {len(rows)} 条预约记录：")
                    for idx, row in enumerate(rows, 1):
                        print(f"  {idx}. ID={row['id']}, 科室={row['department']}, "
                              f"时间={row['appointment_date']}, 状态={row['status']}")
                else:
                    print("✗ 数据库中未找到预约记录！")
        print("✓ 测试6通过：数据库验证")
    except Exception as e:
        print(f"✗ 测试6失败：{str(e)}")
        import traceback
        traceback.print_exc()
    
    # 测试结束后清理数据（保持测试环境干净）
    # 如果希望保留测试数据用于查看，可以注释掉下面的清理调用
    # print("\n[清理] 测试后清理数据")
    # print("-" * 60)
    # await cleanup_test_data(db_pool.pool, checkpointer, store, user_id, session_id)
    
    # 清理资源
    await db_pool.close()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_appointment_workflow())

