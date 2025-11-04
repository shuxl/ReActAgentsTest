import os
from typing import Optional
from langchain_mcp_adapters.client import MultiServerMCPClient


# Author:@南哥AGI研习社 (B站 or YouTube 搜索"南哥AGI研习社")


class MCPClientInitializationError(Exception):
    """自定义异常类用于MCP Client初始化错误"""
    pass


def get_mcp_client(
    server_name: str = "amap-amap-sse",
    base_url: str = "https://mcp.amap.com/sse",
    api_key: Optional[str] = None,
    env_key_name: str = "AMAP_MCP_KEY",
    transport: str = "sse"
) -> MultiServerMCPClient:
    """
    初始化并返回 MCP Server 客户端实例
    
    Args:
        server_name (str): MCP Server 名称，默认为 "amap-amap-sse"
        base_url (str): MCP Server 基础 URL，默认为 "https://mcp.amap.com/sse"
        api_key (Optional[str]): API Key，如果为 None 则从环境变量读取
        env_key_name (str): 环境变量名称，默认为 "AMAP_MCP_KEY"
        transport (str): 传输协议，默认为 "sse"
    
    Returns:
        MultiServerMCPClient: MCP Server 客户端实例
    
    Raises:
        MCPClientInitializationError: 当 API Key 未设置或初始化失败时抛出
    """
    # 获取 API Key
    if api_key is None:
        api_key = os.getenv(env_key_name)
    
    # 检查 API Key
    if not api_key or api_key == "":
        error_msg = f"请设置环境变量 {env_key_name}"
        print(f"{env_key_name}:{api_key}")
        raise MCPClientInitializationError(error_msg)
    
    print(f"{env_key_name}:{api_key}")
    
    try:
        # 构建完整的 URL（如果 base_url 不包含 key 参数，则添加）
        if "?" in base_url:
            url = f"{base_url}&key={api_key}"
        else:
            url = f"{base_url}?key={api_key}"
        
        # 创建 MCP Client 配置
        client_config = {
            server_name: {
                "url": url,
                "transport": transport,
            }
        }
        
        # 初始化 MCP Client
        client = MultiServerMCPClient(client_config)
        return client
    except Exception as e:
        error_msg = f"初始化 MCP Client 失败: {str(e)}"
        raise MCPClientInitializationError(error_msg) from e


def get_amap_mcp_client(
    api_key: Optional[str] = None,
    env_key_name: str = "AMAP_MCP_KEY"
) -> MultiServerMCPClient:
    """
    便捷函数：获取高德地图 MCP Server 客户端
    
    Args:
        api_key (Optional[str]): API Key，如果为 None 则从环境变量读取
        env_key_name (str): 环境变量名称，默认为 "AMAP_MCP_KEY"
    
    Returns:
        MultiServerMCPClient: 高德地图 MCP Server 客户端实例
    """
    return get_mcp_client(
        server_name="amap-amap-sse",
        base_url="https://mcp.amap.com/sse",
        api_key=api_key,
        env_key_name=env_key_name,
        transport="sse"
    )

