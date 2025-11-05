import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from typing import Optional
from langchain_core.tools import BaseTool, tool
from datetime import datetime
import uuid
import json
import re
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


# 解析和转换日期时间字符串
def parse_datetime(date_str: Optional[str]) -> tuple[str, str]:
    """
    解析日期时间字符串，转换为ISO格式的时间戳和日期
    
    Args:
        date_str: 日期时间字符串（支持多种格式，如"今天早上8点"、"2024-01-15"等）
    
    Returns:
        (timestamp, date): ISO格式的时间戳和日期字符串
    """
    if date_str is None:
        now = datetime.now()
        return now.isoformat(), now.strftime("%Y-%m-%d")
    
    try:
        # 尝试解析标准日期时间格式
        # 首先尝试ISO格式
        if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
            # 标准日期格式 YYYY-MM-DD
            if len(date_str) == 10:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                # 带时间的格式
                dt = datetime.fromisoformat(date_str.replace(' ', 'T'))
            return dt.isoformat(), dt.strftime("%Y-%m-%d")
        
        # 尝试其他常见格式
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.isoformat(), dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        # 如果都解析失败，使用当前时间
        logger.warning(f"日期解析失败: {date_str}，使用当前时间")
        now = datetime.now()
        return now.isoformat(), now.strftime("%Y-%m-%d")
        
    except Exception as e:
        logger.warning(f"日期解析失败: {date_str}, 错误: {e}，使用当前时间")
        # 如果解析失败，使用当前时间
        now = datetime.now()
        return now.isoformat(), now.strftime("%Y-%m-%d")


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
    
    @tool("record_blood_pressure", description="记录用户的血压数据到长期记忆，支持自动转换日期时间格式")
    async def record_blood_pressure(
        systolic: int,
        diastolic: int,
        date_time: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        记录用户的血压数据
        
        Args:
            systolic: 收缩压（mmHg），范围90-250
            diastolic: 舒张压（mmHg），范围60-150
            date_time: 测量日期时间（支持多种格式，如"今天早上8点"、"2024-01-15 08:00"等），可选，默认当前时间
            notes: 备注信息，可选
        
        Returns:
            str: 保存结果消息
        """
        try:
            # 数据验证
            is_valid, validation_msg = validate_blood_pressure(systolic, diastolic)
            if not is_valid:
                return validation_msg
            
            # 解析日期时间
            timestamp, date = parse_datetime(date_time)
            
            # 构造血压记录数据
            record_data = {
                "systolic": systolic,
                "diastolic": diastolic,
                "timestamp": timestamp,
                "date": date,  # 新增日期字段
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
            
            return f"成功保存血压记录：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg，测量日期 {date}，测量时间 {timestamp}。{health_msg}"
            
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
                    record_date = record.get("date") or record.get("timestamp", "").split("T")[0]
                    if start_date and record_date < start_date:
                        continue
                    if end_date and record_date > end_date:
                        continue
                    filtered_records.append(record)
                records = filtered_records
            
            # 按时间排序（最新的在前）
            records.sort(key=lambda x: x.get("timestamp", "") or x.get("date", ""), reverse=True)
            
            # 限制数量
            records = records[:limit]
            
            if not records:
                return "未找到符合条件的血压记录。"
            
            # 格式化返回结果
            result_lines = [f"找到 {len(records)} 条血压记录：\n"]
            for idx, record in enumerate(records, 1):
                systolic = record.get("systolic", "未知")
                diastolic = record.get("diastolic", "未知")
                date = record.get("date", record.get("timestamp", "未知").split("T")[0])
                timestamp = record.get("timestamp", "未知")
                notes = record.get("notes", "")
                notes_str = f"，备注：{notes}" if notes else ""
                result_lines.append(f"{idx}. 收缩压：{systolic} mmHg，舒张压：{diastolic} mmHg，日期：{date}，时间：{timestamp}{notes_str}")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            logger.error(f"查询血压记录失败: {str(e)}")
            return f"查询血压记录时发生错误: {str(e)}"
    
    @tool("update_blood_pressure", description="更新已存在的血压记录")
    async def update_blood_pressure(
        record_id: str,
        systolic: Optional[int] = None,
        diastolic: Optional[int] = None,
        date_time: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        更新已存在的血压记录
        
        Args:
            record_id: 记录ID（需要包含record_前缀）
            systolic: 新的收缩压，可选
            diastolic: 新的舒张压，可选
            date_time: 新的测量日期时间，可选
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
            if date_time is not None:
                timestamp, date = parse_datetime(date_time)
                target_record["timestamp"] = timestamp
                target_record["date"] = date
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
            
            return f"成功更新血压记录：收缩压 {target_record['systolic']} mmHg，舒张压 {target_record['diastolic']} mmHg，日期 {target_record.get('date', '未知')}，时间 {target_record['timestamp']}。"
            
        except Exception as e:
            logger.error(f"更新血压记录失败: {str(e)}")
            return f"更新血压记录时发生错误: {str(e)}"
    
    @tool("info", description="查询用户的基础信息，包括setting信息和血压信息统计")
    async def info() -> str:
        """
        查询用户的基础信息
        
        Returns:
            str: 格式化的用户信息，包括setting信息和血压信息统计
        """
        try:
            result_lines = []
            
            # 1. 查询setting信息（从memories命名空间）
            namespace_settings = ("memories", user_id)
            settings_memories = await store.asearch(namespace_settings, query="")
            
            if settings_memories:
                result_lines.append("=== 用户设置信息 ===")
                for memory in settings_memories:
                    try:
                        if isinstance(memory.value, dict) and "data" in memory.value:
                            setting_data = memory.value["data"]
                            result_lines.append(f"- {setting_data}")
                    except Exception as e:
                        logger.warning(f"解析设置信息失败: {e}")
                        continue
            else:
                result_lines.append("=== 用户设置信息 ===")
                result_lines.append("暂无设置信息")
            
            result_lines.append("")
            
            # 2. 查询血压信息统计（从blood_pressure命名空间）
            namespace_bp = ("blood_pressure", user_id)
            bp_memories = await store.asearch(namespace_bp, query="")
            
            result_lines.append("=== 血压信息统计 ===")
            
            if not bp_memories:
                result_lines.append("暂无血压记录")
            else:
                # 解析所有血压记录
                records = []
                for memory in bp_memories:
                    try:
                        if isinstance(memory.value, dict) and "data" in memory.value:
                            record_data = json.loads(memory.value["data"])
                            records.append(record_data)
                    except Exception as e:
                        logger.warning(f"解析血压记录失败: {e}")
                        continue
                
                if records:
                    # 统计信息
                    total_records = len(records)
                    
                    # 计算平均值
                    systolic_values = [r.get("systolic") for r in records if r.get("systolic")]
                    diastolic_values = [r.get("diastolic") for r in records if r.get("diastolic")]
                    
                    avg_systolic = sum(systolic_values) / len(systolic_values) if systolic_values else 0
                    avg_diastolic = sum(diastolic_values) / len(diastolic_values) if diastolic_values else 0
                    
                    # 获取最新记录
                    records.sort(key=lambda x: x.get("timestamp", "") or x.get("date", ""), reverse=True)
                    latest_record = records[0] if records else None
                    
                    result_lines.append(f"总记录数：{total_records} 条")
                    result_lines.append(f"平均收缩压：{avg_systolic:.1f} mmHg")
                    result_lines.append(f"平均舒张压：{avg_diastolic:.1f} mmHg")
                    
                    if latest_record:
                        latest_date = latest_record.get("date", latest_record.get("timestamp", "未知").split("T")[0])
                        result_lines.append(f"\n最新记录：")
                        result_lines.append(f"  日期：{latest_date}")
                        result_lines.append(f"  收缩压：{latest_record.get('systolic', '未知')} mmHg")
                        result_lines.append(f"  舒张压：{latest_record.get('diastolic', '未知')} mmHg")
                        if latest_record.get('notes'):
                            result_lines.append(f"  备注：{latest_record.get('notes')}")
                else:
                    result_lines.append("暂无有效的血压记录")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            logger.error(f"查询用户信息失败: {str(e)}")
            return f"查询用户信息时发生错误: {str(e)}"
    
    return [record_blood_pressure, query_blood_pressure, update_blood_pressure, info]


# 获取工具列表 提供给第三方调用
async def get_tools(store: Optional[AsyncPostgresStore] = None, user_id: Optional[str] = None):
    """
    获取工具列表（无人工审查版本）
    
    Args:
        store: PostgreSQL Store实例（可选）
        user_id: 用户ID（可选）
    
    Returns:
        List[BaseTool]: 工具列表
    """
    tools = []
    
    # 如果提供了store和user_id，添加血压记录工具（直接添加，不添加人工审查）
    if store and user_id:
        bp_tools = create_blood_pressure_tools(store, user_id)
        tools.extend(bp_tools)
    
    # 返回工具列表
    return tools

