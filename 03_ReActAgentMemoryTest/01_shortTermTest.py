import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from langchain_core.tools import tool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Dict, List, Any
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from utils.llms import get_deepseek_llm



# Author:@南哥AGI研习社 (B站 or YouTube 搜索“南哥AGI研习社”)


# 使用langgraph推荐方式定义大模型
# 通过工具类初始化 DeepSeek LLM
llm = get_deepseek_llm()


# @tool("book_hotel",description="提供预订酒店的工具")
@tool("book_hotel",description="预定酒店的工具")
def book_hotel(hotel_name: str):
    return f"成功预定了在{hotel_name}的住宿。"


# 解析消息列表
def parse_messages(messages: List[Any]) -> None:
    """
    解析消息列表，打印 HumanMessage、AIMessage 和 ToolMessage 的详细信息

    Args:
        messages: 包含消息的列表，每个消息是一个对象
    """
    print("=== 消息解析结果 ===")
    for idx, msg in enumerate(messages, 1):
        print(f"\n消息 {idx}:")
        # 获取消息类型
        msg_type = msg.__class__.__name__
        print(f"类型: {msg_type}")
        # 提取消息内容
        content = getattr(msg, 'content', '')
        print(f"内容: {content if content else '<空>'}")
        # 处理附加信息
        additional_kwargs = getattr(msg, 'additional_kwargs', {})
        if additional_kwargs:
            print("附加信息:")
            for key, value in additional_kwargs.items():
                if key == 'tool_calls' and value:
                    print("  工具调用:")
                    for tool_call in value:
                        print(f"    - ID: {tool_call['id']}")
                        print(f"      函数: {tool_call['function']['name']}")
                        print(f"      参数: {tool_call['function']['arguments']}")
                else:
                    print(f"  {key}: {value}")
        # 处理 ToolMessage 特有字段
        if msg_type == 'ToolMessage':
            tool_name = getattr(msg, 'name', '')
            tool_call_id = getattr(msg, 'tool_call_id', '')
            print(f"工具名称: {tool_name}")
            print(f"工具调用 ID: {tool_call_id}")
        # 处理 AIMessage 的工具调用和元数据
        if msg_type == 'AIMessage':
            tool_calls = getattr(msg, 'tool_calls', [])
            if tool_calls:
                print("工具调用:")
                for tool_call in tool_calls:
                    print(f"  - 名称: {tool_call['name']}")
                    print(f"    参数: {tool_call['args']}")
                    print(f"    ID: {tool_call['id']}")
            # 提取元数据
            metadata = getattr(msg, 'response_metadata', {})
            if metadata:
                print("元数据:")
                token_usage = metadata.get('token_usage', {})
                print(f"  令牌使用: {token_usage}")
                print(f"  模型名称: {metadata.get('model_name', '未知')}")
                print(f"  完成原因: {metadata.get('finish_reason', '未知')}")
        # 打印消息 ID
        msg_id = getattr(msg, 'id', '未知')
        print(f"消息 ID: {msg_id}")
        print("-" * 50)


# 保存状态图的可视化表示
def save_graph_visualization(graph, filename: str = "graph.png") -> None:
    """保存状态图的可视化表示。

    Args:
        graph: 状态图实例。
        filename: 保存文件路径。
    """
    # 尝试执行以下代码块
    try:
        # 以二进制写模式打开文件
        with open(filename, "wb") as f:
            # 将状态图转换为Mermaid格式的PNG并写入文件
            f.write(graph.get_graph().draw_mermaid_png())
        # 记录保存成功的日志
        print(f"Graph visualization saved as {filename}")
    # 捕获IO错误
    except IOError as e:
        # 记录警告日志
        print(f"Failed to save graph visualization: {e}")


# 每次在调用 LLM 的节点之前，都会调用该函数
# 修剪聊天历史以满足 token 数量或消息数量的限制
def pre_model_hook(state):
    trimmed_messages = trim_messages(
        messages = state["messages"],
        # 限制为 4 条消息
        max_tokens=4,
        strategy="last",
        # 使用 len 计数消息数量
        token_counter=len,
        start_on="human",
        include_system=True,
        allow_partial=False,
    )
    # trimmed_messages = trim_messages(
    #     messages = state["messages"],
    #     strategy="last",
    #     token_counter=count_tokens_approximately,
    #     max_tokens=20,
    #     start_on="human",
    #     end_on=("human", "tool"),
    # )
    # 可以在 `llm_input_messages` 或 `messages` 键下返回更新的信息
    return {"llm_input_messages": trimmed_messages}


# 定义并运行agent
async def run_agent():
    # 追加自定义工具列表
    tools = [book_hotel]

    # 定义系统消息，指导如何使用工具
    system_message = SystemMessage(content=(
        "你是一个AI助手。"
    ))

    # 基于数据库持久化存储的short-term
    db_uri = "postgresql://postgres:sxl_pwd_123@localhost:5433/sxl_pg_db1?sslmode=disable"

    # short-term短期记忆 实例化PostgresSaver对象 并初始化checkpointer
    async with AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer:
        await checkpointer.setup()

        # 创建ReAct风格的agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_message,
            # 一个可选的节点，用于添加在agent节点之前
            # pre_model_hook=pre_model_hook,
            checkpointer=checkpointer,
        )

        # 将定义的agent的graph进行可视化输出保存至本地
        save_graph_visualization(agent)

        # 定义thread_id
        config = {"configurable": {"thread_id": "1"}}

        # 获取线程对关联的state
        # state_result = await checkpointer.aget_tuple(config)
        # print(f"当前状态内容:{state_result}")

        # 将检索出的信息拼接到用户输入中
        # user_input = "我叫什么"
        # user_input = "我是南哥"
        # user_input = "我叫什么"
        user_input = "预定一个汉庭酒店"
        # user_input = f"我叫什么"


        # 1、非流式处理查询
        agent_response = await agent.ainvoke({"messages": [HumanMessage(content=user_input)]}, config)
        # 将返回的messages进行格式化输出
        # print(f"agent_response:{agent_response}")
        parse_messages(agent_response['messages'])
        agent_response_content = agent_response["messages"][-1].content
        print(f"final response: {agent_response_content}")

        # # 2、流式处理查询
        # async for message_chunk, metadata in agent.astream(
        #         input={"messages": [HumanMessage(content=user_input)]},
        #         config=config,
        #         stream_mode="messages"
        # ):
        #     # 测试原始输出
        #     # print(f"Token:{message_chunk}\n")
        #     # print(f"Metadata:{metadata}\n\n")
        #
        #     # 跳过工具输出
        #     # if metadata["langgraph_node"]=="tools":
        #     #     continue
        #
        #     # 输出最终结果
        #     if message_chunk.content:
        #         print(message_chunk.content, end="|", flush=True)



if __name__ == "__main__":
    asyncio.run(run_agent())




