# 0701_ReActAgentBloodPressureNoHILTest - 血压记录智能体（无人工审查版本）

## 项目简介

本项目是07版本血压记录智能体的改进版本，主要变化包括：
1. **移除人工审查功能**：工具调用自动执行，无需人工审批
2. **新增info命令**：可以查询用户的基础信息（setting信息和血压统计信息）
3. **日期字段增强**：血压记录支持独立的日期字段，并自动转换日期时间格式

## 与07版本的主要区别

### 1. 移除人工审查功能

- **07版本**：工具调用前需要人工审批（accept/edit/reject/response）
- **0701版本**：工具调用自动执行，无需人工审批
- **影响**：
  - 移除了 `/agent/resume` API接口
  - 移除了 `interrupted` 状态
  - 前端不再需要处理中断响应

### 2. 新增info命令工具

新增 `info` 工具，可以查询：
- **用户设置信息**：从 `memories` 命名空间读取用户的长期记忆设置
- **血压统计信息**：
  - 总记录数
  - 平均收缩压和舒张压
  - 最新血压记录详情

### 3. 日期字段增强

- **新增字段**：血压记录中新增 `date` 字段（YYYY-MM-DD格式）
- **日期转换**：支持多种日期时间格式的自动转换
  - 标准格式：`2024-01-15`、`2024-01-15 08:00:00`
  - 智能解析：支持常见的中文日期时间表达（由LLM理解后转换为标准格式）
- **存储结构**：
  ```json
  {
      "systolic": 120,
      "diastolic": 80,
      "timestamp": "2024-01-15T08:00:00",
      "date": "2024-01-15",  // 新增字段
      "notes": "",
      "record_id": "uuid"
  }
  ```

## 功能特性

### 核心功能

1. **多轮对话引导**
   - 友好地引导用户填写血压数据
   - 逐步收集收缩压、舒张压、测量日期时间和备注信息
   - 支持用户一次性提供所有信息或分多次提供

2. **数据验证**
   - 验证血压数值是否在合理范围内（收缩压：90-250 mmHg，舒张压：60-150 mmHg）
   - 验证收缩压必须大于舒张压
   - 提供健康建议（正常范围、偏高/偏低提醒）

3. **日期时间处理**
   - 自动解析和转换用户提供的日期时间格式
   - 支持标准ISO格式和常见的中文表达
   - 同时保存时间戳（timestamp）和日期（date）两个字段

4. **数据持久化**
   - 使用PostgreSQL Store存储血压记录到长期记忆
   - 支持查询历史血压记录
   - 支持更新已保存的血压记录

5. **信息查询**
   - 使用 `info` 工具查询用户设置和血压统计信息

### 工具功能

- **record_blood_pressure**：记录血压数据到长期记忆（自动处理日期时间转换）
- **query_blood_pressure**：查询历史血压记录
- **update_blood_pressure**：更新已存在的血压记录
- **info**：查询用户的基础信息（设置信息和血压统计信息）

## 技术架构

### 基于07版本架构

本项目基于`07_ReActAgentBloodPressureTest`的架构实现，主要变化：
- 移除了所有人工审查相关代码
- 工具直接调用，无需中断和恢复流程
- 同步方式处理请求（不使用Celery异步任务调度）

### 技术栈

- **后端框架**：FastAPI
- **Agent框架**：LangGraph
- **会话管理**：Redis（异步）
- **记忆存储**：PostgreSQL（AsyncPostgresSaver + AsyncPostgresStore）
- **日志系统**：ConcurrentRotatingFileHandler
- **前端界面**：Rich（CLI界面）

### 项目结构

```
0701_ReActAgentBloodPressureNoHILTest/
├── 01_backendServer.py          # 后端API服务（无人工审查版本）
├── 02_frontendServer.py          # 前端客户端（无中断处理版本）
├── utils/
│   ├── __init__.py
│   ├── config.py                # 配置管理
│   ├── llms.py                  # LLM初始化
│   └── tools.py                 # 血压记录相关工具（无人工审查）
├── logfile/                     # 日志文件目录
└── README.md                    # 项目说明文档
```

## 环境要求

### Python版本

- **Python 3.10 或更高版本**（需要使用联合类型语法 `|`）

### 依赖服务

1. **PostgreSQL**：用于短期记忆和长期记忆存储
2. **Redis**：用于会话状态管理

### Python依赖

主要依赖包：
- langgraph
- langchain
- fastapi
- uvicorn
- redis
- psycopg
- rich
- pydantic

注意：不再需要 `python-dateutil` 包，使用标准库的 `datetime` 和 `re` 模块进行日期解析。

## 配置说明

### 环境变量

- `DB_URI`：PostgreSQL连接字符串（可选，有默认值）
- `DEEPSEEK_API_KEY`：DeepSeek API Key（必需）

### 配置文件

配置文件与07版本相同，主要包括：

- **数据库配置**：PostgreSQL和Redis连接参数
- **LLM配置**：模型类型、温度参数等
- **服务配置**：API服务地址和端口（默认8001）

## 运行方式

### 1. 启动后端服务

```bash
cd 0701_ReActAgentBloodPressureNoHILTest
python 01_backendServer.py
```

后端服务将在 `http://localhost:8001` 启动。

### 2. 启动前端客户端

在另一个终端窗口中：

```bash
cd 0701_ReActAgentBloodPressureNoHILTest
python 02_frontendServer.py
```

### 3. 使用示例

启动前端客户端后，按照提示输入用户ID和会话ID，然后开始对话：

```
用户: 你好
Agent: 您好！我是您的健康助手，可以帮助您记录血压数据。您今天测量血压了吗？

用户: 是的，我今天早上8点测量了
Agent: 太好了！请告诉我您的收缩压是多少？

用户: 120
Agent: 好的，收缩压是120 mmHg。请告诉我您的舒张压是多少？

用户: 80
Agent: 好的，收缩压120，舒张压80。请问您是什么时候测量的？

用户: 今天早上8点
Agent: [自动调用 record_blood_pressure 工具，date_time="今天早上8点"会被转换为标准格式]
Agent: 成功保存血压记录：收缩压 120 mmHg，舒张压 80 mmHg，测量日期 2024-01-15，测量时间 2024-01-15T08:00:00。您的血压值在正常范围内，继续保持良好的生活习惯。

用户: info
Agent: [调用 info 工具]
Agent: === 用户设置信息 ===
- 您的偏好设置：每天测量一次血压
=== 血压信息统计 ===
总记录数：1 条
平均收缩压：120.0 mmHg
平均舒张压：80.0 mmHg

最新记录：
  日期：2024-01-15
  收缩压：120 mmHg
  舒张压：80 mmHg
```

## API接口

### 主要接口

1. **POST /agent/invoke**：调用智能体处理用户查询（无中断，直接返回结果）
2. **GET /agent/status/{user_id}/{session_id}**：获取会话状态（状态不包含interrupted）
3. **GET /agent/active/sessionid/{user_id}**：获取用户最近激活的会话ID
4. **GET /agent/sessionids/{user_id}**：获取用户的所有会话ID
5. **POST /agent/write/longterm**：写入长期记忆
6. **DELETE /agent/session/{user_id}/{session_id}**：删除会话

**注意**：已移除 `/agent/resume` 接口（因为不再需要人工审查）

详细API文档可通过访问 `http://localhost:8001/docs` 查看Swagger文档。

## 系统提示词

默认系统提示词包含以下内容：

1. **角色定位**：专业的健康助手
2. **核心任务**：引导用户填写血压数据、验证数据、保存数据
3. **对话策略**：友好、逐步引导、确认后保存
4. **数据验证规则**：血压范围、逻辑检查、健康提醒
5. **日期时间处理**：说明工具会自动转换日期时间格式
6. **可用工具**：列出所有可用工具及其功能
7. **异常处理**：处理用户拒绝、修改、一次性提供所有信息等场景

## 数据存储

### 血压记录存储结构

- **命名空间**：`("blood_pressure", user_id)`
- **Key格式**：`record_{timestamp}_{uuid}`
- **Value格式**：JSON对象
  ```json
  {
      "systolic": 120,
      "diastolic": 80,
      "timestamp": "2024-01-15T08:00:00",
      "date": "2024-01-15",
      "notes": "",
      "record_id": "uuid"
  }
  ```

### 长期记忆

用户的其他长期记忆存储在命名空间 `("memories", user_id)` 中，可以在系统提示词中拼接使用，也可以通过 `info` 工具查询。

## 注意事项

1. **首次运行**：需要确保PostgreSQL和Redis服务已启动
2. **数据库初始化**：首次运行时会自动创建所需的数据表
3. **工具调用**：工具调用会自动执行，无需人工审批
4. **日期转换**：如果用户提供的日期时间格式无法解析，系统会自动使用当前时间
5. **会话管理**：会话数据默认保存1小时（TTL=3600秒），可在配置中修改

## 与07版本的迁移

如果您从07版本迁移到0701版本：

1. **API调用**：移除所有对 `/agent/resume` 的调用
2. **状态处理**：移除所有对 `interrupted` 状态的处理
3. **前端代码**：移除所有中断处理相关代码
4. **数据兼容**：0701版本可以读取07版本创建的血压记录（会自动添加date字段）

## 扩展方向

1. **更智能的日期解析**：集成自然语言处理库，更好地理解中文日期时间表达
2. **数据分析**：添加血压趋势分析、健康建议生成
3. **提醒功能**：定期测量提醒、异常值提醒
4. **多设备支持**：集成智能血压计、自动读取数据
5. **图表生成**：自动生成血压趋势图

## 参考资料

- [LangGraph文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI文档](https://fastapi.tiangolo.com/)
- [项目代码介绍](../AgentTest/项目代码介绍.md)
- [血压记录智能体设计方案](../AgentTest/血压记录智能体设计方案.md)
- [07版本README](../07_ReActAgentBloodPressureTest/README.md)

---

*项目作者：@南哥AGI研习社*  
*创建时间：2024年*  
*版本：0701（无人工审查版本）*

