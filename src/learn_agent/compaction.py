"""Context compaction — L1 (large-result caching) and L2 (old tool_result trimming).

Integration points (see 2026-06-20-L1_L2_compaction.md §6):
- L1: called from execute_tool_use_blocks() after each tool result
- L2: called from run_one_turn() after normalize_messages(), before API call
"""

import json
import os
import random
import string
import time
from dataclasses import dataclass

from learn_agent.config.settings import settings
from learn_agent.loop_state import LoopState

CWD = os.getcwd()

# ── Session ID ────────────────────────────────────────────────

def generate_session_id() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{ts}_{rand}"


# ── Context window resolution ─────────────────────────────────

# Known model context windows (tokens). Extend as needed.
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-opus-4-8-20250224": 200_000,
    "claude-opus-4-8": 200_000,
    "claude-opus-4-5-20251101": 200_000,
    "claude-opus-4-5": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-sonnet-4-20250514": 200_000,
    "claude-sonnet-4": 200_000,
}


def resolve_context_window() -> int:
    """Return the context window size for the configured model."""
    if settings.CONTEXT_WINDOW > 0:
        return settings.CONTEXT_WINDOW

    model = settings.ANTHROPIC_MODEL
    # Try exact match first, then prefix match
    if model in _MODEL_CONTEXT_WINDOWS:
        return _MODEL_CONTEXT_WINDOWS[model]
    for prefix, window in sorted(_MODEL_CONTEXT_WINDOWS.items(), key=lambda x: -len(x[0])):
        if model.startswith(prefix):
            return window
    # Fallback
    return 200_000


# ── L1: Large tool-result caching ─────────────────────────────

def apply_l1_compaction(
    content: str,
    tool_name: str,
    tool_input: dict,
    state: LoopState,
) -> tuple[str, bool]:
    """Check if a tool result exceeds L1 threshold; if so, cache to disk.

    Returns (content, was_compacted).
    """
    if not settings.COMPACTION_ENABLED or not settings.L1_ENABLED:
        return content, False

    # Quick pre-check: skip token-count API for obviously-small results
    char_threshold = settings.L1_TOOL_RESULT_THRESHOLD_TOKENS * 4
    if len(content) <= char_threshold:
        return content, False

    # Accurate token count
    token_count = _count_single_message(content)
    if token_count <= settings.L1_TOOL_RESULT_THRESHOLD_TOKENS:
        return content, False

    # ── Cache to disk ──────────────────────────
    cache_id = f"{state.turn_count}_{tool_name}_{_short_id()}"
    cache_dir = os.path.join(CWD, settings.L1_CACHE_DIR, state.session_id)
    cache_path = os.path.join(cache_dir, f"{cache_id}.txt")

    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(content)

    # ── Build preview ──────────────────────────
    lines = content.split("\n")
    total_lines = len(lines)
    head_n = min(settings.L1_PREVIEW_HEAD_LINES, total_lines)
    tail_n = min(settings.L1_PREVIEW_TAIL_LINES, max(0, total_lines - head_n))
    omitted = total_lines - head_n - tail_n

    preview_parts = []
    if head_n > 0:
        preview_parts.append("\n".join(lines[:head_n]))
    if omitted > 0:
        preview_parts.append(f"\n... [{omitted} lines omitted] ...\n")
    if tail_n > 0:
        preview_parts.append("\n".join(lines[-tail_n:]))

    preview = "\n".join(preview_parts)

    compacted = (
        f"[Large tool result cached — L1]\n"
        f"cache_id: {cache_id}\n"
        f"file_path: {cache_path}\n"
        f"total_lines: {total_lines}\n"
        f"total_tokens: {token_count}\n"
        f"\n--- Preview (first {head_n} lines) ---\n"
        f"{preview}\n"
        f"\n[Use read_file(path=\"{cache_path}\") to read full content if needed]"
    )

    # ── Log ────────────────────────────────────
    before_tokens = token_count
    after_tokens = len(compacted) // 4  # rough estimate
    log_compaction(state, "L1", before_tokens, after_tokens, 0,
                   {"cache_id": cache_id, "tool": tool_name})

    return compacted, True


def _short_id(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


# ── L2: Historical tool_result trimming ────────────────────────

# Tools with side effects — the L2 placeholder warns against blind re-run
_SIDEEFFECT_TOOLS = {"bash", "write_file", "edit_file", "delegate_task",
                     "create_plan", "update_plan_status", "load_skill"}


def apply_l2_compaction(messages: list, state: LoopState) -> list:
    """Compact old tool_result messages when context exceeds L2 trigger ratio.

    Only replaces content — never removes messages (API pairing constraint).
    """
    if not settings.COMPACTION_ENABLED or not settings.L2_ENABLED:
        return messages

    window = resolve_context_window()
    trigger = int(window * settings.L2_TRIGGER_RATIO)
    target = int(window * settings.L2_TARGET_RATIO)

    if state.estimated_tokens <= trigger:
        return messages

    keep_n = settings.L2_KEEP_RECENT_TOOL_RESULTS

    # Collect indices of tool_result blocks (reverse order for recency tracking)
    result_indices: list[int] = []
    for i, msg in enumerate(messages):
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                result_indices.append(i)
                break  # count each message at most once

    # The most recent `keep_n` tool_result messages are kept
    protected = set(result_indices[-keep_n:]) if len(result_indices) > keep_n else set(result_indices)

    compacted_count = 0
    before_estimate = state.estimated_tokens

    for i in result_indices:
        if i in protected:
            continue

        msg = messages[i]
        content = msg.get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue

            # Already compacted by L1? Skip (preview is already short)
            if block.get("_l1_compacted"):
                continue

            # Already compacted by L2? Skip
            if block.get("_l2_compacted"):
                continue

            # Determine tool identity from preceding assistant message
            tool_name, tool_input = _find_tool_identity(messages, i)
            side_effect = tool_name in _SIDEEFFECT_TOOLS
            warning = " ⚠ Side-effect tool — do NOT re-run blindly." if side_effect else ""

            old_content = block.get("content", "")
            saved_tokens = len(old_content) // 4

            block["content"] = (
                f"[Earlier tool result compacted — L2]\n"
                f"tool: {tool_name}\n"
                f"args: {_brief_args(tool_input)}\n"
                f"Re-run if needed, or check .agents/transcripts/{state.session_id}.jsonl for full history."
                f"{warning}"
            )
            block["_l2_compacted"] = True
            compacted_count += 1

    if compacted_count > 0:
        after_estimate = max(0, before_estimate - compacted_count * 2000)  # rough
        log_compaction(state, "L2", before_estimate, after_estimate, 0,
                       {"compacted_results": compacted_count})

    return messages


def _find_tool_identity(messages: list, result_idx: int) -> tuple[str, dict]:
    """Walk backwards from the tool_result message to find its tool_use block."""
    for j in range(result_idx - 1, -1, -1):
        content = messages[j].get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block.get("name", "unknown"), block.get("input", {})
    return "unknown", {}


def _brief_args(tool_input: dict, max_len: int = 80) -> str:
    """Short argument summary for the L2 placeholder."""
    if not tool_input:
        return "(none)"
    parts = []
    for k, v in tool_input.items():
        s = str(v)
        if len(s) > 40:
            s = s[:37] + "..."
        parts.append(f"{k}={s}")
    joined = ", ".join(parts)
    return joined[:max_len]


# ── Token counting ────────────────────────────────────────────

def _count_single_message(content: str) -> int:
    """Estimate token count for a single string content.

    Uses character-based heuristic for speed; avoids a full count_tokens API call.
    Conservative: over-estimates for code, under-estimates for CJK.
    """
    # Rough heuristic: 3 chars/token for mixed content (between 4 for code
    # and ~2 for CJK). This is just for L1 pre-check — L2 uses estimated_tokens.
    return max(1, len(content) // 3)


def estimate_context_tokens(messages: list, system_prompt: str, client) -> int:
    """Use Anthropic count_tokens API for an accurate context token count."""
    try:
        # Clean internal metadata before sending to count_tokens
        clean = _strip_internal_meta(messages)
        result = client.beta.messages.count_tokens(
            model=settings.ANTHROPIC_MODEL,
            messages=clean,
            system=system_prompt,
        )
        return result.input_tokens
    except Exception:
        # Fallback to rough estimate
        total = len(system_prompt) // 3
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 3
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        total += len(str(block.get("content", block.get("text", "")))) // 3
        return total


def _strip_internal_meta(messages: list) -> list:
    """Remove internal compaction metadata before token counting / API calls."""
    cleaned = []
    for msg in messages:
        clean = {"role": msg["role"]}
        if isinstance(msg.get("content"), str):
            clean["content"] = msg["content"]
        elif isinstance(msg.get("content"), list):
            clean["content"] = [
                {k: v for k, v in block.items()
                 if not k.startswith("_")}
                for block in msg["content"]
                if isinstance(block, dict)
            ]
        else:
            clean["content"] = msg.get("content", "")
        cleaned.append(clean)
    return cleaned


# ── Compaction logging ────────────────────────────────────────

def log_compaction(state: LoopState, layer: str, before: int, after: int,
                   duration_ms: int, details: dict | None = None) -> None:
    entry = {
        "turn": state.turn_count,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "layer": layer,
        "before_tokens": before,
        "after_tokens": after,
        "saved_tokens": before - after,
        "duration_ms": duration_ms,
        "details": details or {},
    }
    state.compaction_log.append(entry)
    print(f"\033[35m[Compaction]\033[0m layer={layer} "
          f"before={before} after={after} saved={before - after}")


# ── Transcript ────────────────────────────────────────────────

def append_transcript(state: LoopState, entry: dict) -> None:
    """Append one JSON line to the session transcript file."""
    if not settings.TRANSCRIPT_ENABLED or not state.session_id:
        return
    path = os.path.join(CWD, settings.TRANSCRIPT_DIR, f"{state.session_id}.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"\033[33m[transcript] write failed: {e}\033[0m")


def transcript_turn(state: LoopState, msg: dict) -> None:
    """Record a turn's message in the transcript."""
    append_transcript(state, {
        "turn": state.turn_count,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "role": msg.get("role"),
        "content": msg.get("content"),
    })
