# 07_ReActAgentBloodPressureTest - 血压记录智能体

## 项目简介

本项目是一个基于LangGraph框架的多轮会话智能体，专门用于引导用户填写和记录血压数据。智能体通过友好的对话方式收集用户的血压信息（收缩压、舒张压、测量时间等），并进行数据验证和持久化存储。

## 功能特性

### 核心功能

1. **多轮对话引导**
   - 友好地引导用户填写血压数据
   - 逐步收集收缩压、舒张压、测量时间和备注信息
   - 支持用户一次性提供所有信息或分多次提供

2. **数据验证**
   - 验证血压数值是否在合理范围内（收缩压：90-250 mmHg，舒张压：60-150 mmHg）
   - 验证收缩压必须大于舒张压
   - 提供健康建议（正常范围、偏高/偏低提醒）

3. **数据持久化**
   - 使用PostgreSQL Store存储血压记录到长期记忆
   - 支持查询历史血压记录
   - 支持更新已保存的血压记录

4. **人工审查（Human-in-the-Loop）**
   - 工具调用前需要人工审批
   - 支持accept（接受）、edit（编辑参数）、reject（拒绝）、response（直接反馈）四种响应类型

### 工具功能

- **record_blood_pressure**：记录血压数据到长期记忆
- **query_blood_pressure**：查询历史血压记录
- **update_blood_pressure**：更新已存在的血压记录

## 技术架构

### 基于05版本架构

本项目基于`05_ReActAgentHILApiMultiSessionTest`的架构实现，采用同步方式处理请求（不使用Celery异步任务调度）。

### 技术栈

- **后端框架**：FastAPI
- **Agent框架**：LangGraph
- **会话管理**：Redis（异步）
- **记忆存储**：PostgreSQL（AsyncPostgresSaver + AsyncPostgresStore）
- **日志系统**：ConcurrentRotatingFileHandler
- **前端界面**：Rich（CLI界面）

### 项目结构

```
07_ReActAgentBloodPressureTest/
├── 01_backendServer.py          # 后端API服务
├── 02_frontendServer.py          # 前端客户端
├── utils/
│   ├── __init__.py
│   ├── config.py                # 配置管理（继承utils/config.py）
│   └── tools.py                 # 血压记录相关工具
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

## 配置说明

### 环境变量

- `DB_URI`：PostgreSQL连接字符串（可选，有默认值）
- `DEEPSEEK_API_KEY`：DeepSeek API Key（必需）

### 配置文件

配置文件继承自`utils/config.py`，主要包括：

- **数据库配置**：PostgreSQL和Redis连接参数
- **LLM配置**：模型类型、温度参数等
- **服务配置**：API服务地址和端口（默认8001）

## 运行方式

### 1. 启动后端服务

```bash
cd 07_ReActAgentBloodPressureTest
python 01_backendServer.py
```

后端服务将在 `http://localhost:8001` 启动。

### 2. 启动前端客户端

在另一个终端窗口中：

```bash
cd 07_ReActAgentBloodPressureTest
python 02_frontendServer.py
```

### 3. 使用示例

启动前端客户端后，按照提示输入用户ID和会话ID，然后开始对话：

```
用户: 你好
Agent: 您好！我是您的健康助手，可以帮助您记录血压数据。您今天测量血压了吗？

用户: 是的，我今天早上测量了
Agent: 太好了！请告诉我您的收缩压是多少？

用户: 120
Agent: 好的，收缩压是120 mmHg。请告诉我您的舒张压是多少？

用户: 80
Agent: 好的，收缩压120，舒张压80。请问您是什么时候测量的？

用户: 今天早上8点
Agent: 收到，测量时间是今天早上8点。还有其他需要备注的信息吗？比如运动后、服药后等？

用户: 没有
Agent: 让我确认一下您的血压数据：
   - 收缩压：120 mmHg
   - 舒张压：80 mmHg
   - 测量时间：今天早上8点
   以上信息是否正确？

用户: 是的，正确
Agent: [调用 record_blood_pressure 工具]
Agent: 好的，您的血压数据已成功保存！您的血压值在正常范围内，继续保持良好的生活习惯。
```

## API接口

### 主要接口

1. **POST /agent/invoke**：调用智能体处理用户查询
2. **POST /agent/resume**：恢复被中断的智能体执行
3. **GET /agent/status/{user_id}/{session_id}**：获取会话状态
4. **GET /agent/active/sessionid/{user_id}**：获取用户最近激活的会话ID
5. **GET /agent/sessionids/{user_id}**：获取用户的所有会话ID
6. **POST /agent/write/longterm**：写入长期记忆
7. **DELETE /agent/session/{user_id}/{session_id}**：删除会话

详细API文档可通过访问 `http://localhost:8001/docs` 查看Swagger文档。

## 系统提示词

默认系统提示词包含以下内容：

1. **角色定位**：专业的健康助手
2. **核心任务**：引导用户填写血压数据、验证数据、保存数据
3. **对话策略**：友好、逐步引导、确认后保存
4. **数据验证规则**：血压范围、逻辑检查、健康提醒
5. **异常处理**：处理用户拒绝、修改、一次性提供所有信息等场景

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
      "notes": "",
      "record_id": "uuid"
  }
  ```

### 长期记忆

用户的其他长期记忆存储在命名空间 `("memories", user_id)` 中，可以在系统提示词中拼接使用。

## 注意事项

1. **首次运行**：需要确保PostgreSQL和Redis服务已启动
2. **数据库初始化**：首次运行时会自动创建所需的数据表
3. **工具调用审批**：每次工具调用都需要人工审批，可以通过前端界面进行响应
4. **会话管理**：会话数据默认保存1小时（TTL=3600秒），可在配置中修改

## 扩展方向

1. **数据分析**：添加血压趋势分析、健康建议生成
2. **提醒功能**：定期测量提醒、异常值提醒
3. **多设备支持**：集成智能血压计、自动读取数据
4. **图表生成**：自动生成血压趋势图

## 参考资料

- [LangGraph文档](https://langchain-ai.github.io/langgraph/)
- [FastAPI文档](https://fastapi.tiangolo.com/)
- [项目代码介绍](../AgentTest/项目代码介绍.md)
- [血压记录智能体设计方案](../AgentTest/血压记录智能体设计方案.md)

---

*项目作者：@南哥AGI研习社*  
*创建时间：2024年*

