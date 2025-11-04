# LangGraph 数据库存储：二进制 vs 明文存储分析

## 一、为什么存储在库中的信息要序列化为二进制？

### 1.1 技术原因

#### 1.1.1 LangGraph 的默认序列化机制

LangGraph 使用 `JsonPlusSerializer` 作为默认序列化器，它采用以下策略：

1. **优先使用 msgpack**：对于大多数对象，优先使用 `ormsgpack`（msgpack的高性能实现）进行序列化
2. **JSON 作为后备**：如果 msgpack 失败（如包含非UTF-8字符），回退到 JSON 序列化
3. **Pickle 作为最后手段**：如果配置了 `pickle_fallback=True`，可以回退到 pickle

**序列化流程**：
```python
# JsonPlusSerializer.dumps_typed() 的逻辑
try:
    return "msgpack", _msgpack_enc(obj)  # 优先使用 msgpack
except ormsgpack.MsgpackEncodeError:
    if "valid UTF-8" in str(exc):
        return "json", self.dumps(obj)    # 回退到 JSON
    elif self.pickle_fallback:
        return "pickle", pickle.dumps(obj)  # 最后回退到 pickle
```

#### 1.1.2 为什么选择二进制格式（msgpack）？

**优势**：

1. **性能优势**：
   - msgpack 比 JSON 更快（序列化/反序列化速度）
   - 二进制格式更紧凑，存储空间更小
   - 减少数据库 I/O 操作

2. **数据完整性**：
   - 保留 Python 对象的完整类型信息
   - 支持复杂对象（如 Pydantic 模型、UUID、Path 等）
   - 避免 JSON 序列化过程中的信息丢失

3. **兼容性**：
   - 支持自定义对象的序列化（通过 Extension Type）
   - 保留 LangChain 消息对象的完整结构

**示例对比**：

```python
# 消息对象结构
HumanMessage(
    content="预定一个汉庭酒店",
    id="msg_123",
    additional_kwargs={...},
    response_metadata={...}
)

# JSON 序列化（明文）
{
    "type": "HumanMessage",
    "content": "预定一个汉庭酒店",
    "id": "msg_123",
    ...
}

# msgpack 序列化（二进制）
<二进制数据，约 243 bytes>

# 存储空间对比（近似值）：
# JSON: ~500 bytes
# msgpack: ~243 bytes  
# 节省约 50% 存储空间
```

### 1.2 设计原因

#### 1.2.1 数据模型复杂度

LangGraph 需要存储的消息对象包含：

- **LangChain 消息对象**：HumanMessage, AIMessage, ToolMessage, SystemMessage
- **工具调用信息**：tool_calls, tool_call_id
- **元数据**：response_metadata, additional_kwargs
- **消息 ID**：用于追踪和关联

这些对象无法简单地转换为纯文本 JSON，需要保留类型信息以便反序列化。

#### 1.2.2 检查点系统的需求

LangGraph 的检查点系统需要：

1. **快速恢复状态**：二进制格式可以更快地恢复 Agent 状态
2. **版本控制**：通过版本号管理不同版本的检查点
3. **链式结构**：通过 `parent_checkpoint_id` 形成检查点链

### 1.3 直接存储原始信息是否可行？

**理论上可行，但有以下问题**：

1. **信息丢失**：
   - Python 对象的类型信息可能丢失
   - 复杂对象（如 Pydantic 模型）无法直接序列化

2. **性能问题**：
   - JSON 文本存储占用更多空间
   - 查询和更新性能下降

3. **兼容性问题**：
   - 无法直接存储 LangChain 的消息对象
   - 需要额外的转换逻辑

---

## 二、API 是否支持修改为明文存储？

### 2.1 官方 API 支持情况

**✅ 部分支持**：LangGraph 提供了自定义序列化器的接口

#### 2.1.1 自定义序列化器接口

`AsyncPostgresSaver` 支持通过 `serde` 参数传入自定义序列化器：

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol

# 自定义序列化器
class CustomSerializer(SerializerProtocol):
    def dumps(self, obj: Any) -> bytes:
        # 返回 JSON 编码的字节
        return json.dumps(obj).encode('utf-8')
    
    def loads(self, data: bytes) -> Any:
        # 从字节解码 JSON
        return json.loads(data.decode('utf-8'))
    
    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        # 返回类型和序列化后的数据
        return "json", json.dumps(obj).encode('utf-8')
    
    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        type_, data_ = data
        return json.loads(data_.decode('utf-8'))

# 使用自定义序列化器
async with AsyncPostgresSaver.from_conn_string(
    db_uri,
    serde=CustomSerializer()  # 传入自定义序列化器
) as checkpointer:
    await checkpointer.setup()
```

#### 2.1.2 限制

**⚠️ 关键限制**：即使使用自定义序列化器，数据仍然存储在 `BYTEA` 字段中

```sql
-- 表结构定义（base.py）
CREATE TABLE checkpoint_writes (
    ...
    blob BYTEA NOT NULL,  -- 仍然是二进制字段
    ...
);
```

这意味着：
- 数据库层面仍然是二进制存储
- 即使序列化为 JSON，也需要通过 `encode('utf-8')` 转换为字节
- 数据库查询时仍然看到的是二进制数据

#### 2.1.3 真正的明文存储

要实现真正的明文存储，需要：

1. **修改表结构**：将 `blob BYTEA` 改为 `data TEXT` 或 `data JSONB`
2. **修改序列化逻辑**：不返回 bytes，直接返回字符串
3. **修改读取逻辑**：不进行字节解码，直接读取文本

**这需要修改 LangGraph 的源码**，官方 API 不直接支持。

---

## 三、如何改造为明文存储？有何风险？

### 3.1 改造方案

#### 方案一：自定义序列化器（部分明文）

**优点**：
- 不需要修改 LangGraph 源码
- 数据以 JSON 格式存储（虽然仍是 BYTEA）

**缺点**：
- 数据库层面仍然是二进制
- 需要额外的解码步骤才能查看

**实现**：

```python
import json
from typing import Any
from langgraph.checkpoint.serde.base import SerializerProtocol

class JsonPlainSerializer(SerializerProtocol):
    """JSON 明文序列化器（虽然是二进制字段，但内容是 JSON）"""
    
    def dumps(self, obj: Any) -> bytes:
        """序列化为 JSON 字节"""
        return json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8')
    
    def loads(self, data: bytes) -> Any:
        """从 JSON 字节反序列化"""
        return json.loads(data.decode('utf-8'))
    
    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """返回类型和 JSON 字节"""
        return "json", self.dumps(obj)
    
    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        """从类型和 JSON 字节反序列化"""
        type_, data_ = data
        if type_ == "json":
            return self.loads(data_)
        raise ValueError(f"Unknown type: {type_}")

# 使用
async with AsyncPostgresSaver.from_conn_string(
    db_uri,
    serde=JsonPlainSerializer()
) as checkpointer:
    await checkpointer.setup()
```

**查看数据**：

```python
# 虽然存储为 BYTEA，但可以通过解码查看
import psycopg

async with await psycopg.AsyncConnection.connect(db_uri) as conn:
    async with conn.cursor() as cur:
        await cur.execute("""
            SELECT 
                channel,
                encode(blob, 'escape') as blob_text
            FROM checkpoint_writes 
            WHERE thread_id = '1' 
            LIMIT 1
        """)
        result = await cur.fetchone()
        print(result['blob_text'])  # 可以看到 JSON 文本
```

#### 方案二：修改表结构（完全明文）

**⚠️ 需要修改 LangGraph 源码**

**步骤**：

1. **修改表结构定义**：

```python
# 修改 langgraph/checkpoint/postgres/base.py

# 原代码（第56行）
blob BYTEA NOT NULL,

# 改为
data JSONB NOT NULL,  # 或 TEXT NOT NULL
```

2. **修改写入逻辑**：

```python
# 修改 _dump_writes 方法
def _dump_writes(self, ...):
    return [
        (
            thread_id,
            checkpoint_ns,
            checkpoint_id,
            task_id,
            task_path,
            idx,
            channel,
            "json",  # 类型
            json.dumps(value)  # 直接存储 JSON 字符串
        )
        for idx, (channel, value) in enumerate(writes)
    ]
```

3. **修改读取逻辑**：

```python
# 修改 _load_writes 方法
def _load_writes(self, writes):
    return [
        (
            tid.decode(),
            channel.decode(),
            json.loads(data.decode())  # 从 JSON 字符串解析
        )
        for tid, channel, t, data in writes
    ]
```

4. **修改 SQL 语句**：

```python
# 修改 UPSERT_CHECKPOINT_WRITES_SQL
UPSERT_CHECKPOINT_WRITES_SQL = """
    INSERT INTO checkpoint_writes (
        thread_id, checkpoint_ns, checkpoint_id, task_id, 
        task_path, idx, channel, type, data  -- blob 改为 data
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
    ...
"""
```

**优点**：
- 完全明文存储
- 可以直接用 SQL 查询和分析
- 便于调试和维护

**缺点**：
- 需要修改 LangGraph 源码
- 升级 LangGraph 时需要重新应用修改
- 可能存在兼容性问题

#### 方案三：使用 JSONB 存储（推荐）

**最佳方案**：保持二进制字段，但使用 JSONB 格式

**实现**：

```python
import json
from typing import Any
from langgraph.checkpoint.serde.base import SerializerProtocol

class JsonbSerializer(SerializerProtocol):
    """JSONB 序列化器 - 存储为 JSON 格式，但仍然是二进制字段"""
    
    def dumps(self, obj: Any) -> bytes:
        """序列化为 JSON 字节（格式化为可读格式）"""
        return json.dumps(
            obj, 
            ensure_ascii=False, 
            indent=2,
            default=str  # 处理无法序列化的对象
        ).encode('utf-8')
    
    def loads(self, data: bytes) -> Any:
        """从 JSON 字节反序列化"""
        return json.loads(data.decode('utf-8'))
    
    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """返回类型和 JSON 字节"""
        return "json", self.dumps(obj)
    
    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        """从类型和 JSON 字节反序列化"""
        type_, data_ = data
        if type_ == "json":
            return self.loads(data_)
        raise ValueError(f"Unknown type: {type_}")

# 使用
async with AsyncPostgresSaver.from_conn_string(
    db_uri,
    serde=JsonbSerializer()
) as checkpointer:
    await checkpointer.setup()
```

**查看数据**：

```sql
-- 直接查询 JSON 内容
SELECT 
    thread_id,
    channel,
    encode(blob, 'escape') as json_content
FROM checkpoint_writes
WHERE thread_id = '1'
AND channel = 'messages';
```

---

### 3.2 风险分析

#### 3.2.1 方案一的风险（自定义序列化器）

**风险级别：低**

**风险**：
1. ✅ **兼容性良好**：使用官方 API，不影响 LangGraph 升级
2. ✅ **性能影响小**：JSON 序列化性能略低于 msgpack，但可接受
3. ⚠️ **存储空间增加**：JSON 比 msgpack 占用更多空间（约增加 30-50%）
4. ⚠️ **类型信息丢失**：某些复杂对象可能无法正确序列化

**建议**：
- 适合开发和调试阶段
- 生产环境建议保留 msgpack

#### 3.2.2 方案二的风险（修改源码）

**风险级别：高**

**风险**：
1. ❌ **升级困难**：每次 LangGraph 升级都需要重新应用修改
2. ❌ **维护成本高**：需要维护自己的 LangGraph 分支
3. ❌ **兼容性问题**：可能与新版本不兼容
4. ❌ **测试覆盖**：需要充分测试所有功能
5. ⚠️ **性能影响**：JSONB 查询性能可能低于二进制存储

**建议**：
- 不推荐在生产环境使用
- 仅用于特殊需求或深度定制

#### 3.2.3 方案三的风险（JSONB 序列化器）

**风险级别：中**

**风险**：
1. ✅ **兼容性良好**：使用官方 API
2. ⚠️ **存储空间增加**：JSON 格式占用更多空间
3. ⚠️ **性能影响**：序列化/反序列化速度略慢
4. ✅ **可读性好**：便于调试和查看

**建议**：
- 适合开发和调试
- 可以用于生产环境（如果可读性比性能更重要）

---

### 3.3 性能对比

| 指标 | msgpack（默认） | JSON（自定义） | JSONB（数据库） |
|------|----------------|---------------|----------------|
| 序列化速度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 反序列化速度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 存储空间 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| 可读性 | ⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 兼容性 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

### 3.4 实际建议

#### 3.4.1 开发阶段

**推荐方案**：使用自定义 JSON 序列化器（方案一或方案三）

**原因**：
- 便于调试和查看数据
- 不影响生产环境
- 易于切换回默认方案

#### 3.4.2 生产环境

**推荐方案**：保留默认的 msgpack 序列化

**原因**：
- 性能最优
- 存储空间最小
- 官方支持，稳定性最好

**如果需要查看数据**：
- 使用 `query_chat_history.py` 脚本查看
- 通过 LangGraph API 读取
- 不要直接查询数据库

#### 3.4.3 特殊情况

如果确实需要明文存储：

1. **使用方案三**（JSONB 序列化器）
2. **监控性能影响**
3. **准备回退方案**

---

## 四、总结

### 4.1 为什么要二进制存储？

1. **性能考虑**：msgpack 比 JSON 更快、更紧凑
2. **数据完整性**：保留完整的 Python 对象类型信息
3. **设计决策**：LangGraph 的设计就是基于二进制存储

### 4.2 API 是否支持修改？

**部分支持**：
- ✅ 可以自定义序列化器
- ❌ 无法直接修改表结构为 TEXT/JSONB
- ⚠️ 即使自定义序列化器，数据库字段仍然是 BYTEA

### 4.3 如何改造？

**三个方案**：
1. **方案一**：自定义 JSON 序列化器（低风险，推荐用于开发）
2. **方案二**：修改源码（高风险，不推荐）
3. **方案三**：JSONB 序列化器（中风险，平衡可读性和性能）

### 4.4 风险

**主要风险**：
- 性能下降（序列化/反序列化速度）
- 存储空间增加（约 30-50%）
- 维护成本（如果修改源码）
- 兼容性问题（升级困难）

### 4.5 最终建议

**对于大多数场景**：
- ✅ 保留默认的 msgpack 二进制存储
- ✅ 使用 `query_chat_history.py` 脚本查看数据
- ✅ 通过 LangGraph API 访问数据

**对于特殊需求**：
- ⚠️ 使用自定义 JSON 序列化器（方案一或方案三）
- ⚠️ 监控性能影响
- ⚠️ 准备回退方案

**不推荐**：
- ❌ 修改 LangGraph 源码（方案二）
- ❌ 直接查询数据库二进制字段

---

## 五、代码示例

### 5.1 自定义 JSON 序列化器示例

```python
# utils/json_serializer.py
import json
from typing import Any
from langgraph.checkpoint.serde.base import SerializerProtocol

class JsonPlainSerializer(SerializerProtocol):
    """JSON 明文序列化器 - 便于调试和查看"""
    
    def dumps(self, obj: Any) -> bytes:
        """序列化为 JSON 字节"""
        return json.dumps(
            obj, 
            ensure_ascii=False, 
            indent=2,
            default=str
        ).encode('utf-8')
    
    def loads(self, data: bytes) -> Any:
        """从 JSON 字节反序列化"""
        return json.loads(data.decode('utf-8'))
    
    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """返回类型和 JSON 字节"""
        return "json", self.dumps(obj)
    
    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        """从类型和 JSON 字节反序列化"""
        type_, data_ = data
        if type_ == "json":
            return self.loads(data_)
        raise ValueError(f"Unknown type: {type_}")
```

### 5.2 使用自定义序列化器

```python
# 01_shortTermTest.py 修改
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from utils.json_serializer import JsonPlainSerializer

async with AsyncPostgresSaver.from_conn_string(
    db_uri,
    serde=JsonPlainSerializer()  # 使用自定义序列化器
) as checkpointer:
    await checkpointer.setup()
    # ... 其余代码不变
```

### 5.3 查看 JSON 格式的数据

```python
# query_json_data.py
import asyncio
import psycopg

async def view_json_data(thread_id: str = "1"):
    """查看 JSON 格式的存储数据"""
    db_uri = "postgresql://postgres:sxl_pwd_123@localhost:5433/sxl_pg_db1?sslmode=disable"
    
    async with await psycopg.AsyncConnection.connect(db_uri) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT 
                    checkpoint_id,
                    channel,
                    type,
                    encode(blob, 'escape') as json_content
                FROM checkpoint_writes
                WHERE thread_id = %s
                AND channel = 'messages'
                ORDER BY checkpoint_id DESC
                LIMIT 1
            """, (thread_id,))
            
            result = await cur.fetchone()
            if result:
                print("JSON 内容：")
                print(result['json_content'])
            else:
                print("未找到数据")

if __name__ == "__main__":
    asyncio.run(view_json_data())
```

---

## 六、参考资料

1. LangGraph 源码：
   - `langgraph/checkpoint/postgres/base.py`
   - `langgraph/checkpoint/serde/jsonplus.py`
   - `langgraph/checkpoint/serde/base.py`

2. PostgreSQL 文档：
   - BYTEA 类型：https://www.postgresql.org/docs/current/datatype-binary.html
   - JSONB 类型：https://www.postgresql.org/docs/current/datatype-json.html

3. 序列化格式对比：
   - msgpack：https://msgpack.org/
   - JSON：https://www.json.org/

