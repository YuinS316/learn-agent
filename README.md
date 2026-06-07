# learn-agent

A minimal coding agent CLI that uses an LLM (OpenAI-compatible API) to autonomously solve tasks by executing shell commands.

It's a learning project exploring the fundamentals of agent loops — the model decides whether to call a tool, the tool executes, results feed back into the conversation, and the loop continues until the model is satisfied with the answer.

## Features

- **Agent Loop** — Multi-turn conversation loop where the LLM decides when to call tools and when to stop.
- **Bash Tool** — The agent can execute arbitrary shell commands in the current working directory.
- **Safety Guard** — Blocks obviously dangerous commands (`rm -rf /`, `sudo`, `shutdown`, `reboot`, `> /dev/`).
- **OpenAI-Compatible** — Works with any provider that speaks the OpenAI API (OpenAI, Azure, local models via Ollama/vLLM, etc.).
- **Conversation History** — Maintains context across turns so the agent can iteratively refine its approach.
- **macOS Chinese Input Fix** — Patches `libedit` quirks so Chinese input works correctly in the terminal on macOS.
- **Configurable** — All settings via `.env` file; choose your model, endpoint, and API key.

## Project Structure

```
learn-agent/
├── src/learn_agent/
│   ├── __init__.py
│   ├── main.py            # CLI entry point
│   ├── agent_loop.py      # Core agent loop + bash tool
│   └── config/
│       ├── __init__.py
│       └── settings.py    # Pydantic settings (reads .env)
├── pyproject.toml
├── .env.example
└── README.md
```

## Prerequisites

- Python >= 3.9
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd learn-agent

# 2. Create .env from the example
cp .env.example .env

# 3. Edit .env with your credentials
#    OPENAI_API_KEY="your-api-key"
#    OPENAI_BASE_URL="https://api.openai.com/v1"  # or your custom endpoint
#    OPENAI_MODEL="gpt-4o"                         # or any model you prefer

# 4. Sync dependencies with uv
uv sync

# 5. Run
uv run python -m learn_agent.main
```

## Usage

Once running, you'll see:

```
s01: Agent Loop (OpenAI version)
输入问题，回车发送。输入 q 退出。

s01 >>
```

Type a task and press Enter. The agent will:

1. Think about whether it needs to run a command.
2. Execute bash commands (shown in yellow).
3. Feed the output back and continue thinking.
4. Print its final response when done.

Type `q` or `exit` to quit.

### Example

```
s01 >> What files are in this directory?

$ ls -la
total 224
drwxr-xr-x  12 user  staff    384 Jun  6 00:47 .
drwxr-xr-x   3 user  staff     96 Jun  5 23:45 ..
-rw-r--r--   1 user  staff    128 Jun  6 00:31 .env
...
```

## Configuration

All configuration is set in the `.env` file:

| Variable          | Description                     | Example                              |
|-------------------|---------------------------------|--------------------------------------|
| `OPENAI_API_KEY`  | Your API key                    | `sk-...`                             |
| `OPENAI_BASE_URL` | API base URL                    | `https://api.openai.com/v1`          |
| `OPENAI_MODEL`    | Model name to use               | `gpt-4o`, `deepseek-chat`, …         |

## Dependencies

- [openai](https://pypi.org/project/openai/) — OpenAI Python SDK
- [pydantic-settings](https://pypi.org/project/pydantic-settings/) — Settings management
- [python-dotenv](https://pypi.org/project/python-dotenv/) — `.env` file loading

## License

MIT
