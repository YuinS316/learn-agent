# Agent 上下文压缩功能需求文档

## 1. 背景

### 1.1 项目现状

当前项目是一个基于 Anthropic API 的 coding agent，核心架构：

| 组件 | 文件 | 说明 |
|------|------|------|
| Agent loop | `agent_loop.py` | `run_one_turn()` → API 调用 → 工具执行 → 循环 |
| LoopState | `loop_state.py` | 消息列表、plan 状态、失败追踪 |
| AgentConfig | `agent_config.py` | parent/subagent 的差异化配置 |
| normalize_messages | `utils/normalize_messages.py` | 消息清理 + tool_use/tool_result 配对校验 |
| execute_tool_use_blocks | `agent_loop.py:154` | 遍历 tool_use block，调用 handler，返回 tool_result |
| Settings | `config/settings.py` | pydantic-settings，环境变量驱动 |
| Skills | `skill_registry.py` | `.agents/skills/` 下 SKILL.md 发现 |

已有工具：`bash`、`read_file`、`write_file`、`edit_file`、`glob`、`create_plan`、`update_plan_status`、`delegate_task`、`load_skill`

### 1.2 问题

随着 agent 任务复杂度和工具调用次数增加，上下文长度快速膨胀：

- 工具读取的大文件内容（`read_file` 无 limit 时可能数千行）
- 历史 tool_result 累积
- 多轮对话堆积的旧推理过程

**影响**：
- 触达模型上下文窗口上限导致请求失败
- 输入 token 成本线性增长
- 过长上下文中关键信息被稀释（"lost in the middle"）

### 1.3 目标

实现 **L1 + L2 两层渐进式上下文压缩机制**，在保证 agent 推理质量的前提下，控制活跃上下文长度，并通过 transcript 保留完整可恢复记录。L3/L4 作为未来规划。

---

## 2. 整体设计

### 2.1 设计原则

- **渐进压缩**：从轻到重，能用轻量层就不用重量层
- **信息可恢复**：所有被压缩的内容落盘，有可回查入口
- **与现有代码紧密集成**：压缩插入点在 `execute_tool_use_blocks` 和 `normalize_messages` 中，不引入独立中间件
- **可观测**：每次压缩记录触发层级、压缩前后 token 数、耗时
- **精确计数**：使用 Anthropic SDK 的 `count_tokens` API，不用字符估算

### 2.2 两层压缩概览（MVP）

| 层级 | 名称 | 触发时机 | 触发条件 | 处理对象 |
|------|------|----------|----------|----------|
| L1 | 大结果落盘 | 工具返回后立即 | 单个 tool_result > 10k tokens | 当前 tool_result |
| L2 | 历史 tool_result 裁剪 | 下一轮请求前 | 总上下文 ≥ 75% context_window | 旧的 tool_result |

**L3（旧对话裁剪）和 L4（全量摘要）** 风险较高（摘要质量不可控、摘要请求本身消耗大量 token），作为未来规划放在附录。

### 2.3 整体流程

```
┌─────────────────────────────────────────────┐
│  run_one_turn() 每一轮                       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │ execute_tool_use_blocks │
       │   ↓                    │
       │ L1 检测：result > 10k  │──Yes──► 落盘 .agents/cache/tool_results/
       │ tokens?                │         消息内容替换为预览 + 文件路径
       └───────────┬───────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │ 工具结果追加到        │
       │ state.messages        │
       └───────────┬───────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │ 更新 state.estimated  │
       │ _tokens（count_tokens）│
       └───────────┬───────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │ 下一轮 run_one_turn() │
       │ normalize_messages()  │
       │   ↓                   │
       │ L2 检测：≥ 75% 窗口？ │──Yes──► 保留最近 3 次 tool_result
       │                           │     更早的替换为占位符
       └───────────┬───────────┘
                   │
                   ▼
       ┌───────────────────────┐
       │ API 请求              │
       └───────────────────────┘
```

### 2.4 Token 计量

**使用 Anthropic SDK 的 `client.beta.messages.count_tokens()` 精确计数。**

```python
# 项目已有 client 实例
from learn_agent.agent_loop import client

result = client.beta.messages.count_tokens(
    model=settings.ANTHROPIC_MODEL,
    messages=normalized_messages,
    system=system_prompt,
)
token_count = result.input_tokens
```

- 每轮 `run_one_turn()` 结束后更新 `state.estimated_tokens`
- 由于 `count_tokens` 本身也是一次 API 调用，**每轮只调用一次**（在构建好完整 messages + system 后）
- 为减少延迟，可以在发送给模型的主请求前并行调用 `count_tokens`（当压缩判定不需要等待结果时）

### 2.5 上下文窗口

**动态读取，不硬编码。** 通过以下方式获取：

```python
# 方式 1：模型名 → 已知窗口映射（本地，零延迟）
MODEL_CONTEXT_WINDOWS = {
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-opus-4-8-20250224": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    # ...
}

# 方式 2：count_tokens API 的响应中可能包含模型限制信息
```

MVP 采用**方式 1**（已知映射表），并在 `Settings` 中提供 `CONTEXT_WINDOW` 覆盖项。后续可探索从 API 自动获取。

---

## 3. L1 大结果落盘

### 3.1 触发条件

在 `execute_tool_use_blocks()` 中，每个 tool_result 生成后立即检查：

- 阈值：`token_count(tool_result_content) > L1_TOOL_RESULT_THRESHOLD_TOKENS`（默认 10,000）
- 使用 `count_tokens` 精确计算单条消息的 token 数

### 3.2 集成点

**`agent_loop.py:154` 的 `execute_tool_use_blocks()` 函数，返回 results 之前。**

```python
def execute_tool_use_blocks(tool_use_blocks, state, config):
    results = []
    for tu in tool_use_blocks:
        # ... 现有逻辑：调用 handler，得到 output 字符串 ...

        # ── L1 compaction ──────────────────────────
        if config.has_compaction_layer("L1"):
            output = apply_l1_compaction(output, tu, state)
        
        results.append({...})
    return results
```

### 3.3 处理流程

1. 调用 `count_tokens` 检查单个 tool_result content 的 token 数
2. 超过阈值 → 生成 `cache_id = f"{state.turn_count}_{tu['id']}"`
3. 完整内容写入 `.agents/cache/tool_results/{state.session_id}/{cache_id}.txt`
4. 生成预览：前 30 行 + 分隔符 + 后 20 行
5. 替换原 tool_result 的 content 为：

```
[Large tool result cached]
cache_id: 12_toolu_abc123
file_path: .agents/cache/tool_results/sess_xxx/12_toolu_abc123.txt
total_lines: 4823
total_tokens: 28500

--- Preview (first 30 lines) ---
<前30行内容>

... [4773 lines omitted] ...

--- Preview (last 20 lines) ---
<后20行内容>

[Use read_file to read full content: read_file(path=".agents/cache/.../12_toolu_abc123.txt")]
```

关键变化：**不再引入 `read_cached_tool_result` 新工具**，直接用已有的 `read_file` 按路径读取。

### 3.4 存储管理

- 路径：`.agents/cache/tool_results/{session_id}/`
- MVP 阶段不主动清理，session 结束后可手动删除整个 session 目录
- 后续可加 LRU / TTL 策略

---

## 4. L2 历史 tool_result 裁剪

### 4.1 触发条件

在 `normalize_messages()` 调用前后检测，上下文总 token ≥ **75% context_window**。

### 4.2 集成点

**在 `run_one_turn()` 中，`normalize_messages()` 调用前或调用后。** 建议在 `normalize_messages()` 之后做 L2 处理，因为此时消息格式已经规范化，tool_use/tool_result 配对已校验通过。

```python
def run_one_turn(state, config):
    # ...
    messages = normalize_messages(state.messages)
    
    # ── L2 compaction ──────────────────────────
    if config.has_compaction_layer("L2"):
        messages = apply_l2_compaction(messages, state, config)
    
    response = client.messages.create(
        messages=messages,
        # ...
    )
```

### 4.3 处理策略

- 保留**最近 3 次** tool_result 的完整内容
- 更早的 tool_result：
  - 如果已经被 L1 压缩过 → **保持不变**（预览 + 文件路径已经很短）
  - 如果未被 L1 压缩 → 替换 content 为占位符：

```
[Earlier tool result compacted - L2]
tool: read_file
args: path=src/main.py
Re-run if needed, or check .agents/transcripts/{session_id}.jsonl for full history.
```

### 4.4 目标水位

| 参数 | 值 | 说明 |
|------|-----|------|
| L2 触发比例 | 75% | context_window * 0.75 |
| L2 目标比例 | 55% | 压缩后应降到该水位以下 |

如果 L2 执行后仍然超过 75%，记录 warning 日志，不做进一步处理（L3/L4 尚未实现）。

### 4.5 关键约束

- **tool_use 和 tool_result 必须成对**（Anthropic API 严格校验）
- 仅替换 tool_result 的 content 字段，不删除消息
- 占位符保留**工具名 + 参数摘要**，让模型判断是否需要重跑
- 有副作用的工具（`write_file`、`edit_file`、`bash`）的占位符额外标注 "⚠ Side-effect tool — do NOT re-run blindly"

### 4.6 幂等性

- 每条被 L1 压缩的 tool_result 标记为 `_l1_compacted: true`
- L2 遍历时跳过已有 `_l1_compacted` 标记的消息（内容已经够短）
- 已被 L2 压缩的标记为 `_l2_compacted: true`，避免重复处理
- 这些元数据字段在 `normalize_messages` 中已被 strip，不会发给 API

---

## 5. Token 计量与上下文跟踪

### 5.1 LoopState 扩展

```python
@dataclass
class LoopState:
    # ... 现有字段 ...
    session_id: str = ""                        # 新增
    estimated_tokens: int = 0                   # 新增：当前上下文 token 估算
    compaction_log: list[dict] = field(default_factory=list)  # 新增
```

### 5.2 更新时机

在 `run_one_turn()` 中，工具结果追加到 `state.messages` 后：

```python
# 追加 tool_results 到 messages 后
state.messages.append({"role": "user", "content": tool_results})
state.turn_count += 1

# 更新 token 估算（异步/同步取决于性能要求）
state.estimated_tokens = estimate_context_tokens(state, config)
```

### 5.3 估算函数

```python
def estimate_context_tokens(state: LoopState, config: AgentConfig) -> int:
    """Estimate total context tokens including system prompt."""
    system = build_system(state, config)
    messages = normalize_messages(state.messages)
    result = client.beta.messages.count_tokens(
        model=settings.ANTHROPIC_MODEL,
        messages=messages,
        system=system,
    )
    return result.input_tokens
```

MVP 阶段同步调用（增加一轮 API 延迟）。后续可改为：用上一轮的已知值 + 本轮的增量估算，异步更新精确值。

---

## 6. 集成实现指南

### 6.1 修改文件清单

| 文件 | 改动 |
|------|------|
| `agent-design.md` | 本文档（重写） |
| `config/settings.py` | 新增 compaction 配置字段 |
| `loop_state.py` | 新增 `session_id`、`estimated_tokens`、`compaction_log` |
| `agent_config.py` | `AgentConfig` 新增 `compaction_layers` 字段 |
| `agent_loop.py` | 1) L1 插入 `execute_tool_use_blocks` 2) L2 插入 `run_one_turn` 3) token 估算 4) session_id 生成 |
| `main.py` | 启动时生成 session_id 传入 LoopState |

### 6.2 各集成点详细说明

#### A. Session ID 生成（`main.py` 或 `agent_loop.py`）

```python
import time, random, string

def generate_session_id() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{ts}_{rand}"
```

在 `main.py` 中生成并传入 `LoopState`：

```python
state = LoopState(
    messages=history,
    session_id=generate_session_id(),
)
```

#### B. L1 插入 `execute_tool_use_blocks`

在函数返回 results 前，对每个 result 判大小。超过阈值的落盘并替换 content。需要接收 `state` 参数以获取 `session_id` 和 `turn_count`。

#### C. L2 插入 `run_one_turn`

在 `normalize_messages()` 调用后、`client.messages.create()` 前。检查 `state.estimated_tokens`，超过 75% 阈值则裁剪旧 tool_result。

#### D. System prompt 注入压缩状态（`build_system`）

```python
def build_system(state, config):
    prompt = config.system_prompt
    # ... 现有 goal / plan progress 注入 ...

    # ── Compaction status ──────────────────────
    if state.compaction_log:
        recent = state.compaction_log[-3:]  # 最近 3 条
        prompt += "\n\n## Context Compaction Status\n"
        for entry in recent:
            prompt += (
                f"- L{entry['layer']} at turn {entry['turn']}: "
                f"saved {entry['saved_tokens']} tokens "
                f"({entry['before_tokens']} → {entry['after_tokens']})\n"
            )
        prompt += "Full transcript: .agents/transcripts/{session_id}.jsonl\n"

    return prompt
```

### 6.3 文件目录结构（压缩相关新增）

```
.agents/
├── skills/                  # 已有
│   ├── brainstorming/
│   ├── dispatching-parallel-agents/
│   └── ...
├── cache/                   # 新增
│   └── tool_results/
│       └── {session_id}/
│           └── {turn}_{tool_use_id}.txt
└── transcripts/             # 新增
    └── {session_id}.jsonl
```

`.gitignore` 追加：

```
.agents/cache/
.agents/transcripts/
```

---

## 7. 配置项汇总

所有配置作为 `Settings` 字段，支持 `.env` 环境变量覆盖：

```python
# config/settings.py 新增字段

class Settings(BaseSettings):
    # ... 现有字段 ...

    # ── Compaction ──────────────────────────────
    # 总开关：是否启用上下文压缩
    COMPACTION_ENABLED: bool = True

    # 上下文窗口（0 = 自动根据模型推断）
    CONTEXT_WINDOW: int = 0

    # L1 大结果落盘
    L1_ENABLED: bool = True
    L1_TOOL_RESULT_THRESHOLD_TOKENS: int = 10_000
    L1_PREVIEW_HEAD_LINES: int = 30
    L1_PREVIEW_TAIL_LINES: int = 20
    L1_CACHE_DIR: str = ".agents/cache/tool_results"

    # L2 历史 tool_result 裁剪
    L2_ENABLED: bool = True
    L2_TRIGGER_RATIO: float = 0.75
    L2_TARGET_RATIO: float = 0.55
    L2_KEEP_RECENT_TOOL_RESULTS: int = 3

    # Transcript
    TRANSCRIPT_ENABLED: bool = True
    TRANSCRIPT_DIR: str = ".agents/transcripts"
```

### AgentConfig 绑定

```python
@dataclass(frozen=True)
class AgentConfig:
    # ... 现有字段 ...
    compaction_layers: frozenset[str] = frozenset()  # {"L1", "L2"}

# Parent: 启用 L1 + L2
PARENT_AGENT_CONFIG = AgentConfig(
    # ... 现有字段 ...
    compaction_layers=frozenset({"L1", "L2"}),
)

# Subagent: 仅 L1（短生命周期，不需要 L2）
SUBAGENT_CONFIG = AgentConfig(
    # ... 现有字段 ...
    compaction_layers=frozenset({"L1"}),
)
```

---

## 8. Transcript 持久化

### 8.1 文件位置

`.agents/transcripts/{session_id}.jsonl`

### 8.2 格式（每行一条 JSON）

普通消息行：

```json
{"turn": 42, "timestamp": "2026-06-20T13:41:48Z", "role": "assistant", "content": [...], "tokens_est": 1234}
```

压缩事件行：

```json
{"turn": 42, "timestamp": "2026-06-20T13:41:48Z", "compaction": {"layer": "L1", "cache_id": "42_toolu_abc", "before_tokens": 28500, "after_tokens": 1200, "duration_ms": 45}}
```

### 8.3 写入时机

- 每轮 agent loop 结束时追加新增消息
- 压缩事件发生时立即追加事件记录
- **写入失败不阻塞主流程**，记录 error log

### 8.4 实现

```python
def append_transcript(state: LoopState, entry: dict) -> None:
    path = os.path.join(CWD, ".agents/transcripts", f"{state.session_id}.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"\033[33m[transcript] write failed: {e}\033[0m")
```

---

## 9. 坑点与边界情况

### 9.1 Tool_use / Tool_result 配对

Anthropic API 严格要求配对。L2 只替换 content，**不删除消息**。占位符保持 tool_result block 结构完整。

### 9.2 有副作用工具的重跑风险

L2 占位符告诉模型可以 re-run，但 `write_file`、`edit_file`、`bash` 等工具重跑有风险。

**缓解**：占位符中按工具名分类标注：
- 读类工具（`read_file`、`glob`）："Re-run if needed"
- 写类工具（`write_file`、`edit_file`、`bash`）："⚠ Side-effect — do NOT re-run blindly. Check full history or ask user."

### 9.3 L1 预览可能看不到关键内容

"前 30 + 后 20" 对不同内容效果不同。日志类错误通常在尾部，代码类关键在头部，中间夹错可能两头都看不到。

**MVP 不优化**，模型发现预览不够时会主动用 `read_file` 读完整缓存文件。

### 9.4 缓存路径泄露

模型可能把 `.agents/cache/...` 路径展示给用户。

**缓解**：在 system prompt 中明确说明 `.agents/cache/` 是内部缓存，不应直接展示给用户；展示时应描述为"已缓存的结果"。

### 9.5 Token 计数 API 的额外延迟

`count_tokens` 是一次额外的 API 调用，增加延迟。

**缓解**：
- L1 只需要对单个结果计数，可本地估算（`tiktoken` 库）做快速初筛，超过阈值再用 API 精确确认
- L2 的 token 总数可以用上一轮已知值 + 本轮增量估算，减少调用频率
- 后续可每 N 轮调用一次精确计数，中间用增量估算

### 9.6 阈值抖动

L2 压缩后可能刚好降到 74%，下一轮多了点工具结果又超 75%。

**缓解**：L2 目标水位 55%，远低于触发水位 75%，提供足够缓冲。

### 9.7 大结果的 L1 判定效率

如果工具返回 200k+ 字符的字符串，把整个字符串传给 `count_tokens` 也很浪费。

**缓解**：先做长度快速预判，超过阈值字符数（如 40k 字符 = 阈值 10k token × 4 系数）再调用 `count_tokens`。这个预判可以用保守系数。

---

## 10. 附录：L3/L4 未来规划

以下内容不在 MVP 范围，仅作未来参考。

### 10.1 L3：旧对话裁剪（设计草稿）

**触发**：总上下文 ≥ 85% context_window（未来实现 L3 后阈值可能调整）

**策略**：
- 保留头 3 条 + 尾 47 条 → **改为 token 预算制**：保留头部 ~5k token + 尾部 ~50k token
- 中间替换为摘要标记
- 裁剪边界对齐到完整 turn

**风险**：丢失中间对话中的关键约束和上下文

### 10.2 L4：全量摘要（设计草稿）

**触发**：总上下文 ≥ 92% context_window

**策略**：
- 保留最近 10 轮原始对话
- 之前所有消息 → 调用模型生成结构化摘要
- 摘要本身就消耗大量 input token

**核心风险**：
- 摘要是有损压缩，可能漏掉关键信息
- 摘要请求本身是巨大的 token 消耗
- 需要严格的结构化 schema 输出
- 需要重试机制（3 次指数退避）

### 10.3 Transcript 搜索工具（为 L3/L4 预留）

当 L3/L4 实施后，模型需要能查询被压缩的对话内容。预留工具设计：

```json
{
  "name": "search_transcript",
  "description": "Search the full conversation transcript for information that may have been compacted.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query (keyword or phrase)"
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of matching transcript entries to return",
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

实现思路：按行读取 transcript JSONL，在 content 字段中做文本匹配，返回匹配的行及其上下文。

---

## 11. 实现优先级

| 优先级 | 内容 |
|--------|------|
| **P0** | L1 大结果落盘 + Transcript 写入 |
| **P0** | L2 历史 tool_result 裁剪 |
| **P1** | Token 精确计数集成（count_tokens API） |
| **P1** | Session ID 生成与管理 |
| **P1** | System prompt 压缩状态注入 |
| **P2** | 观测埋点完善 |
| **P2** | tiktoken 本地快速预判优化 |
| **Future** | L3 旧对话裁剪 |
| **Future** | L4 全量摘要 + search_transcript 工具 |
