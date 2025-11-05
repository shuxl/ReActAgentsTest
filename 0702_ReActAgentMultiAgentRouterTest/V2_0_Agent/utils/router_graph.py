"""
路由图创建
创建并配置StateGraph路由图
"""
import logging
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from .router_state import RouterState
from .router import router_node, clarify_intent_node, route_decision
from .config import Config

logger = logging.getLogger(__name__)


def placeholder_agent_node(state: RouterState) -> RouterState:
    """
    占位智能体节点
    在专门智能体实现之前，返回提示信息
    
    Args:
        state: 路由状态
        
    Returns:
        RouterState: 更新后的状态
    """
    messages = state.get("messages", [])
    current_intent = state.get("current_intent", "unclear")
    
    intent_messages = {
        "blood_pressure": "抱歉，血压记录智能体功能正在开发中，敬请期待。",
        "appointment": "抱歉，复诊管理智能体功能正在开发中，敬请期待。",
        "doctor_assistant": "抱歉，医生助手智能体功能正在开发中，敬请期待。"
    }
    
    placeholder_message = intent_messages.get(current_intent, "抱歉，该功能正在开发中。")
    
    from langchain_core.messages import AIMessage
    
    updated_state = state.copy()
    updated_messages = list(messages)
    updated_messages.append(AIMessage(content=placeholder_message))
    updated_state["messages"] = updated_messages
    
    logger.info(f"占位智能体节点执行: {current_intent}")
    
    return updated_state


def create_router_graph(checkpointer: AsyncPostgresSaver):
    """
    创建路由图
    
    Args:
        checkpointer: PostgreSQL checkpointer实例，用于保存对话状态
        
    Returns:
        CompiledGraph: 编译后的路由图
    """
    # 创建StateGraph
    router_graph = StateGraph(RouterState)
    
    # 添加节点
    router_graph.add_node("router", router_node)  # 路由节点（每次调用都经过）
    router_graph.add_node("clarify_intent", clarify_intent_node)  # 意图澄清节点
    
    # 注意：专门智能体节点（blood_pressure_agent、appointment_agent、doctor_assistant_agent）
    # 将在后续里程碑中实现，这里先添加占位节点
    router_graph.add_node("blood_pressure_agent", placeholder_agent_node)
    router_graph.add_node("appointment_agent", placeholder_agent_node)
    router_graph.add_node("doctor_assistant_agent", placeholder_agent_node)
    
    # 设置入口点：每次调用都从router节点开始
    router_graph.set_entry_point("router")
    
    # 添加条件边：根据意图路由到对应智能体
    router_graph.add_conditional_edges(
        "router",
        route_decision,
        {
            "blood_pressure": "blood_pressure_agent",
            "appointment": "appointment_agent",
            "doctor_assistant": "doctor_assistant_agent",
            "unclear": "clarify_intent"
        }
    )
    
    # 添加回边：专门智能体执行完后，返回到router节点
    router_graph.add_edge("blood_pressure_agent", "router")
    router_graph.add_edge("appointment_agent", "router")
    router_graph.add_edge("doctor_assistant_agent", "router")
    router_graph.add_edge("clarify_intent", "router")
    
    # 编译图
    compiled_graph = router_graph.compile(checkpointer=checkpointer)
    
    logger.info("路由图创建成功")
    
    return compiled_graph


async def create_router_agent(checkpointer: AsyncPostgresSaver):
    """
    创建路由智能体实例
    
    Args:
        checkpointer: PostgreSQL checkpointer实例
        
    Returns:
        CompiledGraph: 编译后的路由图Agent
    """
    graph = create_router_graph(checkpointer)
    return graph

