# learn-agent

> **探索 LLM Agent 自主运行原理的极简演示项目**  
> 基于 Anthropic Messages API，模型通过工具调用自主完成多步编程任务。

**核心设计哲学：*Act, don't explain*** — 模型直接使用工具干活，而不是告诉用户它打算干什么。

---

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [架构概览](#架构概览)
- [核心模块](#核心模块)
  - [main.py — CLI 入口](#mainpy--cli-入口)
  - [agent_loop.py — 核心引擎](#agent_looppy--核心引擎)
  - [loop_state.py — 状态管理](#loop_statepy--状态管理)
  - [agent_config.py — 代理角色配置](#agent_configpy--代理角色配置)
  - [compaction.py — 上下文压缩](#compactionpy--上下文压缩)
  - [hook_system.py — 钩子系统](#hook_systempy--钩子系统)
- [工具系统](#工具系统)
- [子代理机制](#子代理机制)
- [技能系统](#技能系统)
- [计划系统](#计划系统)
- [安全性设计](#安全性设计)
- [配置参考](#配置参考)
- [测试指南](#测试指南)
- [开发指南：添加新工具](#开发指南添加新工具)
- [常见问题](#常见问题)
- [设计文档](#设计文档)

---

## 快速开始

```bash
# 1. 克隆并配置
cp .env.example .env
# 编辑 .env，填入 API 配置（参考下方环境变量说明）

# 2. 同步依赖（使用 uv）
uv sync

# 3. 运行 CLI
uv run python -m learn_agent.main

# 4. 运行测试
uv run pytest
```

### 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `ANTHROPIC_BASE_URL` | ✅ | — | API 基地址（兼容 Anthropic Messages API 格式即可） |
| `ANTHROPIC_API_KEY` | ✅ | — | API 密钥 |
| `ANTHROPIC_MODEL` | ✅ | — | 模型名称 |
| `PARENT_MAX_TURNS` | ❌ | 100 | 父代理最大轮次 |
| `PARENT_MAX_FAILURES` | ❌ | 5 | 父代理最大失败次数 |
| `SUBAGENT_MAX_TURNS` | ❌ | 20 | 子代理最大轮次 |
| `SUBAGENT_MAX_FAILURES` | ❌ | 3 | 子代理最大失败次数 |
| `MAX_PLAN_ITEMS` | ❌ | 10 | 计划项数量上限 |
| `COMPACTION_ENABLED` | ❌ | `true` | 上下文压缩总开关 |
| `L1_TOOL_RESULT_THRESHOLD_TOKENS` | ❌ | 10000 | L1 缓存触发的 token 阈值 |

完整配置项参见 [`config/settings.py`](src/learn_agent/config/settings.py)。

---

## 项目结构

```
learn-agent/
├── src/learn_agent/
│   ├── main.py                  # CLI 入口，交互式 REPL
│   ├── agent_loop.py            # ★ 核心引擎
│   ├── loop_state.py            # 会话状态 & 计划数据结构
│   ├── agent_config.py          # 代理角色配置（parent / subagent）
│   ├── skill_registry.py        # 技能发现与加载系统
│   ├── compaction.py            # 上下文压缩（L1/L2）
│   ├── hook_system.py           # 钩子系统（6 个生命周期阶段）
│   ├── config/settings.py       # Pydantic 配置管理
│   ├── tools/                   # 9 个工具
│   │   ├── register_tools.py    # 工具注册、权限过滤、处理器路由
│   │   ├── run_bash.py          # Shell 命令执行
│   │   ├── run_read.py          # 文件读取
│   │   ├── run_write.py         # 文件写入
│   │   ├── run_edit.py          # 文件编辑
│   │   ├── run_glob.py          # 文件搜索
│   │   ├── run_create_plan.py   # 创建执行计划
│   │   ├── run_update_plan_status.py  # 更新计划状态
│   │   ├── run_delegate_task.py # 委派任务给子代理
│   │   └── run_load_skill.py    # 加载技能文档
│   ├── hooks/                   # 内置钩子（预留）
│   └── utils/
│       ├── extract_text.py      # 文本提取
│       ├── normalize_messages.py # 消息规范化
│       └── safe_path.py         # 路径安全检查
├── tests/                       # 14 个测试文件
│   ├── test_agent_loop.py       # 核心循环（模拟 API）
│   ├── test_plan_system.py      # 计划系统全套测试
│   ├── test_delegate_task.py    # 委派机制测试
│   ├── test_safety_and_limits.py # 安全限制测试
│   ├── test_hook_system.py      # 钩子系统测试
│   ├── test_skill_registry.py   # 技能注册表测试
│   ├── test_load_skill.py       # 技能加载测试
│   ├── test_agent_config.py     # 代理配置测试
│   ├── test_normalize_messages.py # 消息规范化测试
│   ├── test_loop_state.py       # 状态管理测试
│   ├── test_compaction.py       # 上下文压缩测试
│   └── test_tools/*.py          # 各工具单元测试
├── docs/                        # 设计文档
│   ├── 2026-06-12-subagent.md   # 子代理设计
│   ├── 2026-06-15-skills.md     # 技能系统设计
│   ├── 2026-06-20-L1_L2_compaction.md  # 上下文压缩设计
│   └── 2026-06-21-hooks.md      # 钩子系统设计
├── .agents/skills/              # 14 个 Agent 技能（来自 obra/superpowers）
├── .agents/cache/tool_results/  # L1 缓存目录（自动生成）
├── .agents/transcripts/         # 会话转录目录（自动生成）
├── skills-lock.json             # 技能版本锁定
├── pyproject.toml               # 项目配置 & 依赖
└── .env.example                 # 环境变量模板
```

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│  main.py (CLI)                                                            │
│  启动时发现技能 → 交互 REPL → 读取输入 → 创建 LoopState                  │
│  └─ USER_PROMPT_SUBMIT hook → agent_loop()                               │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  agent_loop.py (核心引擎)                                                 │
│                                                                           │
│  while turn_count <= max_turns:                                           │
│    1. build_system(state, config)                                         │
│       → 注入 Goal + Plan Progress + 技能列表 + 压缩状态                    │
│    2. anthropic.messages.create() → LLM 响应                              │
│    3. 分离 text_blocks 和 tool_use_blocks                                 │
│    4. 有 tool_use → execute_tool_use_blocks()                             │
│       ├─ PRE_TOOL_USE hook（可拦截工具）                                  │
│       ├─ 分发到 TOOL_HANDLERS，执行权限检查                                │
│       ├─ STATE_TOOLS 额外接收 state 参数                                  │
│       ├─ L1 压缩：大结果自动落盘缓存                                      │
│       └─ POST_TOOL_USE hook（可修改结果）                                 │
│    5. 追踪失败计数，检查 max_failures                                     │
│    6. validate_plan_progress(state) → 自动修正计划违规                     │
│    7. tool_results 追加为 user message                                    │
│    8. 更新 token 估算 → 有 tool_use 继续，否则退出                        │
│                                                                           │
│  └─ STOP hook（统一退出点）                                               │
└─────────────────────┬─────────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌───────────────┐         ┌──────────────────┐
│ tools/ (9个)  │         │ utils/           │
│ bash, read,   │         │ extract_text     │
│ write, edit,  │         │ normalize_messages│
│ glob, plan,   │         │ safe_path        │
│ delegate,     │         └──────────────────┘
│ load_skill    │
└───────────────┘
```

---

## 核心模块

### main.py — CLI 入口

启动时自动发现技能文件并打印摘要，进入交互式 REPL 循环：

```python
def main():
    # 1. 启动时发现技能
    n = registry.discover()
    # 2. 输出技能摘要
    print(f"📦 Find {n} skills: ...")
    # 3. 进入交互循环
    while True:
        query = input("请输入 >> ")
        # 4. USER_PROMPT_SUBMIT hook
        # 5. 创建 LoopState，调用 agent_loop()
        # 6. 提取并输出最终文本
```

支持输入 `q` / `exit` / 空行退出。回话 ID 自动生成（时间戳 + 随机后缀），用于转录和缓存路径。

### agent_loop.py — 核心引擎

| 函数 | 职责 |
|------|------|
| `build_system(state, config)` | 构建动态 system prompt，注入目标、计划进度、技能列表和压缩状态 |
| `run_one_turn(state, config)` | 单轮交互：API 调用 → 响应解析 → 工具执行 → 状态更新 |
| `execute_tool_use_blocks(blocks, state, config)` | 遍历 tool_use，分发到对应处理器，执行权限检查、钩子拦截和 L1 压缩 |
| `validate_plan_progress(state)` | 验证计划状态顺序，自动修正违规并返回提示消息 |
| `agent_loop(state, config)` | 主循环：调用 `run_one_turn` 直到 max_turns 或 max_failures |

#### 计划进度注入示例

每次 API 调用时自动注入进 system prompt：

```
## Goal
实现用户注册功能

## Plan Progress
✅ [0] (done) 分析需求
🟡 [1] (doing) 实现用户模型
⬜ [2] (pending) 编写注册接口

Work through plans in order. Only ONE plan 'doing' at a time.
```

#### 工具执行流程（execute_tool_use_blocks）

每个工具调用的完整生命周期：

```
PRE_TOOL_USE hook（可拦截，返回 False 则阻止执行）
    │
    ▼
handler(**tool_input)  或 handler(state, **tool_input)  # STATE_TOOLS
    │
    ▼
L1 compaction（大结果 → 缓存到磁盘，替换为预览）
    │
    ▼
POST_TOOL_USE hook（可修改 result）
    │
    ▼
追加到 tool_results 列表
```

#### 失败追踪

- 工具返回结果以 `"Error:"` 开头计为失败
- `failure_count` 累计所有失败；`consecutive_failures` 记录连续失败数
- 任一失败计数超过 `max_failures` → 触发安全停止
- 成功调用后 `consecutive_failures` 重置为 0

### loop_state.py — 状态管理

```python
@dataclass
class Plan:
    content: str       # 简短名称，如 "读取现有代码"
    status: str        # "pending" | "doing" | "done"
    description: str   # 详细描述

@dataclass
class LoopState:
    messages: list                  # 对话消息列表
    turn_count: int = 1             # 已执行轮数
    transition_reason: str | None   # 本轮结束原因
    goal: str = ""                  # 当前执行目标
    plans: list[Plan] | None = None # 当前计划列表
    failure_count: int = 0          # 累计失败次数
    consecutive_failures: int = 0   # 连续失败次数
    failure_log: list[str]          # 最近失败记录
    stopped_reason: str | None      # 安全停止原因
    session_id: str = ""            # 会话 ID（用于缓存和转录）
    estimated_tokens: int = 0       # 上下文 token 估算
    compaction_log: list[dict]      # 压缩事件日志
```

关键方法：

| 方法 | 说明 |
|------|------|
| `plan_snapshot()` | 深度复制 plans，用于回滚 |
| `rollback_plans(snapshot)` | 从快照恢复 plans |
| `reset_runtime_state()` | 重置运行时状态（turn_count、plans、failures 等），**保留消息历史**，适合重试场景 |

### agent_config.py — 代理角色配置

两种预置配置：

| 属性 | PARENT_AGENT_CONFIG | SUBAGENT_CONFIG |
|------|---------------------|-----------------|
| 角色 | parent | subagent |
| 允许工具 | bash, read, write, edit, glob, 计划, 委派, 技能加载 | glob, read_file 仅只读 |
| 最大轮数 | 100（可配置） | 20（可配置） |
| 最大失败 | 5（可配置） | 3（可配置） |
| 可委派 | ✅ | ❌ |
| 上下文压缩 | L1 + L2 | L1 |

`AgentConfig` 是一个 frozen dataclass，通过 `allowed_tool_names` frozenset 实现权限白名单。

### compaction.py — 上下文压缩

两层渐进式压缩机制，防止上下文无限膨胀：

#### L1：大结果落盘缓存

- **触发时机**：工具返回后立即
- **触发条件**：单个 tool_result > 10k tokens（阈值可配）
- **处理**：完整内容写入 `.agents/cache/tool_results/{session_id}/`，消息替换为前 30 行 + 后 20 行的预览 + 文件路径
- **恢复**：模型通过 `read_file` 按路径读取完整缓存

#### L2：历史 tool_result 裁剪

- **触发时机**：下一轮请求前
- **触发条件**：总上下文 ≥ 75% context_window（比例可配）
- **处理**：保留最近 3 次 tool_result，更早的替换为占位符（含工具名 + 参数摘要）
- **安全**：有副作用的工具（bash/write/edit/delegate_task 等）标注 ⚠ 警告，避免重跑

#### 可观测性

每次压缩事件记录到 `state.compaction_log`，注入 system prompt 告知模型，完整历史保存在 `.agents/transcripts/{session_id}.jsonl`。

### hook_system.py — 钩子系统

6 个生命周期阶段，覆盖 agent 从启动到退出的完整流程：

| 阶段 | 触发位置 | 触发时机 | 典型用途 |
|------|----------|----------|---------|
| `USER_PROMPT_SUBMIT` | main.py | 用户输入 prompt 后 | 日志、prompt 预处理、敏感词过滤 |
| `PRE_TOOL_USE` | agent_loop.py | 工具 handler 执行前 | 危险命令拦截、频率限制、参数校验 |
| `POST_TOOL_USE` | agent_loop.py | 工具 handler 返回后 + L1 之后 | 结果日志、后处理、安全审计 |
| `SUBAGENT_START` | run_delegate_task.py | 子 agent 派发前 | 派发日志、任务监控 |
| `SUBAGENT_STOP` | run_delegate_task.py | 子 agent 返回后 | 结果审核、执行统计 |
| `STOP` | agent_loop.py | agent loop 退出前 | 统计摘要、资源清理、转录收尾 |

**全局生效**：父 agent 和子 agent 共享同一套 hook，通过 `ctx.config.role` 区分。

**关键特性**：
- Hook 返回 `None` → 正常继续
- Hook 返回 `HookContext` → 数据已修改，使用新数据
- PRE_TOOL_USE 返回 `False` → **拦截工具执行**，模型收到错误信息
- 支持 priority 排序（越小越先执行）
- 非 critical hook 异常 → 静默吞掉并打印日志，不影响主流程
- critical hook 异常 → 向上抛出，中断流程

---

## 工具系统

### 注册机制

`register_tools.py` 管理三个核心结构：

| 结构 | 说明 |
|------|------|
| `TOOLS` | 9 个工具的 Anthropic API 格式定义列表 |
| `TOOL_HANDLERS` | 工具名 → 处理函数映射字典 |
| `STATE_TOOLS` | 状态修改型工具集合（需额外接收 `state` 参数） |

`filter_tools(allowed)` 根据权限白名单过滤工具定义，返回 Agent 可见的工具子集。

### 工具清单

| 工具 | 文件 | 功能 | 状态型 | 安全措施 |
|------|------|------|--------|---------|
| `bash` | `run_bash.py` | Shell 命令执行 | ❌ | 危险命令黑名单、120s 超时、50K 截断 |
| `read_file` | `run_read.py` | 读取文件 | ❌ | 路径安全检测 |
| `write_file` | `run_write.py` | 写入/覆盖文件 | ❌ | 路径安全检测 |
| `edit_file` | `run_edit.py` | 替换首个匹配文本 | ❌ | 路径安全检测、存在性校验 |
| `glob` | `run_glob.py` | Glob 模式文件搜索 | ❌ | 结果逃逸过滤 |
| `create_plan` | `run_create_plan.py` | 创建执行计划 | ✅ | 参数校验（空值、数量） |
| `update_plan_status` | `run_update_plan_status.py` | 更新计划状态 | ✅ | 索引/状态合法性校验 |
| `delegate_task` | `run_delegate_task.py` | 委派任务给子代理 | ✅ | 空任务检查、隔离运行 |
| `load_skill` | `run_load_skill.py` | 加载技能文档 | ✅ | 技能名存在性校验 |

---

## 子代理机制

`delegate_task` 实现了"代理中的代理"模式——将只读任务委派给受限子代理。

### 隔离性

- **独立状态**：子代理拥有独立 `LoopState`，与父代理完全隔离
- **独立配置**：使用 `SUBAGENT_CONFIG`（更小的轮数和失败预算）
- **受限能力**：只能使用 `glob` + `read_file`，不可委派
- **共享钩子**：子代理运行期间也会触发全局 hook（PRE_TOOL_USE、POST_TOOL_USE、STOP），通过 `ctx.config.role == "subagent"` 区分

### 数据流

```
父代理调用 delegate_task(task, context, paths, format)
  │
  ├─ SUBAGENT_START hook
  ├─ 创建子代理 LoopState（空白上下文）
  ├─ agent_loop(child_state, config=SUBAGENT_CONFIG)
  │     ├─ 子代理自主调用 glob/read_file 收集信息
  │     └─ 返回证据型摘要
  ├─ SUBAGENT_STOP hook
  │
  └─ 父代理收到 findings，继续决策
```

### 子代理退出处理

如果子代理因 `max_turns` 或 `max_failures` 安全停止，父代理会收到停止原因 + 最近失败记录 + 部分结果，不会静默失败。

---

## 技能系统

将特定领域的操作指南打包为可发现、可加载的文档，模型按需获取。

### 技能目录结构

```
.agents/skills/
├── brainstorming/
│   ├── SKILL.md              # 必需：含 YAML frontmatter 的技能定义
│   └── ...
├── systematic-debugging/
│   ├── SKILL.md
│   ├── root-cause-tracing.md
│   └── find-polluter.sh
└── ...
```

当前内置 **14 个技能**，来自 [obra/superpowers](https://github.com/obra/superpowers)，通过 `skills-lock.json` 锁定版本。

### SkillRegistry

| 方法 | 时机 | 行为 |
|------|------|------|
| `discover()` | 启动时 | 扫描 `.agents/skills/*/SKILL.md`，解析 frontmatter，构建索引 |
| `build_skills_prompt()` | 每次构建 system prompt | 注入技能摘要列表 |
| `load_skill(name)` | 模型调用时 | 返回技能正文 |
| `list_names()` | 查询时 | 列出所有技能名 |

> 仅父 agent 可使用 `load_skill`，子 agent 无权限。

---

## 计划系统

让模型执行多步复杂任务的核心机制。

### 生命周期

```
1. create_plan(goal, plans)  → 创建计划，自动激活第 0 项
2. update_plan_status(N, "done")    → 完成当前步骤
3. update_plan_status(N+1, "doing") → 开始下一步
4. 全部 done → 任务完成
```

### 状态机

```
     ┌──────────┐
     │ pending  │  ← create_plan 自动激活第 0 项
     └────┬─────┘
          ▼
     ┌──────────┐
     │  doing   │  ← 一次只能有一个 doing
     └────┬─────┘
          ▼
     ┌──────────┐
     │   done   │
     └──────────┘
```

### 自动修正

`validate_plan_progress()` 自动检测以下违规并修正：

- 多个 plan 同时标记为 `doing`
- 跳过某个 plan（如 `[0] done → [2] doing`，缺少 `[1]`）
- 状态交错（如 `[0] done → [1] pending → [2] doing`）

修正后，违规信息作为 user message 返回给模型，引导模型自我修正。

---

## 消息规范化

每次 API 调用前做三层清理，确保 Anthropic API 格式严格合规：

1. **去除内部元数据** — 移除所有以 `_` 开头的字段（如 `_l1_compacted`、`_l2_compacted`）
2. **补偿孤儿 tool_use** — 为缺少 `tool_result` 的 `tool_use` 插入 `"(cancelled)"` 占位
3. **合并连续同角色消息** — 确保 user/assistant 严格交替

---

## 安全性设计

| 维度 | 措施 |
|------|------|
| 路径安全 | `safe_path()` 阻止目录逃逸（`..`、绝对路径、符号链接） |
| Bash 安全 | 危险命令黑名单（`rm -rf /`、`sudo`、`shutdown` 等）、120s 超时 |
| 工具权限 | `allowed_tool_names` 白名单 + 执行前二次检查 |
| Hook 拦截 | PRE_TOOL_USE 钩子可返回 `False` 阻止任何工具调用 |
| 输出限制 | Bash 输出 50K 截断，工具结果打印 5K 截断 |
| 失败预算 | 父代理 5 次，子代理 3 次，超限自动安全停止并给出摘要 |

---

## 配置参考

所有配置项定义在 [`config/settings.py`](src/learn_agent/config/settings.py) 中，通过 Pydantic Settings 管理。

### 基础配置

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `ANTHROPIC_BASE_URL` | `ANTHROPIC_BASE_URL` | `""` | API 基地址 |
| `ANTHROPIC_API_KEY` | `ANTHROPIC_API_KEY` | `""` | API 密钥 |
| `ANTHROPIC_MODEL` | `ANTHROPIC_MODEL` | `""` | 模型名称 |
| `MAX_PLAN_ITEMS` | `MAX_PLAN_ITEMS` | `10` | 计划项数量上限 |

### 代理限制

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `PARENT_MAX_TURNS` | `PARENT_MAX_TURNS` | `100` | 父代理最大轮次 |
| `PARENT_MAX_FAILURES` | `PARENT_MAX_FAILURES` | `5` | 父代理最大失败次数 |
| `SUBAGENT_MAX_TURNS` | `SUBAGENT_MAX_TURNS` | `20` | 子代理最大轮次 |
| `SUBAGENT_MAX_FAILURES` | `SUBAGENT_MAX_FAILURES` | `3` | 子代理最大失败次数 |

### 上下文压缩

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `COMPACTION_ENABLED` | `COMPACTION_ENABLED` | `true` | 压缩总开关 |
| `CONTEXT_WINDOW` | `CONTEXT_WINDOW` | `0` | 模型上下文窗口（0=自动检测） |
| `L1_ENABLED` | `L1_ENABLED` | `true` | L1 大结果缓存 |
| `L1_TOOL_RESULT_THRESHOLD_TOKENS` | `L1_TOOL_RESULT_THRESHOLD_TOKENS` | `10000` | 触发 L1 的 token 阈值 |
| `L1_PREVIEW_HEAD_LINES` | `L1_PREVIEW_HEAD_LINES` | `30` | 预览头部行数 |
| `L1_PREVIEW_TAIL_LINES` | `L1_PREVIEW_TAIL_LINES` | `20` | 预览尾部行数 |
| `L1_CACHE_DIR` | `L1_CACHE_DIR` | `.agents/cache/tool_results` | 缓存目录 |
| `L2_ENABLED` | `L2_ENABLED` | `true` | L2 历史裁剪 |
| `L2_TRIGGER_RATIO` | `L2_TRIGGER_RATIO` | `0.75` | L2 触发阈值（占 context_window 比例） |
| `L2_TARGET_RATIO` | `L2_TARGET_RATIO` | `0.55` | L2 压缩目标比例 |
| `L2_KEEP_RECENT_TOOL_RESULTS` | `L2_KEEP_RECENT_TOOL_RESULTS` | `3` | L2 保留的最近 tool_result 数量 |

### 转录

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| `TRANSCRIPT_ENABLED` | `TRANSCRIPT_ENABLED` | `true` | 转录总开关 |
| `TRANSCRIPT_DIR` | `TRANSCRIPT_DIR` | `.agents/transcripts` | 转录文件目录 |

---

## 测试指南

```bash
# 运行所有测试
uv run pytest

# 详细输出
uv run pytest -v

# 特定测试文件
uv run pytest tests/test_plan_system.py

# 特定测试类
uv run pytest tests/test_plan_system.py -k "TestValidatePlanProgress"

# 带覆盖率
uv run pytest --cov=src/learn_agent
```

### 测试覆盖

| 文件 | 覆盖内容 |
|------|---------|
| `test_agent_loop.py` | 核心循环：文本响应、工具调用、多轮交互、未知工具处理 |
| `test_plan_system.py` | 计划系统全套：状态计算、违规检测、system prompt 注入、快照回滚 |
| `test_delegate_task.py` | 委派机制：空任务拒绝、结果返回、超时停止、上下文传递 |
| `test_safety_and_limits.py` | 安全限制：max_turns、max_failures、权限检查、状态重置 |
| `test_hook_system.py` | 钩子系统：注册、触发顺序、拦截、异常隔离、critical 传播 |
| `test_normalize_messages.py` | 消息规范化：元数据剥离、孤儿补偿、消息合并 |
| `test_agent_config.py` | 代理配置默认值 |
| `test_skill_registry.py` / `test_load_skill.py` | 技能发现与加载 |
| `test_loop_state.py` | 状态管理：快照、回滚、重置 |
| `test_compaction.py` | 上下文压缩 |
| `test_tools/*.py` | 各工具的单元测试（使用 `tmp_path` 隔离） |

### 模拟策略

- `test_agent_loop.py` 和 `test_delegate_task.py` 使用 `unittest.mock` 模拟 Anthropic 客户端
- `test_plan_system.py` 直接测试纯函数，无需模拟
- `test_tools/*.py` 使用 `tmp_path` fixture 隔离文件系统

---

## 依赖

| 依赖 | 用途 | 版本 |
|------|------|------|
| `anthropic` | Anthropic Messages API 客户端 | >=0.109.1 |
| `pydantic-settings` | 基于 Pydantic 的配置管理 | >=2.11.0 |
| `python-dotenv` | .env 文件加载 | >=1.2.1 |
| `pytest` | 测试框架（dev） | >=8.0 |

Python >=3.12，构建系统使用 `setuptools>=64`。

---

## 开发指南：添加新工具

只需 4 步：

### 第 1 步：创建工具文件

在 `src/learn_agent/tools/` 下创建 `run_my_tool.py`：

```python
def run_my_tool(param1: str) -> str:
    try:
        return "result"
    except Exception as e:
        return f"Error: {e}"
```

如需修改 `LoopState`，添加 `state` 参数（会自动被注册为 STATE_TOOL）：

```python
def run_my_state_tool(state: LoopState, param1: str) -> str:
    state.goal = param1
    return "ok"
```

### 第 2 步：注册工具

在 `register_tools.py` 中：
1. `TOOLS` 列表添加工具定义（Anthropic API 格式）
2. `TOOL_HANDLERS` 字典添加名称 → 函数映射
3. 如是状态修改型工具，加入 `STATE_TOOLS` 集合

### 第 3 步：导出

在 `tools/__init__.py` 的 `__all__` 中导出。

### 第 4 步：添加测试

在 `tests/test_tools/` 下创建测试文件，使用 `tmp_path` fixture 隔离文件系统。

---

## 常见问题

**Q: 如何更换 LLM 后端？**

修改 `.env` 中的 `ANTHROPIC_BASE_URL` 和 `ANTHROPIC_MODEL`。后端需兼容 Anthropic Messages API 格式。

**Q: 模型不按计划顺序执行怎么办？**

`validate_plan_progress()` 会自动检测违规并修正，同时将违规信息返回给模型自我修正。

**Q: 子代理能访问哪些工具？**

仅 `glob` 和 `read_file`，不可执行 bash、不可写入文件、不可委派。

**Q: `reset_runtime_state()` 与重新创建 LoopState 有何区别？**

前者保留消息历史（对话上下文），只清空运行时状态（turn_count、plans、failures 等），适合重试场景。后者从头开始。

**Q: L1 压缩后模型怎么读取完整结果？**

直接使用 `read_file` 工具读取缓存文件路径即可，无需额外工具。

**Q: Hook 系统和 compaction 是什么关系？**

两者是独立的。Hook 系统是生命周期拦截机制，compaction 是上下文管理策略。当前 compaction 直接在 `agent_loop.py` 中内联调用，后续可考虑迁移为 POST_TOOL_USE hook 和 STOP hook 的实现。

**Q: 如何添加自定义 hook？**

```python
from learn_agent.hook_system import HookStage, HookContext, hook_registry

def my_hook(ctx: HookContext) -> HookContext | None:
    if ctx.config.role == "subagent":
        return None  # 跳过子 agent
    print(f"[{ctx.stage.value}] tool={ctx.data.get('tool_name')}")
    return None

hook_registry.register(HookStage.POST_TOOL_USE, my_hook, priority=50)
```

---

## 设计文档

- [子代理、轮次限制与失败保护设计](docs/2026-06-12-subagent.md) — delegate_task 机制、配置系统、安全停止
- [技能系统设计](docs/2026-06-15-skills.md) — SkillRegistry、SKILL.md 格式、发现与加载
- [上下文压缩设计](docs/2026-06-20-L1_L2_compaction.md) — L1/L2 两层渐进式压缩、token 计量、transcript
- [钩子系统设计](docs/2026-06-21-hooks.md) — 6 个生命周期阶段、HookContext、HookRegistry、使用示例
