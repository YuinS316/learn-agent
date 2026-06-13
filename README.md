# learn-agent

一个极简的 **Coding Agent CLI** 演示项目，探索 LLM Agent 的基础运行原理。使用 **Anthropic Messages API** 驱动"思考 → 调用工具 → 观察结果 → 继续思考"的自主循环（Agent Loop），让模型自主完成多步编程任务。

**核心设计哲学：*Act, don't explain* —— 模型直接使用工具干活，而不是告诉用户它打算干什么。**

---

## 快速开始

### 环境准备

```bash
# 1. 克隆项目
git clone <repo-url>
cd learn-agent

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入以下配置：
#   ANTHROPIC_BASE_URL="https://api.anthropic.com"
#   ANTHROPIC_API_KEY="sk-xxx"
#   ANTHROPIC_MODEL="claude-sonnet-4-20250514"

# 3. 同步依赖（使用 uv）
uv sync

# 4. 运行 CLI
uv run python -m learn_agent.main
```

### 交互演示

```
Agent Loop (Anthropic version)
输入问题，回车发送。输入 q 退出。

s01 >> 这个项目里有哪些 Python 文件？
> glob({"pattern": "**/*.py"})
src/learn_agent/__init__.py
src/learn_agent/main.py
...

项目包含以下模块：main.py（CLI 入口）、agent_loop.py（核心循环）...
```

---

## 项目结构

```
learn-agent/
├── src/
│   └── learn_agent/
│       ├── __init__.py              # 包入口
│       ├── main.py                  # CLI 入口点（交互式循环）
│       ├── agent_loop.py            # Agent 循环核心 + 系统提示 + 计划验证
│       ├── loop_state.py            # 会话状态 & 计划数据结构
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py          # Pydantic 配置管理（读取 .env）
│       ├── tools/
│       │   ├── __init__.py          # 工具注册中心
│       │   ├── register_tools.py    # 工具定义 & 处理器映射
│       │   ├── run_bash.py          # bash 命令执行
│       │   ├── run_read.py          # 文件读取
│       │   ├── run_write.py         # 文件写入
│       │   ├── run_edit.py          # 文件编辑（文本替换）
│       │   ├── run_glob.py          # 文件搜索（glob 模式）
│       │   ├── run_create_plan.py   # 创建结构化执行计划
│       │   ├── run_update_plan_status.py  # 更新计划项状态
│       │   └── run_delegate_task.py # 委派只读任务给子代理
│       └── utils/
│           ├── __init__.py
│           ├── extract_text.py      # 从消息内容中提取纯文本
│           ├── normalize_messages.py # 消息清理与规范化
│           └── safe_path.py         # 路径安全检查（防止目录逃逸）
├── tests/
│   ├── conftest.py                  # pytest 全局配置
│   ├── test_agent_loop.py           # Agent 循环单元测试
│   ├── test_agent_config.py         # AgentConfig 测试
│   ├── test_plan_system.py          # 计划系统全套测试
│   ├── test_loop_state.py           # LoopState 基础功能测试
│   ├── test_delegate_task.py        # 委派任务机制测试
│   ├── test_extract_text.py         # extract_text 工具测试
│   ├── test_normalize_messages.py   # 消息规范化测试
│   ├── test_safe_path.py            # 路径安全测试
│   ├── test_safety_and_limits.py    # 安全限制综合测试
│   └── test_tools/
│       ├── test_run_bash.py
│       ├── test_run_read.py
│       ├── test_run_write.py
│       ├── test_run_edit.py
│       └── test_run_glob.py
├── docs/
│   └── 2026-06-12-subagent.md       # 子代理机制设计文档
├── .agents/skills/                   # Agent 技能库（实验性）
├── pyproject.toml                   # 项目配置 & 依赖声明
├── .env.example                     # 环境变量模板
├── .python-version                  # Python 版本（3.12）
└── README.md                        # 本文档
```

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│  main.py (CLI)                                                      │
│  • 读取用户输入                                                     │
│  • 初始化 LoopState(messages=[...])                                 │
│  • 调用 agent_loop(state)                                           │
│  • 用 extract_text() 提取最终回答并打印                              │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  agent_loop.py (核心引擎)                                            │
│                                                                     │
│  while turn_count <= max_turns:                                     │
│    1. build_system(state, config)  → 动态 system prompt             │
│       - 注入 Goal + Plan Progress（计划进度条）                       │
│    2. client.messages.create(...)  → 获取 LLM 响应                   │
│    3. 分离 text_blocks 和 tool_use_blocks                           │
│    4. 如果有 tool_use → execute_tool_use_blocks()                   │
│       - 根据 TOOL_HANDLERS 分发到各工具处理器                         │
│       - 状态修改型工具（create_plan/update_plan_status/delegate_task）│
│         额外接收 state 参数                                           │
│    5. 追踪失败计数（max_failures 检查）                               │
│    6. validate_plan_progress(state)  → 计划状态顺序校验              │
│    7. 将 tool_results 作为 user 消息追加                             │
│    8. turn_count++ → 继续循环                                       │
│    9. 无 tool_use → 退出循环                                        │
└──────────────────┬──────────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
┌───────────────┐   ┌───────────────────┐
│ tools/        │   │ utils/            │
│               │   │                   │
│ bash          │   │ extract_text      │
│ read_file     │   │ normalize_messages│
│ write_file    │   │ safe_path         │
│ edit_file     │   └───────────────────┘
│ glob          │
│ create_plan   │
│ update_plan_  │
│   status      │
│ delegate_task │
└───────────────┘
```

---

## 核心模块详解

### 1. `agent_loop.py` — Agent 循环核心

这是整个引擎，包含以下关键函数：

#### `build_system(state, config) -> str`

构建动态 system prompt。如果 state 中存在 `goal` 和 `plans`，将它们格式化为易读的计划进度条注入到 prompt 中。

```
## Goal
实现用户注册功能

## Plan Progress
✅ [0] (done) 分析需求: 阅读现有代码结构
🟡 [1] (doing) 实现用户模型: 创建 User 数据模型
⬜ [2] (pending) 编写注册接口: 实现 POST /register 端点

Work through plans in order. Only ONE plan 'doing' at a time.
```

这是**状态注入**的关键机制——模型每次调用都能看到当前计划的完整视图。子代理（subagent）不会注入计划信息，只有父代理会。

#### `run_one_turn(state, config) -> bool`

单轮交互的核心逻辑：

1. **调用 API**：传入 system prompt + 消息历史 + 工具定义
2. **解析响应**：分离 text_blocks 和 tool_use_blocks
3. **存储消息**：将 assistant 消息追加到 state.messages
4. **执行工具**：如果有 tool_use，调用 `execute_tool_use_blocks()`
5. **失败追踪**：检测工具错误，更新 failure_count / consecutive_failures
6. **安全停止**：检查 failure_count >= max_failures
7. **计划验证**：父代理模式下调用 `validate_plan_progress()`
8. **返回**：有 tool_use → True（继续），否则 → False（结束）

#### `execute_tool_use_blocks(blocks, state, config) -> list[dict]`

遍历所有 tool_use 块，根据 `TOOL_HANDLERS` 分发：

- 查找处理器 → 权限检查 → 执行 → 收集结果
- 状态修改型工具（在 `STATE_TOOLS` 集合中）额外接收 `state` 参数
- 未知工具返回 `Error: unknown tool '{name}'`
- 无权限工具返回 `Error: tool '{name}' is not allowed for {role}`

#### `validate_plan_progress(state) -> str | None`

验证计划状态顺序是否合法，**自动修正违规并返回提示消息**（消息会喂回给模型，让模型自我修正）。

状态约束规则：
```
done(s) → doing(0 or 1) → pending(s)
```

合法示例：
| 状态序列 | 说明 |
|---------|------|
| `[doing, pending, pending]` | 刚开始执行 |
| `[done, doing, pending]` | 正常进行中 |
| `[done, done, done]` | 全部完成 |

非法示例（自动修正）：
| 状态序列 | 问题 | 修正后 |
|---------|------|--------|
| `[done, doing, doing, pending]` | 两个 doing | `[done, doing, pending, pending]` |
| `[done, doing, done, pending]` | 交错 | `[done, doing, pending, pending]` |
| `[pending, done, pending]` | 跳过 doing | `[pending, pending, pending]` |

#### `append_safety_stop_message(state, reason)`

在安全停止时追加一条 assistant 消息，包含停止原因和最近的失败日志。

### 2. `loop_state.py` — 状态管理

使用 Python `@dataclass` 定义核心数据结构。

#### `Plan`

```python
@dataclass
class Plan:
    content: str       # 简短名称，如 "Read existing code"
    status: str        # "pending" | "doing" | "done"
    description: str   # 详细描述，如 "Use glob to find .py files and read key modules"
```

#### `LoopState`

```python
@dataclass
class LoopState:
    messages: list                  # 对话消息列表（Anthropic 格式）
    turn_count: int = 1             # 已执行轮数
    transition_reason: str | None = None  # 本轮结束原因
    goal: str = ""                  # 当前执行目标（由 create_plan 设置）
    plans: list[Plan] | None = None  # 当前计划列表
    failure_count: int = 0          # 累计失败次数
    consecutive_failures: int = 0   # 连续失败次数
    failure_log: list[str]          # 最近失败记录
    stopped_reason: str | None = None  # 停止原因
```

关键方法：

| 方法 | 功能 |
|------|------|
| `plan_snapshot()` | 返回计划的深拷贝（用于回滚） |
| `rollback_plans(snapshot)` | 从快照恢复计划状态 |
| `reset_runtime_state()` | 重置运行时状态（保留 messages），用于重试 |

### 3. `agent_config.py` — 代理配置

定义两种角色代理的配置：

#### `AgentConfig`

```python
@dataclass(frozen=True)
class AgentConfig:
    name: str                       # "parent" | "subagent"
    role: str                       # "parent" | "subagent"
    max_turns: int                  # 最大对话轮数
    max_failures: int               # 最大允许失败次数
    allowed_tool_names: frozenset   # 允许使用的工具集
    can_delegate: bool = False      # 是否允许委派任务
    system_prompt: str = ""         # 系统提示
```

#### 两种配置对比

| 属性 | `PARENT_AGENT_CONFIG` | `SUBAGENT_CONFIG` |
|------|----------------------|-------------------|
| name | `"parent"` | `"subagent"` |
| max_turns | 20 (可配置) | 6 (可配置) |
| max_failures | 5 (可配置) | 3 (可配置) |
| allowed_tools | bash, read, write, edit, glob, create_plan, update_plan_status, delegate_task | glob, read_file |
| can_delegate | 是 | 否 |
| system_prompt | 完整编程助手提示 | 只读研究助手提示 |

### 4. `config/settings.py` — 配置管理

基于 `pydantic-settings` 从 `.env` 文件读取配置：

```python
class Settings(BaseSettings):
    ANTHROPIC_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = ""
    MAX_PLAN_ITEMS: int = 10
    PARENT_MAX_TURNS: int = 20
    PARENT_MAX_FAILURES: int = 5
    SUBAGENT_MAX_TURNS: int = 6
    SUBAGENT_MAX_FAILURES: int = 3
```

`model_validator` 确保 ANTHROPIC_API_KEY、ANTHROPIC_BASE_URL、ANTHROPIC_MODEL 三个配置项在启动时必须提供。

---

## 工具系统

### 工具注册 (`register_tools.py`)

工具系统围绕三个核心数据结构组织：

#### `TOOLS` — 工具定义列表

遵循 Anthropic Tool Use API 格式，每个工具包含 `name`、`description`、`input_schema`。

#### `TOOL_HANDLERS` — 处理函数映射

```python
TOOL_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
    "create_plan": run_create_plan,
    "update_plan_status": run_update_plan_status,
    "delegate_task": run_delegate_task,
}
```

#### `STATE_TOOLS` — 状态修改工具集合

```python
STATE_TOOLS = {"create_plan", "update_plan_status", "delegate_task"}
```

这些工具的处理器会额外接收 `state` 参数，允许它们修改 LoopState 的内容。

#### `filter_tools(allowed)`

根据 `AgentConfig.allowed_tool_names` 过滤工具定义，实现权限控制。

### 工具清单

| 工具名 | 文件 | 功能 | 状态修改型 | 安全措施 |
|--------|------|------|-----------|---------|
| `bash` | `run_bash.py` | 执行 shell 命令 | 否 | 危险命令黑名单、120s 超时、输出截断 50000 字符 |
| `read_file` | `run_read.py` | 读取文件，支持行数限制 | 否 | 路径安全检测 |
| `write_file` | `run_write.py` | 写入/覆盖文件，自动创建父目录 | 否 | 路径安全检测 |
| `edit_file` | `run_edit.py` | 替换文件中的首个匹配文本 | 否 | 路径安全检测、文本存在性检查 |
| `glob` | `run_glob.py` | 按 glob 模式搜索文件 | 否 | 路径安全检测（过滤逃逸结果） |
| `create_plan` | `run_create_plan.py` | 创建结构化执行计划 | 是 | 参数校验（空值、数量限制） |
| `update_plan_status` | `run_update_plan_status.py` | 更新计划项状态 | 是 | 索引范围校验、状态合法性校验 |
| `delegate_task` | `run_delegate_task.py` | 委派只读任务给子代理 | 是 | 空任务检查、子代理隔离运行 |

### 各工具实现要点

#### `run_bash`

```python
def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    # 黑名单过滤 → subprocess.run() → 输出截断 50000 字符
```

- 使用 `subprocess.run()` 在 `CWD` 下执行
- 超时时间 120 秒
- 输出超过 50000 字符截断

#### `run_read` / `run_write` / `run_edit`

- 统一使用 `safe_path()` 进行路径安全检查
- `run_write` 自动创建父目录
- `run_edit` 检查旧文本是否存在，只替换第一个匹配

#### `run_glob`

```python
def run_glob(pattern: str) -> str:
    import glob as _g
    # 使用 root_dir=WORKDIR 限制搜索范围
    # 额外过滤确保结果不逃逸工作目录
```

#### `run_create_plan`

- 接收 `goal`（字符串）和 `plans`（列表）
- 验证规则：goal 非空、plans 非空、每项有 content 和 description、不超过 MAX_PLAN_ITEMS
- 创建后第 0 项自动标记为 "doing"
- 替换已存在的计划（如有）
- 在控制台打印格式化的计划概览

#### `run_update_plan_status`

- 校验 `plan_index` 范围（0 ≤ index < len(plans)）
- 校验 `status` 必须是 `pending` / `doing` / `done` 之一
- 在控制台打印状态变更信息

#### `run_delegate_task`

```python
def run_delegate_task(state, task, context="", relevant_paths=None, output_format=""):
    # 1. 构建子代理的初始 user message（包含 task, context, paths, format）
    # 2. 创建子 LoopState(messages=[user_message])
    # 3. 使用 SUBAGENT_CONFIG 运行 agent_loop(child_state)
    # 4. 提取子代理的最终回答
```

---

## 子代理（Subagent）机制

`delegate_task` 工具实现了"代理中的代理"模式：

### 用途

将**只读的信息收集任务**委派给一个受限的子代理，父代理可以同时处理更复杂的工作。

### 隔离性

- **独立状态**：子代理拥有独立的 `LoopState`，与父代理完全隔离
- **独立配置**：使用 `SUBAGENT_CONFIG`（更小的 max_turns 和 max_failures）
- **受限能力**：子代理只能使用 `glob` 和 `read_file` 两个工具
- **不可委派**：子代理的 `can_delegate = False`

### 数据流

```
父代理调用 delegate_task(task, context, paths, format)
  │
  ├── 创建子代理 LoopState
  │     └── messages = [{role: "user", content: "You are a read-only...\nTask:...\nContext:..."}]
  │
  ├── agent_loop(child_state, config=SUBAGENT_CONFIG)
  │     ├── 子代理调用 glob/read_file 收集信息
  │     ├── 最多 6 轮
  │     └── 返回最终文本结果
  │
  └── 父代理接收子代理的发现结果
```

---

## 消息规范化 (`normalize_messages.py`)

在调用 API 前对消息列表做三层清理：

### 1. 去除内部元数据

移除消息块中以 `_` 开头的字段（如 `_internal`、`_source`），防止 API 拒绝请求。

### 2. 补偿孤儿 tool_use

如果 assistant 消息中有 `tool_use` 但没有对应的 `tool_result`，自动插入一个 `"(cancelled)"` 占位 result。这防止因某些失败路径导致 tool_use 缺少对应 result 而触发 API 错误。

### 3. 合并连续同角色消息

Anthropic Messages API 要求 user/assistant 角色严格交替。如果因程序逻辑产生了两个连续的 user 消息或 assistant 消息，将其 content 数组拼接合并。

```python
# 合并前
[{"role": "user", "content": "hello"}, {"role": "user", "content": "world"}]

# 合并后
[{"role": "user", "content": [{"type": "text", "text": "hello"}, {"type": "text", "text": "world"}]}]
```

---

## 安全性设计

### 路径安全 (`safe_path.py`)

所有文件操作工具（read, write, edit, glob）都通过 `safe_path()` 验证路径合法性：

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
```

- 使用 `Path.resolve()` 解析符号链接和相对路径
- 使用 `is_relative_to()` 确保路径未逃逸出工作目录
- 任何试图访问工作目录之外的操作（如 `../../etc/passwd` 或 `/etc/passwd`）都会返回 `Error`

### Bash 安全

内置危险命令黑名单：

```python
dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
```

- 删除根目录、提权操作、系统操作、设备文件操作被直接拦截
- 所有命令在子进程中执行，无法影响父进程环境
- 自动超时 120 秒

### 工具权限控制

- `AgentConfig.allowed_tool_names` 白名单机制
- `filter_tools()` 只返回允许的工具定义给 API
- `execute_tool_use_blocks()` 在执行前二次检查权限

### 输出限制

- Bash 输出截断 50000 字符
- 工具结果打印截断 5000 字符

### 失败预算

- 父代理：max_failures=5（可配置）
- 子代理：max_failures=3（可配置）
- 超过后自动安全停止

---

## 计划系统

计划系统是项目核心功能，让模型能够执行多步复杂任务。

### 生命周期

```
1. 模型调用 create_plan(goal, plans)
   → run_create_plan() 验证并创建计划
   → plans[0].status = "doing"（自动激活第一个步骤）
   → 计划写入 state.goal 和 state.plans
   → system prompt 下次自动注入计划进度

2. 模型按照计划顺序工作
   → 第 N 步完成后调用 update_plan_status(N, "done")
   → 第 N+1 步开始时调用 update_plan_status(N+1, "doing")
   → validate_plan_progress() 在每次工具执行后校验顺序

3. 全部完成
   → 最后一步标记为 "done"
   → 所有计划项状态为 "done"
```

### 状态机

```
     ┌──────────┐
     │ pending  │
     └────┬─────┘
          │ create_plan 自动激活
          ▼
     ┌──────────┐
     │  doing   │
     └────┬─────┘
          │ update_plan_status(N, "done")
          ▼
     ┌──────────┐
     │   done   │
     └──────────┘
```

- 只能向前推进（pending → doing → done）
- 一次只有一个 "doing"
- validate_plan_progress 自动修正违规

---

## 依赖说明

| 依赖 | 用途 | 版本要求 |
|------|------|---------|
| `anthropic` | Anthropic Messages API 客户端 | >=0.109.1 |
| `pydantic-settings` | 基于 Pydantic 的配置管理 | >=2.11.0 |
| `python-dotenv` | .env 文件加载 | >=1.2.1 |
| `pytest` | 测试框架（dev 依赖） | >=8.0 |

构建系统使用 `setuptools>=64`。

---

## 测试指南

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_plan_system.py

# 运行特定测试类
uv run pytest tests/test_plan_system.py -k "TestValidatePlanProgress"

# 显示详细输出
uv run pytest -v

# 跳过网络相关测试（纯本地测试）
uv run pytest -m "not network"
```

### 测试架构

测试使用 `pytest`，配置在 `pyproject.toml` 中。

#### `conftest.py`

在导入任何模块前设置测试环境变量，避免 `Settings()` 初始化时因缺少配置抛出异常：

```python
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "test-model")
os.environ.setdefault("ANTHROPIC_BASE_URL", "https://test.api.com")
```

同时将 `src` 目录加入 `sys.path`，确保测试能直接导入 `learn_agent` 包。

#### 模拟策略

`test_agent_loop.py` 和 `test_delegate_task.py` 使用 `unittest.mock` 模拟 Anthropic 客户端：

```python
# 模拟响应块
class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text

class FakeToolUseBlock:
    def __init__(self, id, name, input_data):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input_data

class FakeResponse:
    def __init__(self, content_blocks):
        self.content = content_blocks

# 注入模拟客户端
mock_client = MagicMock()
mock_client.messages.create.return_value = FakeResponse([FakeTextBlock("done")])
with patch.object(agent_loop, 'client', mock_client):
    agent_loop.agent_loop(state)
```

`test_plan_system.py` 直接测试纯函数逻辑（`_compute_correct_plans`、`validate_plan_progress`、`build_system`、`run_create_plan`、`run_update_plan_status`），无需模拟外部服务。

`test_tools/*.py` 使用 `tmp_path` fixture 创建临时目录，避免影响真实文件系统。

### 测试覆盖

| 测试文件 | 测试内容 | 关键测试场景 |
|---------|---------|-------------|
| `test_agent_loop.py` | Agent 循环核心 | 文本响应结束、工具调用继续、多轮交互、API 参数验证、多工具执行、未知工具处理 |
| `test_plan_system.py` | 计划系统全套逻辑 | 状态顺序计算(7种场景)、违规检测与自动修正、system prompt 构建、计划 CRUD、LoopState 快照与回滚 |
| `test_loop_state.py` | LoopState 基础功能 | 默认值、自定义值、可变性引用、turn_count 递增 |
| `test_delegate_task.py` | 委派任务机制 | 空任务拒绝、子代理返回结果、子代理超时停止、上下文传递、默认值回退 |
| `test_extract_text.py` | 文本提取工具 | 字符串、列表、混合块、空值、None |
| `test_normalize_messages.py` | 消息规范化 | 元数据剥离、孤儿补偿、消息合并、边界情况 |
| `test_safe_path.py` | 路径安全检查 | 相对路径、`..` 逃逸、绝对路径逃逸、符号链接 |
| `test_agent_config.py` | 代理配置 | 两种配置的默认值、角色属性 |
| `test_safety_and_limits.py` | 安全与限制 | max_turns 停止、max_failures 停止、连续失败重置、安全停止消息、子代理权限限制、计划验证作用域隔离、LoopState reset |

---

## 开发指南

### 添加新工具

只需 4 步：

#### 第 1 步：创建工具文件

`src/learn_agent/tools/run_my_tool.py`:

```python
from learn_agent.utils.safe_path import safe_path

def run_my_tool(param1: str, param2: int) -> str:
    try:
        # 工具逻辑
        return "result"
    except Exception as e:
        return f"Error: {e}"
```

如果工具需要修改 `LoopState`，需要在参数中接收 `state: LoopState`：

```python
from learn_agent.loop_state import LoopState

def run_my_state_tool(state: LoopState, param1: str) -> str:
    state.goal = param1
    return "ok"
```

#### 第 2 步：注册工具

在 `register_tools.py` 中：

1. 导入工具函数
2. 在 `TOOLS` 列表中添加工具定义（name, description, input_schema）
3. 在 `TOOL_HANDLERS` 字典中添加映射
4. 如果是状态修改型工具，在 `STATE_TOOLS` 集合中添加工具名

#### 第 3 步：导出

在 `tools/__init__.py` 的 `__all__` 中添加新函数。

#### 第 4 步：添加测试

在 `tests/test_tools/` 目录下创建对应的测试文件，包含：
- 正常执行测试
- 错误处理测试（非法参数、边界情况）
- 安全拦截测试（路径逃逸等）

### 添加新的配置项

1. 在 `settings.py` 的 `Settings` 类中添加字段
2. 在 `.env.example` 中添加说明
3. 确保 `conftest.py` 中设置了测试用的默认值

### 代码风格指南

- **Python 3.12+**：使用 `@dataclass`、`frozenset` 等现代特性
- **类型注解**：所有函数参数和返回值必须标注类型
- **错误处理**：工具函数统一返回字符串，成功返回正常结果，失败返回 `Error: ...`
- **导入风格**：使用相对导入（`from learn_agent.xxx import yyy`）
- **日志**：使用 `print()` 输出彩色日志，工具调用用黄色 `\033[33m`，计划用青色 `\033[36m`，状态更新用品红 `\033[35m`

### 调试技巧

- 工具调用会以黄色输出：`> tool_name({...})`
- 工具结果打印前 5000 字符
- `validate_plan_progress()` 的违规信息会作为额外 tool_result 返回给模型，可在终端看到
- 子代理运行时完全独立，其输出不会干扰父代理的对话流

---

## 配置参考

### `.env` 文件

```ini
ANTHROPIC_BASE_URL="https://api.anthropic.com"
ANTHROPIC_API_KEY="sk-ant-xxx"
ANTHROPIC_MODEL="claude-sonnet-4-20250514"
```

### 所有可配置环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ANTHROPIC_BASE_URL` | `""` (必填) | API 基地址 |
| `ANTHROPIC_API_KEY` | `""` (必填) | API 密钥 |
| `ANTHROPIC_MODEL` | `""` (必填) | 模型名称 |
| `MAX_PLAN_ITEMS` | `10` | 计划项最大数量 |
| `PARENT_MAX_TURNS` | `20` | 父代理最大对话轮数 |
| `PARENT_MAX_FAILURES` | `5` | 父代理最大允许失败次数 |
| `SUBAGENT_MAX_TURNS` | `6` | 子代理最大对话轮数 |
| `SUBAGENT_MAX_FAILURES` | `3` | 子代理最大允许失败次数 |

---

## 常见问题

### Q: 模型不按计划顺序执行怎么办？

`validate_plan_progress()` 会自动检测状态顺序违规并修正，同时将违规信息返回给模型，让它自我修正。如果模型反复违规，可以考虑在 `PARENT_SYSTEM_PROMPT` 中加强约束描述。

### Q: 如何更换不同的 LLM 后端？

修改 `.env` 中的 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL`。例如切换到 DeepSeek：

```ini
ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
ANTHROPIC_MODEL="deepseek-chat"
```

注意：后端需要兼容 Anthropic Messages API 格式。

### Q: 工具执行超时怎么办？

Bash 工具默认超时 120 秒，其他文件操作工具没有设置超时。如有需要可以在各工具函数中添加超时逻辑。

### Q: 为什么消息需要规范化（normalize_messages）？

Anthropic Messages API 对消息格式有严格约束：
1. 不能包含未知字段（如内部元数据字段以 `_` 开头）
2. `tool_use` 必须有对应的 `tool_result`（否则 API 报错）
3. 消息角色必须严格交替（user ↔ assistant）

### Q: `reset_runtime_state()` 和重新创建 LoopState 有什么区别？

`reset_runtime_state()` 保留 `messages`（对话历史），只清空运行时状态（turn_count、goal、plans、failure 相关字段）。这在重试场景中有用——可以复用同一对话上下文重新开始任务。

### Q: 子代理能访问哪些工具？

子代理只能使用 `glob` 和 `read_file` 两个工具，不能执行 bash、不能写入文件、不能委派其他子代理。这是通过 `SUBAGENT_CONFIG.allowed_tool_names` 强制限制的。
