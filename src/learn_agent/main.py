from learn_agent.agent_loop import agent_loop
from learn_agent.loop_state import LoopState
from learn_agent.utils.extract_text import extract_text
from learn_agent.skill_registry import registry
from learn_agent.compaction import generate_session_id
from learn_agent.hook_system import HookContext, HookStage, hook_registry
from learn_agent.agent_config import PARENT_AGENT_CONFIG


def main():
    # Discover skills on startup
    n = registry.discover()
    if n > 0:
        list = registry.list_names()
        names = "\n".join(list[0: 3])
        if len(list) > 3:
            names += "\n..."
        print(f"\033[1;36m📦 Find {n} skills: \n"
              f"{names}"
              f"\033[0m\n"
              )

    print("Agent Loop (Anthropic version)")
    print("输入问题，回车发送。输入 q 退出。\n")


    session_id = generate_session_id()
    print(f"Session: {session_id}")

    history = []
    while True:
        try:
            query = input("\033[36m请输入 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        # Add user message
        history.append({"role": "user", "content": query})

        state = LoopState(messages=history, session_id=session_id)

        # ── USER_PROMPT_SUBMIT hook ────────────────────
        prompt_ctx = HookContext(
            stage=HookStage.USER_PROMPT_SUBMIT,
            state=state,
            config=PARENT_AGENT_CONFIG,
            data={"prompt": query},
        )
        prompt_result = hook_registry.fire(HookStage.USER_PROMPT_SUBMIT, prompt_ctx)
        if isinstance(prompt_result, HookContext):
            # Hook may have modified the prompt (e.g. rewriting)
            actual_prompt = prompt_result.data.get("prompt", query)
            if actual_prompt != query:
                # Update the user message in history with the modified prompt
                history[-1]["content"] = actual_prompt
                state.messages[-1]["content"] = actual_prompt

        # Run the agent loop
        agent_loop(state)

        final_text = extract_text(history[-1]["content"])
        if final_text:
            print(final_text)
        print()


if __name__ == '__main__':
    main()
