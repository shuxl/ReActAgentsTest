import asyncio
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent  # 使用新的 API，替代已弃用的 langgraph.prebuilt.create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from typing import Dict, List, Any
from typing import Callable
from langchain_core.tools import BaseTool, tool as create_tool
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt, Command
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.llms import get_deepseek_llm




# Author:@南哥AGI研习社 (B站 or YouTube 搜索“南哥AGI研习社”)


# 使用langgraph推荐方式定义大模型
# 通过工具类初始化 DeepSeek LLM
llm = get_deepseek_llm()


# 定义一个函数，用于为工具添加人工审查（human-in-the-loop）功能
# 参数：tool（可调用对象或 BaseTool 对象），interrupt_config（可选的人工中断配置）
# 返回：一个带有人工审查功能的 BaseTool 对象
def add_human_in_the_loop(
        tool: Callable | BaseTool,
        *,
        interrupt_config: HumanInterruptConfig = None,
) -> BaseTool:
    """Wrap a tool to support human-in-the-loop review."""

    # 检查传入的工具是否为 BaseTool 的实例
    if not isinstance(tool, BaseTool):
        # 如果不是 BaseTool，则将可调用对象转换为 BaseTool 对象
        tool = create_tool(tool)

    # 检查是否提供了 interrupt_config 参数
    if interrupt_config is None:
        # 如果未提供，则设置默认的人工中断配置，允许接受、编辑和响应
        interrupt_config = {
            "allow_accept": True,
            "allow_edit": True,
            "allow_respond": True,
        }

    # 使用 create_tool 装饰器定义一个新的工具函数，继承原工具的名称、描述和参数模式
    @create_tool(
        tool.name,
        description=tool.description,
        args_schema=tool.args_schema
    )

    # 定义内部函数，用于处理带有中断逻辑的工具调用
    def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        # 创建一个人为中断请求，包含工具名称、输入参数和配置
        request: HumanInterrupt = {
            "action_request": {
                "action": tool.name,
                "args": tool_input
            },
            "config": interrupt_config,
            "description": "Please review the tool call"
        }
        # 调用 interrupt 函数，获取人工审查的响应（取第一个响应）
        response = interrupt([request])[0]
        # 检查响应类型是否为“接受”（accept）
        if response["type"] == "accept":
            # 如果接受，直接调用原始工具并传入输入参数和配置
            tool_response = tool.invoke(tool_input, config)
        # 检查响应类型是否为“编辑”（edit）
        elif response["type"] == "edit":
            # 如果是编辑，更新工具输入参数为响应中提供的参数
            tool_input = response["args"]["args"]
            # 使用更新后的参数调用原始工具
            tool_response = tool.invoke(tool_input, config)
        # 检查响应类型是否为“响应”（response）
        elif response["type"] == "response":
            # 如果是响应，直接将用户反馈作为工具的响应
            user_feedback = response["args"]
            tool_response = user_feedback
        # 如果响应类型不被支持，则抛出异常
        else:
            raise ValueError(f"Unsupported interrupt response type: {response['type']}")

        # 返回工具的响应结果
        return tool_response

    # 返回包装后的工具函数
    return call_tool_with_interrupt


# @tool("book_hotel",description="提供预订酒店的工具")
@tool("book_hotel",description="需要人工审查/批准的预定酒店的工具")
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


# 定义并运行agent
async def run_agent():
    # 获取工具列表 为工具添加human feedback
    tools = [add_human_in_the_loop(book_hotel)]

    # 基于内存存储的short-term
    checkpointer = InMemorySaver()

    # 定义系统提示词，指导如何使用工具
    # 注意：新的 create_agent API 使用 system_prompt 参数（字符串类型）
    # 而不是 prompt 参数（SystemMessage 类型）
    system_prompt = "你是一个AI助手。"

    # 创建ReAct风格的agent
    # 使用新的 API: langchain.agents.create_agent
    # 替代已弃用的 langgraph.prebuilt.create_react_agent
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,  # 新 API 使用 system_prompt（字符串）而不是 prompt（SystemMessage）
        checkpointer=checkpointer
    )

    # 将定义的agent的graph进行可视化输出保存至本地
    # save_graph_visualization(agent)

    # 定义short-term需使用的thread_id
    config = {"configurable": {"thread_id": "1"}}

    # 1、非流式处理查询
    agent_response = await agent.ainvoke({"messages": [HumanMessage(content="调用工具预定一个汉庭酒店")]}, config)
    # 将返回的messages进行格式化输出
    parse_messages(agent_response['messages'])
    agent_response_content = agent_response["messages"][-1].content
    print(f"agent_response:{agent_response_content}")

    # (1)模拟人类反馈：测试3种反馈方式
    agent_response = agent.invoke(
        # Command(resume=[{"type": "accept"}]),
        # Command(resume=[{"type": "edit", "args": {"args": {"hotel_name": "汉庭酒店(软件园店)"}}}]),
        Command(resume=[{"type": "response", "args": "我不想预定这个酒店了"}]),
        config
    )
    # 将返回的messages进行格式化输出
    parse_messages(agent_response['messages'])
    agent_response_content = agent_response["messages"][-1].content
    print(f"agent_response:{agent_response_content}")

    # # (2)模拟人类反馈：测试多伦反馈
    # agent_response = agent.invoke(
    #     Command(resume=[{"type": "response", "args": "把酒店名称换为：汉庭酒店(软件园店)"}]),
    #     config
    # )
    # # 将返回的messages进行格式化输出
    # parse_messages(agent_response['messages'])
    # agent_response_content = agent_response["messages"][-1].content
    # print(f"agent_response:{agent_response_content}")
    #
    # agent_response = agent.invoke(
    #     Command(resume=[{"type": "accept"}]),
    #     config
    # )
    # # 将返回的messages进行格式化输出
    # parse_messages(agent_response['messages'])
    # agent_response_content = agent_response["messages"][-1].content
    # print(f"agent_response:{agent_response_content}")


    # # 2、流式处理查询
    # async for message_chunk, metadata in agent.astream(
    #         input={"messages": [HumanMessage(content="预定一个汉庭酒店")]},
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
    #
    # # 模拟人类反馈：测试3种反馈方式
    # async for message_chunk, metadata in agent.astream(
    #     # Command(resume=[{"type": "accept"}]),
    #     Command(resume=[{"type": "edit", "args": {"args": {"hotel_name": "汉庭酒店(软件园店)"}}}]),
    #     # Command(resume=[{"type": "response", "args": "我不想预定这个酒店了"}]),
    #     config,
    #     stream_mode="messages"
    # ):
    #     # 测试原始输出
    #     # print(f"Token:{message_chunk}\n")
    #     # print(f"Metadata:{metadata}\n\n")
    #
    #     # 跳过工具输出
    #     # if metadata["langgraph_node"]=="tools":
    #     #     continue
    #     # 输出最终结果
    #     if message_chunk.content:
    #         print(message_chunk.content, end="|", flush=True)



if __name__ == "__main__":
    asyncio.run(run_agent())




