"""
查询和显示存储在 PostgreSQL 中的聊天历史记录

这个脚本用于查看 AsyncPostgresSaver 存储的聊天上下文数据
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from utils.llms import get_deepseek_llm


async def query_chat_history(thread_id: str = "1"):
    """查询指定 thread_id 的聊天历史"""
    
    # 数据库连接字符串
    db_uri = "postgresql://postgres:sxl_pwd_123@localhost:5433/sxl_pg_db1?sslmode=disable"
    
    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        # 确保表已创建
        await checkpointer.setup()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        print(f"正在查询 thread_id = '{thread_id}' 的聊天历史...")
        print("=" * 80)
        
        # 创建一个简单的 agent 来获取状态
        from langgraph.prebuilt import create_react_agent
        from langchain_core.messages import SystemMessage
        
        # 需要一个真实的模型来创建 agent
        llm = get_deepseek_llm()
        
        # 创建一个简单的 agent（不需要实际运行）
        agent = create_react_agent(
            model=llm,
            tools=[],
            checkpointer=checkpointer,
        )
        
        # 获取当前状态
        try:
            state = await agent.aget_state(config)
            if state is None or 'messages' not in state.values:
                print(f"❌ 未找到 thread_id = '{thread_id}' 的聊天记录")
                return
            
            messages = state.values.get('messages', [])
            
            print(f"\n✅ 找到聊天记录！")
            print(f"状态版本: {state.config.get('configurable', {}).get('checkpoint_ns', 'default')}")
            print(f"\n{'=' * 80}")
            
            print(f"\n📝 聊天消息历史 (共 {len(messages)} 条消息):")
            print("=" * 80)
            
            for idx, msg in enumerate(messages, 1):
                msg_type = msg.__class__.__name__
                
                print(f"\n消息 {idx}:")
                print(f"  类型: {msg_type}")
                
                if isinstance(msg, HumanMessage):
                    print(f"  内容: {msg.content}")
                elif isinstance(msg, AIMessage):
                    print(f"  内容: {msg.content}")
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        print(f"  工具调用: {msg.tool_calls}")
                elif isinstance(msg, ToolMessage):
                    print(f"  工具名称: {msg.name}")
                    print(f"  工具调用 ID: {msg.tool_call_id}")
                    print(f"  内容: {msg.content}")
                elif isinstance(msg, SystemMessage):
                    print(f"  内容: {msg.content}")
                else:
                    print(f"  内容: {getattr(msg, 'content', '<无内容>')}")
                
                # 显示消息 ID
                if hasattr(msg, 'id'):
                    print(f"  消息 ID: {msg.id}")
                
                print("-" * 80)
        
        except Exception as e:
            print(f"❌ 查询失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return


async def list_all_threads():
    """列出所有已存储的 thread_id"""
    
    db_uri = "postgresql://postgres:sxl_pwd_123@localhost:5433/sxl_pg_db1?sslmode=disable"
    
    import psycopg
    
    async with await psycopg.AsyncConnection.connect(db_uri) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT DISTINCT thread_id, COUNT(*) as checkpoint_count
                FROM checkpoints
                GROUP BY thread_id
                ORDER BY thread_id
            """)
            
            results = await cur.fetchall()
            
            if results:
                print("\n📋 所有已存储的会话 (thread_id):")
                print("=" * 80)
                for thread_id, count in results:
                    print(f"  thread_id: {thread_id} (检查点数量: {count})")
            else:
                print("\n⚠️  数据库中没有任何聊天记录")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="查询聊天历史记录")
    parser.add_argument("--thread-id", "-t", default="1", help="要查询的 thread_id (默认: 1)")
    parser.add_argument("--list", "-l", action="store_true", help="列出所有 thread_id")
    
    args = parser.parse_args()
    
    if args.list:
        asyncio.run(list_all_threads())
    else:
        asyncio.run(query_chat_history(args.thread_id))

