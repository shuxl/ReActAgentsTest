import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from pydantic import BaseModel, Field
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid
from langgraph.types import interrupt, Command
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import uvicorn
from contextlib import asynccontextmanager
import redis.asyncio as redis
import json
from datetime import timedelta
from psycopg_pool import AsyncConnectionPool
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.config import Config
from utils.llms import get_llm_by_config
from utils.tools import get_tools



# Author:@南哥AGI研习社 (B站 or YouTube 搜索“南哥AGI研习社”)


# 设置日志基本配置，级别为DEBUG或INFO
logger = logging.getLogger(__name__)
# 设置日志器级别为DEBUG
logger.setLevel(logging.DEBUG)
# logger.setLevel(logging.INFO)
logger.handlers = []  # 清空默认处理器
# 使用ConcurrentRotatingFileHandler
handler = ConcurrentRotatingFileHandler(
    # 日志文件
    Config.LOG_FILE,
    # 日志文件最大允许大小为5MB，达到上限后触发轮转
    maxBytes = Config.MAX_BYTES,
    # 在轮转时，最多保留3个历史日志文件
    backupCount = Config.BACKUP_COUNT
)
# 设置处理器级别为DEBUG
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logger.addHandler(handler)


# 定义数据模型 客户端发起的智能体请求
class AgentRequest(BaseModel):
    # 用户唯一标识
    user_id: str
    # 用户的问题
    query: str
    # 系统提示词
    system_message: Optional[str] = "你会使用工具来帮助用户。如果工具使用被拒绝，请提示用户。"

# 定义数据模型 智能体给予的响应
class AgentResponse(BaseModel):
    # 会话唯一标识
    session_id: str
    # 三个状态：interrupted, completed, error
    status: str
    # 时间戳
    timestamp: float = Field(default_factory=lambda: time.time())
    # error时的提示消息
    message: Optional[str] = None
    # completed时的结果消息
    result: Optional[Dict[str, Any]] = None
    # interrupted时的中断消息
    interrupt_data: Optional[Dict[str, Any]] = None

# 定义数据模型 客户端给予的反馈响应
class InterruptResponse(BaseModel):
    # 用户唯一标识
    user_id: str
    # 会话唯一标识
    session_id: str
    # 响应类型：accept(允许调用), edit(调整工具参数，此时args中携带修改后的调用参数), response(直接反馈信息，此时args中携带修改后的调用参数)，reject(不允许调用)
    response_type: str
    # 如果是edit, response类型，可能需要额外的参数
    args: Optional[Dict[str, Any]] = None

# 定义数据模型 系统信息响应
class SystemInfoResponse(BaseModel):
    # 当前系统内会话总数
    sessions_count: int
    # 当前活跃的用户
    active_users: List[str]

# 定义数据模型 会话状态信息响应
class SessionStatusResponse(BaseModel):
    # 用户唯一标识符
    user_id: str
    # 会话唯一标识符
    session_id: Optional[str] = None
    # 状态：not_found, idle, running, interrupted, completed, error
    status: str
    # error时的提示消息
    message: Optional[str] = None
    # 上次查询
    last_query: Optional[str] = None
    # 上次更新时间
    last_updated: Optional[float] = None
    # 上次响应
    last_response: Optional[AgentResponse] = None


# 实现redis相关方法
class RedisSessionManager:
    # 初始化异步 Redis 连接和会话配置
    def __init__(self, redis_host, redis_port, redis_db, session_timeout):
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.session_timeout = session_timeout  # 会话过期时间（秒）

    # 关闭 Redis 连接
    async def close(self):
        await self.redis_client.close()

    # 创建新会话，匹配指定数据结构
    # 会话存储 - 保存每个用户的智能体实例和状态
    # 暂时只支持一个用户一个会话，不能一个用户多个会话
    # 结构: {user_id: {
    #   "session_id": session_id,   # 会话ID
    #   "status": "idle|running|interrupted|completed|error",     # 会话状态
    #   "last_response": AgentResponse,     # 上次响应
    #   "last_query": str,                  # 上次查询
    #   "last_updated": timestamp           # 上次更新时间
    # }}
    async def create_session(self, user_id: str, session_id: Optional[str] = None, status: str = "active",
                            last_query: Optional[str] = None, last_response: Optional['AgentResponse'] = None,
                            last_updated: Optional[float] = None) -> str:
        if session_id is None:
            session_id = str(uuid.uuid4())
        if last_updated is None:
            last_updated = str(timedelta(seconds=0))
        session_data = {
            user_id: {
                "session_id": session_id,
                "status": status,
                "last_response": last_response.model_dump() if isinstance(last_response, BaseModel) else last_response,
                "last_query": last_query,
                "last_updated": last_updated
            }
        }
        await self.redis_client.set(
            f"session:{user_id}",
            json.dumps(session_data, default=lambda o: o.__dict__ if not hasattr(o, 'model_dump') else o.model_dump()),
            ex=self.session_timeout
        )
        return session_id

    # 获取会话数据
    async def get_session(self, user_id: str) -> Optional[dict]:
        session_data = await self.redis_client.get(f"session:{user_id}")
        if not session_data:
            return None
        session = json.loads(session_data).get(user_id)
        if session and "last_response" in session:
            if session["last_response"] is not None:
                try:
                    session["last_response"] = AgentResponse(**session["last_response"])
                except Exception as e:
                    logger.error(f"转换 last_response 失败: {e}")
                    session["last_response"] = None
        return session

    # 更新会话数据
    async def update_session(self, user_id: str, status: Optional[str] = None, last_query: Optional[str] = None,
                             last_response: Optional['AgentResponse'] = None, last_updated: Optional[float] = None) -> bool:
        if await self.redis_client.exists(f"session:{user_id}"):
            current_data = await self.get_session(user_id)
            if not current_data:
                return False
            # 更新提供的字段
            if status is not None:
                current_data["status"] = status
            if last_response is not None:
                if isinstance(last_response, BaseModel):
                    current_data["last_response"] = last_response.model_dump()
                else:
                    current_data["last_response"] = last_response
            if last_query is not None:
                current_data["last_query"] = last_query
            if last_updated is not None:
                current_data["last_updated"] = last_updated
            # 保持数据结构
            session_data = {user_id: current_data}
            # 重新存储并刷新过期时间
            await self.redis_client.set(
                f"session:{user_id}",
                json.dumps(session_data, default=lambda o: o.__dict__ if not hasattr(o, 'model_dump') else o.model_dump()),
                ex=self.session_timeout
            )
            return True
        return False

    # 删除会话
    async def delete_session(self, user_id: str) -> bool:
        return (await self.redis_client.delete(f"session:{user_id}")) > 0

    # 获取所有会话数量
    async def get_session_count(self) -> int:
        count = 0
        async for _ in self.redis_client.scan_iter("session:*"):
            count += 1
        return count

    # 获取所有 user_id
    async def get_all_user_ids(self) -> List[str]:
        user_ids = []
        async for key in self.redis_client.scan_iter("session:*"):
            user_id = key.split(":", 1)[1]
            user_ids.append(user_id)
        return user_ids

    # 检查 user_id 是否在 Redis 中
    async def user_id_exists(self, user_id: str) -> bool:
        return (await self.redis_client.exists(f"session:{user_id}")) > 0

# 解析state消息列表进行格式化展示
async def parse_messages(messages: List[Any]) -> None:
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

# 处理智能体返回结果 可能是中断，也可能是最终结果
async def process_agent_result(
        session_id: str,
        result: Dict[str, Any],
        user_id: Optional[str] = None
) -> AgentResponse:
    """
    处理智能体执行结果，统一处理中断和结果

    Args:
        session_id: 会话ID
        result: 智能体执行结果
        user_id: 用户ID，如果提供，将更新会话状态

    Returns:
        AgentResponse: 标准化的响应对象
    """
    response = None

    try:
        # 检查是否有中断
        if "__interrupt__" in result:
            interrupt_data = result["__interrupt__"][0].value
            # 确保中断数据有类型信息
            if "interrupt_type" not in interrupt_data:
                interrupt_data["interrupt_type"] = "unknown"
            # 返回中断信息
            response = AgentResponse(
                session_id=session_id,
                status="interrupted",
                interrupt_data=interrupt_data
            )
            logger.info(f"当前触发工具调用中断:{response}")
        # 如果没有中断，返回最终结果
        else:
            response = AgentResponse(
                session_id=session_id,
                status="completed",
                result=result
            )
            logger.info(f"最终智能体回复结果:{response}")

    except Exception as e:
        response = AgentResponse(
            session_id=session_id,
            status="error",
            message=f"处理智能体结果时出错: {str(e)}"
        )
        logger.error(f"处理智能体结果时出错:{response}")

    # 如果提供了用户ID，更新会话状态
    exists = await app.state.session_manager.user_id_exists(user_id)
    if user_id and exists:
        status = response.status
        last_query = None
        last_response = response
        last_updated = time.time()
        await app.state.session_manager.update_session(user_id, status, last_query, last_response, last_updated)

    return response


# 生命周期函数 app应用初始化函数
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # 实例化异步Redis会话管理器 并存储为单实例
        app.state.session_manager = RedisSessionManager(
            Config.REDIS_HOST,
            Config.REDIS_PORT,
            Config.REDIS_DB,
            Config.SESSION_TIMEOUT
        )
        logger.info("Redis初始化成功")

        # 创建Chat模型
        # 使用外层utils的llms.py中的get_llm_by_config方法（通过sys.path.append导入）
        # 该方法会根据Config中的LLM_TYPE自动选择对应的LLM初始化方法
        llm_chat = get_llm_by_config()
        logger.info("Chat模型初始化成功")

        # 创建数据库连接池 动态连接池根据负载调整连接池大小
        async with AsyncConnectionPool(
                conninfo=Config.DB_URI,
                min_size=Config.MIN_SIZE,
                max_size=Config.MAX_SIZE,
                kwargs={"autocommit": True, "prepare_threshold": 0}
        ) as pool:
            # 短期记忆 初始化checkpointer，并初始化表结构
            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()
            logger.info("Checkpointer初始化成功")

            # 获取工具列表
            tools = await get_tools()

            # 创建ReAct Agent 并存储为单实例
            app.state.agent = create_react_agent(
                model=llm_chat,
                tools=tools,
                checkpointer=checkpointer
            )
            logger.info("Agent初始化成功")
            logger.info("服务完成初始化并启动服务")
            yield

    except Exception as e:
        logger.error(f"初始化失败: {str(e)}")
        raise RuntimeError(f"初始化检查点保存器失败: {str(e)}")

    # 清理资源
    finally:
        # 关闭Redis连接
        await app.state.session_manager.close()
        # 关闭PostgreSQL连接池
        await pool.close()
        logger.info("关闭服务并完成资源清理")

# 实例化app 并使用生命周期上下文管理器进行app初始化
app = FastAPI(
    title="Agent智能体后端API接口服务",
    description="基于LangGraph提供AI Agent服务",
    lifespan=lifespan
)

# API接口:创建智能体并调用，直接返回结果或中断数据
@app.post("/agent/invoke", response_model=AgentResponse)
async def invoke_agent(request: AgentRequest):
    logger.info(f"invoke_agent接口，接受到前端用户请求:{request}")
    # 获取用户请求中的user_id
    user_id = request.user_id

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)
    # 若用户不存在 则只在创建新会话时生成新的会话ID
    if not exists:
        session_id = str(uuid.uuid4())
        status = "idle"
        last_query = None
        last_response = None
        last_updated = time.time()
        # 创建会话并存储到redis中
        await app.state.session_manager.create_session(user_id, session_id, status, last_query, last_response, last_updated)
    # 若用户存在 则使用现有会话的ID
    else:
        session = await app.state.session_manager.get_session(user_id)
        session_id = session.get("session_id")

    # 新请求统一更新会话信息
    status = "running"
    last_query = request.query
    last_response = None
    last_updated = time.time()
    await app.state.session_manager.update_session(user_id, status, last_query, last_response, last_updated)

    # 构造智能体输入消息体
    messages = [
        {"role": "system", "content": request.system_message},
        {"role": "user", "content": request.query}
    ]

    try:
        # 先调用智能体
        result = await app.state.agent.ainvoke({"messages": messages}, config={"configurable": {"thread_id": session_id}})
        # 将返回的messages进行格式化输出 方便查看调试
        await parse_messages(result['messages'])

        # 再处理结果并更新会话状态
        return await process_agent_result(session_id, result, user_id)

    except Exception as e:
        # 异常处理
        error_response = AgentResponse(
            session_id=session_id,
            status="error",
            message=f"处理请求时出错: {str(e)}"
        )
        logger.error(f"处理请求时出错: {error_response}")

        # 更新会话状态
        status = "error"
        last_query = None
        last_response = error_response
        last_updated = time.time()
        await app.state.session_manager.update_session(user_id, status, last_query, last_response, last_updated)

        return error_response

# API接口:恢复被中断的智能体执行，等待执行完成或再次中断
@app.post("/agent/resume", response_model=AgentResponse)
async def resume_agent(response: InterruptResponse):
    logger.info(f"resume_agent接口，接受到前端用户请求:{response}")
    # 获取用户请求中的user_id和session_id
    user_id = response.user_id
    client_session_id = response.session_id

    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)
    # 若用户不存在 则抛出异常
    if not exists:
        logger.error(f"status_code=404,用户会话 {user_id} 不存在")
        raise HTTPException(status_code=404, detail=f"用户会话 {user_id} 不存在")

    # 然后判断会话ID是否匹配 若不匹配则抛出异常
    session = await app.state.session_manager.get_session(user_id)
    server_session_id = session.get("session_id")
    if server_session_id != client_session_id:
        logger.error(f"status_code=400,会话ID不匹配，可能是过期的请求")
        raise HTTPException(status_code=400, detail="会话ID不匹配，可能是过期的请求")

    # 检查会话状态是否为中断 若不是中断则抛出异常
    session = await app.state.session_manager.get_session(user_id)
    status = session.get("status")
    if status != "interrupted":
        logger.error(f"status_code=400,会话当前状态为 {status}，无法恢复非中断状态的会话")
        raise HTTPException(status_code=400, detail=f"会话当前状态为 {status}，无法恢复非中断状态的会话")

    # 更新会话状态
    status = "running"
    last_query = None
    last_response = None
    last_updated = time.time()
    await app.state.session_manager.update_session(user_id, status, last_query, last_response, last_updated)

    # 构造响应数据
    command_data = {
        "type": response.response_type
    }
    # 如果提供了参数，添加到响应数据中
    if response.args:
        command_data["args"] = response.args

    try:
        # 先恢复智能体执行
        result = await app.state.agent.ainvoke(Command(resume=command_data), config={"configurable": {"thread_id": server_session_id}})
        # 将返回的messages进行格式化输出 方便查看调试
        await parse_messages(result['messages'])
        # 再处理结果并更新会话状态
        return await process_agent_result(server_session_id, result, user_id)

    except Exception as e:
        # 异常处理
        error_response = AgentResponse(
            session_id=server_session_id,
            status="error",
            message=f"恢复执行时出错: {str(e)}"
        )
        logger.error(f"处理请求时出错: {error_response}")

        # 更新会话状态
        status = "error"
        last_query = None
        last_response = error_response
        last_updated = time.time()
        await app.state.session_manager.update_session(user_id, status, last_query, last_response, last_updated)

        return error_response

# API接口:获取当前用户的状态
@app.get("/agent/status/{user_id}", response_model=SessionStatusResponse)
async def get_agent_status(user_id: str):
    logger.info(f"get_agent_status接口，接受到前端用户请求:{user_id}")
    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)
    # 若用户不存在 构造SessionStatusResponse对象
    if not exists:
        logger.error(f"用户 {user_id} 的会话不存在")
        return SessionStatusResponse(
            user_id=user_id,
            status="not_found",
            message=f"用户 {user_id} 的会话不存在"
        )

    # 若用户存在 构造SessionStatusResponse对象
    session = await app.state.session_manager.get_session(user_id)
    response = SessionStatusResponse(
        user_id=user_id,
        session_id=session.get("session_id"),
        status=session.get("status"),
        last_query=session.get("last_query"),
        last_updated=session.get("last_updated"),
        last_response=session.get("last_response")
    )
    logger.info(f"返回当前用户的状态:{response}")
    return response

# API接口:获取系统状态信息
@app.get("/system/info", response_model=SystemInfoResponse)
async def get_system_info():
    logger.info(f"get_system_info接口，接受到前端用户请求")
    # 构造SystemInfoResponse对象
    response = SystemInfoResponse(
        # 当前系统内会话总数
        sessions_count=await app.state.session_manager.get_session_count(),
        # 系统内当前活跃的用户
        active_users=await app.state.session_manager.get_all_user_ids()
    )
    logger.info(f"返回当前系统状态信息:{response}")
    return response

# API接口:删除用户会话
@app.delete("/agent/session/{user_id}")
async def delete_agent_session(user_id: str):
    logger.info(f"delete_agent_session接口，接受到前端用户请求:{user_id}")
    # 判断当前用户会话是否存在
    exists = await app.state.session_manager.user_id_exists(user_id)
    # 如果不存在 则抛出异常
    if not exists:
        logger.error(f"status_code=404,用户 {user_id} 的会话不存在")
        raise HTTPException(status_code=404, detail=f"用户会话 {user_id} 不存在")

    # 如果存在 则删除会话
    await app.state.session_manager.delete_session(user_id)
    response = {
        "status": "success",
        "message": f"用户 {user_id} 的会话已删除"
    }
    logger.info(f"用户会话已经删除:{response}")
    return response



# 启动服务器
if __name__ == "__main__":
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)
