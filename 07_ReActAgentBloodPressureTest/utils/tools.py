import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from typing import Callable, Optional
from langchain_core.tools import BaseTool, tool as create_tool
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt.interrupt import HumanInterruptConfig, HumanInterrupt
from langgraph.types import interrupt
from langchain_core.tools import tool
from datetime import datetime
import uuid
import json
from .config import Config
from langgraph.store.postgres import AsyncPostgresStore


# Author:@南哥AGI研习社 (B站 or YouTube 搜索"南哥AGI研习社")


# 设置日志基本配置，级别为DEBUG或INFO
logger = logging.getLogger(__name__)
# 设置日志器级别为DEBUG
logger.setLevel(logging.DEBUG)
logger.handlers = []  # 清空默认处理器
# 使用ConcurrentRotatingFileHandler
handler = ConcurrentRotatingFileHandler(
    # 日志文件
    Config.LOG_FILE,
    # 日志文件最大允许大小为5MB，达到上限后触发轮转
    maxBytes=Config.MAX_BYTES,
    # 在轮转时，最多保留3个历史日志文件
    backupCount=Config.BACKUP_COUNT
)
# 设置处理器级别为DEBUG
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
logger.addHandler(handler)


# 验证血压数据
def validate_blood_pressure(systolic: int, diastolic: int) -> tuple[bool, str]:
    """
    验证血压数据
    
    Args:
        systolic: 收缩压
        diastolic: 舒张压
    
    Returns:
        (is_valid, message): 验证结果和消息
    """
    # 范围检查
    if not (90 <= systolic <= 250):
        return False, f"收缩压 {systolic} mmHg 超出合理范围（90-250）。请确认数据是否正确。"
    
    if not (60 <= diastolic <= 150):
        return False, f"舒张压 {diastolic} mmHg 超出合理范围（60-150）。请确认数据是否正确。"
    
    # 逻辑检查
    if systolic <= diastolic:
        return False, f"收缩压 {systolic} 必须大于舒张压 {diastolic}。请确认数据是否正确。"
    
    # 健康提示
    warnings = []
    if systolic > 140:
        warnings.append("收缩压偏高，建议关注")
    if diastolic > 90:
        warnings.append("舒张压偏高，建议关注")
    if systolic < 90:
        warnings.append("收缩压偏低，建议关注")
    if diastolic < 60:
        warnings.append("舒张压偏低，建议关注")
    
    warning_msg = "。".join(warnings) if warnings else ""
    
    return True, warning_msg


# 为工具添加人工审查（human-in-the-loop）功能
async def add_human_in_the_loop(
        tool: Callable | BaseTool,
        *,
        interrupt_config: HumanInterruptConfig = None,
) -> BaseTool:
    """
    为工具添加人工审查（human-in-the-loop）

    Args:
        tool: 可调用对象或 BaseTool 对象
        interrupt_config: 可选的人工中断配置

    Returns:
        BaseTool: 一个带有人工审查功能的 BaseTool 对象
    """
    # 检查传入的工具是否为 BaseTool 的实例
    if not isinstance(tool, BaseTool):
        # 如果不是 BaseTool，则将可调用对象转换为 BaseTool 对象
        tool = create_tool(tool)

    # 使用 create_tool 装饰器定义一个新的工具函数，继承原工具的名称、描述和参数模式
    @create_tool(
        tool.name,
        description=tool.description,
        args_schema=tool.args_schema
    )
    # 定义内部函数，用于处理带有中断逻辑的工具调用
    async def call_tool_with_interrupt(config: RunnableConfig, **tool_input):
        # 创建一个人为中断请求，包含工具名称、输入参数和配置
        request: HumanInterrupt = {
            "action_request": {
                "action": tool.name,
                "args": tool_input
            },
            "config": interrupt_config,
            "description": f"准备调用 {tool.name} 工具：\n- 参数为: {tool_input}\n\n是否允许继续？\n输入 'yes' 接受工具调用\n输入 'no' 拒绝工具调用\n输入 'edit' 修改工具参数后调用工具\n输入 'response' 不调用工具直接反馈信息",
        }
        # 调用 interrupt 函数，获取人工审查的响应（取第一个响应）
        response = interrupt(request)
        logger.info(f"response: {response}")

        # 检查响应类型是否为"接受"（accept）
        if response["type"] == "accept":
            logger.info("工具调用已批准，执行中...")
            logger.info(f"调用工具: {tool.name}, 参数: {tool_input}")
            try:
                # 如果接受，直接调用原始工具并传入输入参数
                tool_response = await tool.ainvoke(input=tool_input)
                logger.info(tool_response)
            except Exception as e:
                logger.error(f"工具调用失败: {e}")
                tool_response = f"工具调用失败: {str(e)}"

        # 检查响应类型是否为"编辑"（edit）
        elif response["type"] == "edit":
            # 如果是编辑，更新工具输入参数为响应中提供的参数
            tool_input = response["args"]["args"]
            try:
                # 使用更新后的参数调用原始工具
                tool_response = await tool.ainvoke(input=tool_input)
                logger.info(tool_response)
            except Exception as e:
                logger.error(f"工具调用失败: {e}")
                tool_response = f"工具调用失败: {str(e)}"

        # 检查响应类型是否为"拒绝"（reject）
        elif response["type"] == "reject":
            logger.info("工具调用被拒绝，等待用户输入...")
            # 直接将用户反馈作为工具的响应
            tool_response = '该工具被拒绝使用，请尝试其他方法或拒绝回答问题。'

        # 检查响应类型是否为"响应"（response）
        elif response["type"] == "response":
            # 如果是响应，直接将用户反馈作为工具的响应
            user_feedback = response["args"]
            tool_response = user_feedback

        else:
            raise ValueError(f"Unsupported interrupt response type: {response['type']}")

        return tool_response

    return call_tool_with_interrupt


# 创建血压记录相关的工具
def create_blood_pressure_tools(store: AsyncPostgresStore, user_id: str):
    """
    创建血压记录相关的工具
    
    Args:
        store: PostgreSQL Store实例
        user_id: 用户ID
    
    Returns:
        List[BaseTool]: 工具列表
    """
    
    @tool("record_blood_pressure", description="记录用户的血压数据到长期记忆")
    async def record_blood_pressure(
        systolic: int,
        diastolic: int,
        timestamp: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        记录用户的血压数据
        
        Args:
            systolic: 收缩压（mmHg），范围90-250
            diastolic: 舒张压（mmHg），范围60-150
            timestamp: 测量时间（ISO格式），可选，默认当前时间
            notes: 备注信息，可选
        
        Returns:
            str: 保存结果消息
        """
        try:
            # 数据验证
            is_valid, validation_msg = validate_blood_pressure(systolic, diastolic)
            if not is_valid:
                return validation_msg
            
            # 时间处理
            if timestamp is None:
                timestamp = datetime.now().isoformat()
            
            # 构造血压记录数据
            record_data = {
                "systolic": systolic,
                "diastolic": diastolic,
                "timestamp": timestamp,
                "notes": notes or "",
                "record_id": str(uuid.uuid4())
            }
            
            # 存储到长期记忆
            namespace = ("blood_pressure", user_id)
            record_id = f"record_{timestamp}_{record_data['record_id']}"
            
            await store.aput(
                namespace=namespace,
                key=record_id,
                value={"data": json.dumps(record_data, ensure_ascii=False)}
            )
            
            logger.info(f"成功为用户 {user_id} 保存血压记录: {record_data}")
            
            # 构造返回消息
            health_msg = ""
            if systolic > 140 or diastolic > 90:
                health_msg = "您的血压值偏高，建议关注健康。"
            elif systolic < 90 or diastolic < 60:
                health_msg = "您的血压值偏低，建议关注健康。"
            else:
                health_msg = "您的血压值在正常范围内，继续保持良好的生活习惯。"
            
            return f"成功保存血压记录：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg，测量时间 {timestamp}。{health_msg}"
            
        except Exception as e:
            logger.error(f"保存血压记录失败: {str(e)}")
            return f"保存血压记录时发生错误: {str(e)}"
    
    @tool("query_blood_pressure", description="查询用户的历史血压记录")
    async def query_blood_pressure(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 10
    ) -> str:
        """
        查询用户的历史血压记录
        
        Args:
            start_date: 开始日期（ISO格式），可选
            end_date: 结束日期（ISO格式），可选
            limit: 返回记录数量限制，默认10
        
        Returns:
            str: 查询结果，格式化的血压记录列表
        """
        try:
            # 从store查询数据
            namespace = ("blood_pressure", user_id)
            memories = await store.asearch(namespace, query="")
            
            if not memories:
                return "未找到历史血压记录。"
            
            # 解析记录
            records = []
            for memory in memories:
                try:
                    if isinstance(memory.value, dict) and "data" in memory.value:
                        record_data = json.loads(memory.value["data"])
                        records.append(record_data)
                except Exception as e:
                    logger.warning(f"解析记录失败: {e}")
                    continue
            
            # 时间过滤
            if start_date or end_date:
                filtered_records = []
                for record in records:
                    record_time = record.get("timestamp", "")
                    if start_date and record_time < start_date:
                        continue
                    if end_date and record_time > end_date:
                        continue
                    filtered_records.append(record)
                records = filtered_records
            
            # 按时间排序（最新的在前）
            records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # 限制数量
            records = records[:limit]
            
            if not records:
                return "未找到符合条件的血压记录。"
            
            # 格式化返回结果
            result_lines = [f"找到 {len(records)} 条血压记录：\n"]
            for idx, record in enumerate(records, 1):
                systolic = record.get("systolic", "未知")
                diastolic = record.get("diastolic", "未知")
                timestamp = record.get("timestamp", "未知")
                notes = record.get("notes", "")
                notes_str = f"，备注：{notes}" if notes else ""
                result_lines.append(f"{idx}. 收缩压：{systolic} mmHg，舒张压：{diastolic} mmHg，测量时间：{timestamp}{notes_str}")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            logger.error(f"查询血压记录失败: {str(e)}")
            return f"查询血压记录时发生错误: {str(e)}"
    
    @tool("update_blood_pressure", description="更新已存在的血压记录")
    async def update_blood_pressure(
        record_id: str,
        systolic: Optional[int] = None,
        diastolic: Optional[int] = None,
        timestamp: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        更新已存在的血压记录
        
        Args:
            record_id: 记录ID（需要包含record_前缀）
            systolic: 新的收缩压，可选
            diastolic: 新的舒张压，可选
            timestamp: 新的测量时间，可选
            notes: 新的备注，可选
        
        Returns:
            str: 更新结果消息
        """
        try:
            # 查找记录
            namespace = ("blood_pressure", user_id)
            memories = await store.asearch(namespace, query="")
            
            target_record = None
            target_key = None
            
            for memory in memories:
                try:
                    if isinstance(memory.value, dict) and "data" in memory.value:
                        record_data = json.loads(memory.value["data"])
                        if record_id in memory.key or record_data.get("record_id") == record_id:
                            target_record = record_data
                            target_key = memory.key
                            break
                except Exception as e:
                    logger.warning(f"解析记录失败: {e}")
                    continue
            
            if not target_record:
                return f"未找到ID为 {record_id} 的血压记录。"
            
            # 更新字段
            if systolic is not None:
                target_record["systolic"] = systolic
            if diastolic is not None:
                target_record["diastolic"] = diastolic
            if timestamp is not None:
                target_record["timestamp"] = timestamp
            if notes is not None:
                target_record["notes"] = notes
            
            # 验证更新后的数据
            is_valid, validation_msg = validate_blood_pressure(
                target_record["systolic"],
                target_record["diastolic"]
            )
            if not is_valid:
                return validation_msg
            
            # 保存更新后的记录
            await store.aput(
                namespace=namespace,
                key=target_key,
                value={"data": json.dumps(target_record, ensure_ascii=False)}
            )
            
            logger.info(f"成功更新用户 {user_id} 的血压记录: {target_record}")
            
            return f"成功更新血压记录：收缩压 {target_record['systolic']} mmHg，舒张压 {target_record['diastolic']} mmHg，测量时间 {target_record['timestamp']}。"
            
        except Exception as e:
            logger.error(f"更新血压记录失败: {str(e)}")
            return f"更新血压记录时发生错误: {str(e)}"
    
    return [record_blood_pressure, query_blood_pressure, update_blood_pressure]


# 获取工具列表 提供给第三方调用
async def get_tools(store: Optional[AsyncPostgresStore] = None, user_id: Optional[str] = None):
    """
    获取工具列表
    
    Args:
        store: PostgreSQL Store实例（可选）
        user_id: 用户ID（可选）
    
    Returns:
        List[BaseTool]: 工具列表
    """
    tools = []
    
    # 如果提供了store和user_id，添加血压记录工具
    if store and user_id:
        bp_tools = create_blood_pressure_tools(store, user_id)
        for tool_instance in bp_tools:
            tools.append(await add_human_in_the_loop(tool_instance))
    
    # 返回工具列表
    return tools

