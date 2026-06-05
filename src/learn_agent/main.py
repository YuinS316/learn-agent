from learn_agent.agent_loop import agent_loop


def main():
    print("s01: Agent Loop (OpenAI version)")
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

        # Run the agent loop
        agent_loop(history)

        # Print the model's final text response
        last_message = history[-1]
        if last_message.get("role") == "assistant" and last_message.get("content"):
            print(last_message["content"])
        print()

if __name__ == '__main__':
    main()

