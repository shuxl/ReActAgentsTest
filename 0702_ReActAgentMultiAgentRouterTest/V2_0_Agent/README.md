# V2.0 多智能体路由系统 - 里程碑1和里程碑2交付物

## 项目结构

```
V2_0_Agent/
├── utils/
│   ├── __init__.py
│   ├── config.py              # 配置管理模块
│   ├── llms.py                # LLM初始化模块
│   ├── database.py            # 数据库连接池管理模块
│   ├── redis_manager.py       # Redis连接管理模块
│   ├── router_state.py        # 路由状态数据结构
│   ├── router.py              # 路由节点实现
│   ├── router_graph.py        # 路由图创建
│   ├── agents/                # 专门智能体模块（待实现）
│   │   └── __init__.py
│   └── tools/                 # 工具模块
│       ├── __init__.py
│       └── router_tools.py    # 路由工具实现
├── logfile/                   # 日志文件目录
├── test_db_connection.py      # 数据库连接测试脚本
├── test_redis_connection.py  # Redis连接测试脚本
├── test_router.py             # 路由功能单元测试
└── requirements.txt           # 依赖包列表
```

## 环境配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件或设置以下环境变量：

```bash
# 数据库配置
export DB_URI="postgresql://postgres:password@localhost:5432/dbname?sslmode=disable"

# Redis配置
export REDIS_HOST="localhost"
export REDIS_PORT="6379"
export REDIS_DB="0"

# LLM配置
export DEEPSEEK_API_KEY="your-api-key-here"
export LLM_TYPE="deepseek-chat"
export LLM_TEMPERATURE="0"
```

## 测试

### 测试数据库连接

```bash
python test_db_connection.py
```

### 测试Redis连接

```bash
python test_redis_connection.py
```

### 测试路由功能

```bash
python test_router.py
```

## 模块说明

### config.py
统一配置管理模块，集中管理所有配置常量，支持环境变量覆盖。

### database.py
PostgreSQL数据库连接池管理模块，使用 `psycopg_pool` 的 `AsyncConnectionPool`，与LangGraph兼容。

### redis_manager.py
Redis连接管理模块，提供基本的Redis操作接口。

### llms.py
LLM初始化模块，支持根据配置自动选择合适的LLM模型。

### router_state.py
路由状态数据结构定义，包含RouterState和IntentResult。

### router.py
路由节点实现，包含router_node、clarify_intent_node和route_decision函数。

### router_graph.py
路由图创建模块，使用LangGraph StateGraph构建路由图结构。

### router_tools.py
路由工具实现，包含identify_intent和clarify_intent工具。

## 里程碑1完成情况

- ✅ 项目结构完整，符合设计文档要求
- ✅ 配置文件（config.py）已实现
- ✅ 数据库连接池管理模块已实现
- ✅ Redis连接管理模块已实现
- ✅ LLM初始化模块已实现
- ✅ 数据库连接测试脚本已创建
- ✅ Redis连接测试脚本已创建

## 里程碑2完成情况

- ✅ RouterState数据结构正确定义
- ✅ IntentResult模型正确定义
- ✅ identify_intent工具能够识别4种意图类型（blood_pressure、appointment、doctor_assistant、unclear）
- ✅ clarify_intent工具能够生成澄清问题
- ✅ router_node能够正确识别意图并更新状态
- ✅ route_decision能够根据意图正确路由
- ✅ StateGraph路由图结构已创建（包含占位节点）
- ✅ 路由功能单元测试已创建

