from learn_agent.agent_loop import agent_loop
from learn_agent.loop_state import LoopState


def extract_text(content) -> str:
    """Extract text content from message content."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts).strip()
    return ""


def main():
    print("Agent Loop (OpenAI version)")
    print("输入问题，回车发送。输入 q 退出。\n")


    history = []
    while True:
        try:
            query = input("\033[36ms01 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        # Add user message
        history.append({"role": "user", "content": query})

        state = LoopState(messages=history)

        # Run the agent loop
        agent_loop(state)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()


if __name__ == '__main__':
    main()
