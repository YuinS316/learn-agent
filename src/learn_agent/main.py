from learn_agent.agent_loop import agent_loop
from learn_agent.loop_state import LoopState
from learn_agent.utils.extract_text import extract_text
from learn_agent.compaction import generate_session_id
from learn_agent.hook_system import HookContext, HookStage, hook_registry
from learn_agent.agent_config import PARENT_AGENT_CONFIG


def main():
    # ── Register built-in hooks ────────────────────────
    from learn_agent.hooks.compaction import register_compaction_hooks
    from learn_agent.hooks.skills import register_skills_hook

    register_compaction_hooks()
    register_skills_hook()

    # ── AGENT_STARTUP hook (fires once) ────────────────
    startup_ctx = HookContext(
        stage=HookStage.AGENT_STARTUP,
        state=LoopState(messages=[]),
        config=PARENT_AGENT_CONFIG,
        data={},
    )
    hook_registry.fire(HookStage.AGENT_STARTUP, startup_ctx)

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
            actual_prompt = prompt_result.data.get("prompt", query)
            if actual_prompt != query:
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
