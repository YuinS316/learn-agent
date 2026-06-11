# 本文档由本程序生成，每次迭代后会重新生成一份，以验证其能力

```
提示词为: 给这个项目写一份完整的开发者文档。你需要先扫描项目结构，理解每个模块的职责，然
  后编写 README.md。如果已经有该文件，直接修改内容即可。
```

## learn-agent 开发者文档

## 项目概述

learn-agent 是一个极简的 coding agent CLI 演示项目，旨在探索 LLM Agent 的基础运行原理。它使用 **Anthropic API** 驱动一个"思考→调用工具→观察结果→继续思考"的自主循环（Agent Loop），让模型能够自主完成多步编程任务。

核心设计哲学：**Act, don't explain** —— 模型应该直接使用工具干活，而不是告诉用户它打算干什么。

## 项目结构

```
learn-agent/
├── src/
│   └── learn_agent/
│       ├── __init__.py              # 包入口
│       ├── main.py                  # CLI 入口点
│       ├── agent_loop.py            # Agent 循环核心 + 系统提示 & 计划验证
│       ├── loop_state.py            # 循环状态 & 计划数据结构
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
│       │   ├── run_create_plan.py   # 创建执行计划
│       │   └── run_update_plan_status.py  # 更新计划状态
│       └── utils/
│           ├── __init__.py
│           ├── extract_text.py      # 从消息内容中提取文本
│           ├── normalize_messages.py # 消息清理和规范化
│           └── safe_path.py         # 路径安全检查（防止目录逃逸）
├── tests/
│   ├── conftest.py                  # pytest 全局配置
│   ├── test_agent_loop.py           # Agent 循环单元测试
│   ├── test_plan_system.py          # 计划系统单元测试
│   ├── test_loop_state.py           # LoopState 测试
│   ├── test_extract_text.py         # extract_text 测试
│   ├── test_normalize_messages.py   # normalize_messages 测试
│   ├── test_safe_path.py            # safe_path 测试
│   └── test_tools/
│       ├── test_run_bash.py
│       ├── test_run_read.py
│       ├── test_run_write.py
│       ├── test_run_edit.py
│       └── test_run_glob.py
├── pyproject.toml                   # 项目配置 & 依赖
├── .env.example                     # 环境变量模板
├── .python-version                  # Python 版本 3.12
└── README.md                        # 用户文档
```

## 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│  main.py (CLI)                                               │
│  • 读取用户输入                                              │
│  • 初始化 LoopState                                          │
│  • 调用 agent_loop()                                         │
│  • 打印最终结果                                              │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│  agent_loop.py (核心循环)                                    │
│                                                              │
│  loop:                                                       │
│    1. build_system() → 动态 system prompt                     │
│    2. client.messages.create() → LLM 响应                     │
│    3. 提取 text 和 tool_use 块                                │
│    4. 如果有 tool_use → execute_tool_use_blocks()            │
│    5. validate_plan_progress() → 检查计划状态顺序              │
│    6. 结果追加到 state.messages                               │
│    7. 如果还有 tool_use → 继续循环                            │
│    8. 否则 → 退出                                            │
└──────────────┬───────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌──────────────┐ ┌──────────────┐
│ tools/       │ │ utils/       │
│ • bash       │ │ • extract    │
│ • read       │ │ • normalize  │
│ • write      │ │ • safe_path  │
│ • edit       │ └──────────────┘
│ • glob       │
│ • create_plan│
│ • update_    │
│   plan_status│
└──────────────┘
```

## 各模块职责详解

### 1. `main.py` — CLI 入口

- 提供交互式命令行界面，提示符为 `s01 >>`
- 支持输入 `q` 或 `exit` 退出
- 每次用户输入后，创建一个 `LoopState` 实例（包含消息历史）
- 调用 `agent_loop(state)` 运行完整的多轮循环
- 循环结束后，用 `extract_text()` 提取最终回复并打印

### 2. `agent_loop.py` — Agent 循环核心

这是整个项目的核心引擎，包含以下关键函数：

#### `build_system(state)`
构建动态 system prompt。如果存在 goal 和 plans，将它们格式化为易读的计划进度条注入到 system prompt 中。这是**状态注入**的关键机制——模型每次调用时都能看到当前计划的全貌。

#### `run_one_turn(state) -> bool`
执行单轮交互：
1. 调用 Anthropic API（传入 system prompt + 消息历史 + 工具定义）
2. 解析响应的 content blocks，分离 text 和 tool_use
3. 将 assistant 消息追加到 state.messages
4. 如果有 tool_use，调用 `execute_tool_use_blocks()` 执行工具
5. 执行后调用 `validate_plan_progress()` 检查计划状态一致性
6. 如果有违规，将违规消息作为额外的 tool_result 返回给模型
7. 如果有 tool_use 则返回 True（继续循环），否则返回 False（结束）

#### `agent_loop(state)`
保持调用 `run_one_turn()` 直到返回 False。

#### `execute_tool_use_blocks(tool_use_blocks, state)`
遍历所有 tool_use 块，根据 `TOOL_HANDLERS` 分发到对应的处理器函数。
- 状态修改型工具（create_plan, update_plan_status）额外传入 `state` 参数
- 普通工具只传入 `**tool_input`
- 未知工具返回错误信息

#### `_compute_correct_plans(plans)`
根据"done(s) → doing(0/1) → pending(s)"的顺序规则，计算每个计划项应该处于的正确状态。

#### `validate_plan_progress(state)`
验证计划状态顺序是否合法：
- 最多一个 "doing"
- 状态必须按 **done → doing → pending** 顺序排列
- 不允许交错（如 done → pending → doing）
- 违规时自动修正并返回错误消息（该消息会喂回给模型，让模型自我修正）

### 3. `loop_state.py` — 状态管理

使用 Python dataclass 定义核心数据结构：

#### `Plan`
- `content`: 计划项简短名称（如 "Read existing code"）
- `status`: 状态，取值 "pending" | "doing" | "done"
- `description`: 详细描述（如 "Use glob to find .py files and read key modules"）

#### `LoopState`
- `messages`: 对话消息列表（Anthropic 格式）
- `turn_count`: 已执行轮数，从 1 开始计数
- `transition_reason`: 本轮结束原因（如 "tool_result"）
- `goal`: 当前执行目标（由 create_plan 设置）
- `plans`: 当前计划列表，每个元素是 Plan 实例
- `plan_snapshot()`: 返回计划的深拷贝（用于回滚）
- `rollback_plans(snapshot)`: 从快照恢复计划状态

### 4. `config/settings.py` — 配置管理

基于 `pydantic-settings` 从 `.env` 文件读取配置：

| 配置项 | 环境变量 | 说明 |
|--------|---------|------|
| ANTHROPIC_BASE_URL | ANTHROPIC_BASE_URL | API 基地址 |
| ANTHROPIC_API_KEY | ANTHROPIC_API_KEY | API 密钥 |
| ANTHROPIC_MODEL | ANTHROPIC_MODEL | 模型名称 |
| MAX_PLAN_ITEMS | MAX_PLAN_ITEMS | 计划项最大数量（默认 10） |

### 5. 工具模块 (`tools/`)

每个工具独立一个文件，清晰分离职责。

| 工具 | 文件名 | 功能 | 是否状态修改 |
|------|--------|------|-------------|
| `bash` | `run_bash.py` | 执行 shell 命令（有安全性过滤） | 否 |
| `read_file` | `run_read.py` | 读取文件内容，支持行数限制 | 否 |
| `write_file` | `run_write.py` | 写入/覆盖文件，自动创建父目录 | 否 |
| `edit_file` | `run_edit.py` | 替换文件中的首个匹配文本 | 否 |
| `glob` | `run_glob.py` | 按 glob 模式搜索文件 | 否 |
| `create_plan` | `run_create_plan.py` | 创建执行计划（状态修改） | **是** |
| `update_plan_status` | `run_update_plan_status.py` | 更新计划项状态（状态修改） | **是** |

#### `register_tools.py` — 工具注册中心

- `TOOLS`: 工具定义列表（Anthropic Tool Use API 格式），包含 name, description, input_schema
- `TOOL_HANDLERS`: 工具名称 → 处理器函数的映射字典
- `STATE_TOOLS`: 标记需要接收 `state` 参数的工集（create_plan, update_plan_status）

### 6. 工具函数模块 (`utils/`)

#### `safe_path.py` — 路径安全
- 定义 `WORKDIR` 为当前工作目录
- `safe_path(path)`: 将相对路径解析为绝对路径，并验证路径未逃逸出工作目录
- 防止 `../../etc/passwd` 或 `/etc/passwd` 这类路径穿越攻击

#### `extract_text.py` — 文本提取
- `extract_text(content)`: 从消息内容中提取纯文本
- 支持 str 和 list[dict] 两种格式
- 只提取 `type == "text"` 的块，忽略 tool_use 等非文本块

#### `normalize_messages.py` — 消息规范化
在调用 API 前对消息列表做三层清理：
1. **去除内部元数据**：移除所有以 `_` 开头的字段（如 `_internal`, `_source`）
2. **补偿孤儿 tool_use**：如果 assistant 消息中有 tool_use 但没有对应的 tool_result，自动插入一个 "(cancelled)" 占位 result（防止 API 报错）
3. **合并连续同角色消息**：Anthropic API 要求 user/assistant 角色严格交替，合并相同角色的连续消息

## 数据流 & 生命周期

### 一次完整的 Agent 运行

```
用户输入: "帮我创建一个 Python 脚本"
  │
  ▼
main.py 创建 LoopState(messages=[user_msg])
  │
  ▼
agent_loop(state)
  │
  ├── run_one_turn(state):
  │     ├── build_system(state) → 生成 system prompt
  │     ├── API 调用 → 模型响应
  │     ├── 解析 text + tool_use
  │     ├── 模型决定: 需要先看目录结构
  │     │     └── 调用 glob("**/*.py")
  │     ├── execute_tool_use_blocks() 执行 glob
  │     ├── 结果作为 tool_result 追加到 messages
  │     └── 返回 True (继续循环)
  │
  ├── run_one_turn(state):  # 第2轮
  │     ├── 模型看到 glob 结果
  │     ├── 调用 create_plan(...) 创建计划
  │     ├── 计划被保存到 state.plans
  │     └── 返回 True
  │
  ├── run_one_turn(state):  # 第3轮
  │     ├── system prompt 中显示计划进度
  │     ├── 模型按照计划执行步骤
  │     ├── 调用 bash/write/edit 等工具
  │     ├── validate_plan_progress() 检查状态顺序
  │     └── 返回 True (还在执行中)
  │
  ├── ... (多轮循环)
  │
  └── run_one_turn(state):  # 最后一轮
        ├── 模型满意结果，只返回 text，无 tool_use
        └── 返回 False → 循环结束

main.py 提取最终文本并打印
```

### 消息格式

消息遵循 Anthropic Messages API 格式：

```python
# 用户消息
{"role": "user", "content": "你好"}

# 用户消息（含 tool_result）
{"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": "call_1", "content": "file content"},
]}

# 助手消息（混合 text 和 tool_use）
{"role": "assistant", "content": [
    {"type": "text", "text": "Let me check..."},
    {"type": "tool_use", "id": "call_1", "name": "bash",
     "input": {"command": "ls -la"}},
]}
```

## 计划系统说明

计划系统是项目的核心功能之一，让模型能够执行多步复杂任务。

### 创建计划 (`run_create_plan`)

- 只能通过工具调用创建（模型自主调用 `create_plan` 工具）
- 接收 `goal`（总体目标）和 `plans`（有序步骤列表）
- 验证：goal 非空、plans 非空、每项有 content 和 description、不超过 MAX_PLAN_ITEMS
- 创建后，第 0 项自动标记为 "doing"

### 更新计划状态 (`run_update_plan_status`)

- 通过工具调用更新指定索引的计划项状态
- 校验索引范围、状态值合法性
- 但**不校验顺序**——顺序校验由 `validate_plan_progress()` 在工具执行后统一进行

### 计划状态约束

状态必须严格遵循：
```
done(s) → doing(0 or 1) → pending(s)
```

合法示例：
- ✅ `[doing, pending, pending]` — 刚开始
- ✅ `[done, doing, pending]` — 进行中
- ✅ `[done, done, done]` — 全部完成

非法示例（会被自动修正+通知模型）：
- ❌ `[done, done, doing, pending]` — 正确，因为第三条 doing 直接在两个 done 之后
- ❌ `[done, doing, doing, pending]` — 两个 doing
- ❌ `[done, doing, done, pending]` — done 出现在 doing 之后（交错）
- ❌ `[pending, done, pending]` — 跳过 doing

### 状态回滚机制

`LoopState` 提供 `plan_snapshot()` 和 `rollback_plans()` 方法，支持在需要时回滚计划状态。

## 安全性设计

### 路径安全（`safe_path.py`）

所有文件操作工具（read, write, edit, glob）都通过 `safe_path()` 验证路径合法性：
- 使用 `Path.resolve()` 解析符号链接和相对路径
- 使用 `is_relative_to()` 确保路径未逃逸出工作目录
- 任何试图访问工作目录之外的操作都会返回错误

### Bash 安全（`run_bash.py`）

内置危险命令黑名单：
- `rm -rf /` — 防止删除根目录
- `sudo` — 防止提权
- `shutdown`, `reboot` — 防止系统操作
- `> /dev/` — 防止破坏设备文件

### API 消息规范化（`normalize_messages.py`）

自动移除以下安全隐患：
- 内部元数据字段（以 `_` 开头）
- 为孤儿 tool_use 添加占位 result，防止 API 调用失败

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
```

### 测试架构

测试使用 `pytest`，配置在 `pyproject.toml` 中。

#### `conftest.py`
- 在导入任何模块前设置测试环境变量
- 将 `src` 目录加入 `sys.path`

#### 测试覆盖

| 测试文件 | 测试内容 | 关键测试场景 |
|---------|---------|-------------|
| `test_agent_loop.py` | agent 循环核心逻辑 | 文本响应结束、工具调用继续、多轮交互、API 参数验证 |
| `test_plan_system.py` | 计划系统全套逻辑 | 状态顺序计算、违规检测与修正、system prompt 构建、计划 CRUD |
| `test_loop_state.py` | LoopState 基础功能 | 默认值、自定义值、可变性、递增 |
| `test_extract_text.py` | 文本提取工具 | 字符串、列表、混合块、空值、None |
| `test_normalize_messages.py` | 消息规范化 | 元数据剥离、孤儿补偿、消息合并、边界情况 |
| `test_safe_path.py` | 路径安全检查 | 相对路径、`..` 逃逸、绝对路径逃逸、符号链接 |
| `test_tools/*.py` | 各工具功能 | 正常执行、错误处理、边界情况、安全拦截 |

### 模拟（Mock）策略

`test_agent_loop.py` 使用 `unittest.mock` 模拟 Anthropic 客户端：
- 使用 `MagicMock` 模拟 `client.messages.create`
- 使用自定义 `FakeResponse`, `FakeTextBlock`, `FakeToolUseBlock` 模拟 API 响应
- 通过 `patch.object(agent_loop, 'client', mock_client)` 注入模拟客户端

`test_plan_system.py` 直接测试纯函数逻辑，无需模拟外部服务。

`test_tools/*.py` 使用 `tmp_path` fixture 创建临时目录，避免影响真实文件系统。

## 依赖说明

| 依赖 | 用途 | 版本要求 |
|------|------|---------|
| `anthropic` | Anthropic API 客户端 | >=0.109.1 |
| `pydantic-settings` | 基于 Pydantic 的配置管理 | >=2.11.0 |
| `python-dotenv` | .env 文件加载 | >=1.2.1 |
| `pytest` | 测试框架（dev 依赖） | >=8.0 |

## 开发流程

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd learn-agent

# 复制环境变量配置
cp .env.example .env
# 编辑 .env 填入 API 密钥

# 同步依赖（使用 uv）
uv sync
```

### 2. 添加新工具

添加一个新工具只需要 3 步：

**第 1 步：创建工具文件**

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

如果工具需要修改 `state`（如更新计划），需要在参数中接收 `state: LoopState`：
```python
from learn_agent.loop_state import LoopState

def run_my_state_tool(state: LoopState, param1: str) -> str:
    state.goal = param1
    return "ok"
```

**第 2 步：注册工具**

在 `register_tools.py` 中：
1. 在 `TOOLS` 列表中添加工具定义（name, description, input_schema）
2. 在 `TOOL_HANDLERS` 字典中添加映射
3. 如果是状态修改型工具，在 `STATE_TOOLS` 集合中添加工具名

**第 3 步：添加测试**

在 `tests/test_tools/` 目录下创建对应的测试文件。

**第 4 步：在 `tools/__init__.py` 中导出**

### 3. 代码风格

- Python 3.12+ (使用 `@dataclass` 等现代特性)
- 使用类型注解
- 使用 f-string 格式化
- 错误处理：工具函数统一返回字符串，成功返回正常结果，失败返回 `Error: ...`

### 4. 调试技巧

- 在 `agent_loop.py` 中，工具调用会以黄色输出 `> tool_name({...})`
- 工具结果会截取前 5000 字符打印
- `validate_plan_progress()` 的违规信息会作为额外 tool_result 返回给模型，可以在终端看到

## 常见问题

### Q: 模型不按计划顺序执行怎么办？
`validate_plan_progress()` 会自动检测状态顺序违规并修正，同时将违规信息返回给模型，让它自我修正。如果模型反复违规，可以考虑在 system prompt 中加强约束。

### Q: 如何更换不同的 LLM 后端？
修改 `.env` 中的 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL`。
当前代码基于 Anthropic Messages API，如要切换为 OpenAI API 格式需要修改 `agent_loop.py` 中的调用方式。

### Q: 工具执行超时怎么办？
Bash 工具默认超时 120 秒，其他文件操作工具没有设置超时。如有需要可以在各工具函数中添加超时逻辑。

### Q: 为什么消息需要规范化（normalize_messages）？
Anthropic API 对消息格式有严格要求：
1. 不能包含未知字段（如内部元数据）
2. tool_use 必须有对应的 tool_result
3. 消息角色必须严格交替（user ↔ assistant）

`normalize_messages()` 确保消息格式始终符合 API 要求。
