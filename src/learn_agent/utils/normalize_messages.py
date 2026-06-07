import json
import uuid


def normalize_messages(messages: list) -> list:
    """将内部消息列表规范化为 OpenAI API 可接受的格式。

    处理以下问题：
    1. 移除内部元数据字段
    2. 补全缺失的 tool 响应（通过 tool_call_id）
    3. 合并连续同角色消息（user/assistant/tool 不能连续相同角色）
    4. 确保消息交替规则：user/assistant/tool 的正确顺序
    """
    normalized = []

    # Step 1: 剥离内部字段，转换为 OpenAI 格式
    for msg in messages:
        role = msg.get("role")
        if role not in ("system", "user", "assistant", "tool"):
            continue  # 跳过未知角色

        clean = {"role": role}

        # 处理 content 字段
        content = msg.get("content")
        if content is not None:
            if isinstance(content, str):
                clean["content"] = content
            elif isinstance(content, list):
                # 清洗 content 数组中的每个 block
                cleaned_blocks = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    # 只保留 OpenAI 允许的字段
                    block_type = block.get("type")
                    if block_type == "text":
                        cleaned_blocks.append({
                            "type": "text",
                            "text": block.get("text", "")
                        })
                    elif block_type == "image_url":
                        cleaned_blocks.append({
                            "type": "image_url",
                            "image_url": block.get("image_url", {})
                        })
                    elif block_type == "tool_use":
                        # OpenAI 使用 tool_calls，不是 content 中的 tool_use
                        # 这里转换为 tool_calls 格式，稍后处理
                        if "tool_calls" not in clean:
                            clean["tool_calls"] = []
                        clean["tool_calls"].append({
                            "id": block.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": json.dumps(block.get("input", {}), ensure_ascii=False)
                            }
                        })
                    elif block_type == "tool_result":
                        # OpenAI 使用单独的 tool 角色消息
                        # 这里收集到列表，防止多条 tool_result 互相覆盖
                        if "_pending_tool_results" not in clean:
                            clean["_pending_tool_results"] = []
                        clean["_pending_tool_results"].append({
                            "tool_call_id": block.get("tool_use_id"),
                            "content": block.get("content", "")
                        })
                    else:
                        # 其他类型，保留基本字段
                        cleaned_block = {"type": block_type}
                        for k, v in block.items():
                            if k not in ("_internal", "_source", "_timestamp", "type"):
                                cleaned_block[k] = v
                        cleaned_blocks.append(cleaned_block)

                if cleaned_blocks:
                    clean["content"] = cleaned_blocks
            else:
                clean["content"] = str(content)
        else:
            clean["content"] = None

        # 处理 tool_calls（来自 assistant 消息）
        if msg.get("tool_calls"):
            if "tool_calls" not in clean:
                clean["tool_calls"] = []
            for tc in msg["tool_calls"]:
                if isinstance(tc, dict):
                    clean["tool_calls"].append({
                        "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name"),
                            "arguments": tc.get("function", {}).get("arguments", "{}")
                        }
                    })
                else:
                    # 处理对象形式的 tool_call
                    clean["tool_calls"].append({
                        "id": getattr(tc, "id", f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": getattr(tc.function, "name", ""),
                            "arguments": getattr(tc.function, "arguments", "{}")
                        }
                    })

        # 处理 tool 角色的消息（OpenAI 格式）
        if role == "tool":
            clean["tool_call_id"] = msg.get("tool_call_id")
            if not clean.get("content"):
                clean["content"] = msg.get("content", "")

        normalized.append(clean)

    # Step 2: 转换待处理的 tool_result 为独立的 tool 消息
    final_messages = []
    for msg in normalized:
        # 检查是否有待处理的 tool_results
        if "_pending_tool_results" in msg:
            tool_results = msg.pop("_pending_tool_results")
            # 先添加原消息（不含 tool_results）
            final_messages.append(msg)
            # 再依次添加 tool 消息
            for tr in tool_results:
                final_messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": tr["content"]
                })
        else:
            final_messages.append(msg)

    # Step 3: 补全缺失的 tool 响应
    # 收集所有已有的 tool 响应 ID
    existing_tool_results = set()
    for msg in final_messages:
        if msg.get("role") == "tool" and msg.get("tool_call_id"):
            existing_tool_results.add(msg["tool_call_id"])

    # 查找缺失的 tool_call 响应，插入占位 tool 消息
    i = 0
    while i < len(final_messages):
        msg = final_messages[i]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id")
                if tc_id and tc_id not in existing_tool_results:
                    # 检查后面是否已经有对应的 tool 消息
                    has_response = False
                    for j in range(i + 1, len(final_messages)):
                        if (final_messages[j].get("role") == "tool"
                                and final_messages[j].get("tool_call_id") == tc_id):
                            has_response = True
                            break

                    if not has_response:
                        # 插入占位 tool 消息
                        final_messages.insert(i + 1, {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": "(cancelled - no response)"
                        })
                        existing_tool_results.add(tc_id)
                        i += 1  # 跳过刚插入的消息
        i += 1

    # Step 4: 合并连续同角色消息（OpenAI 不允许连续相同角色）
    merged = []
    for msg in final_messages:
        if not merged:
            merged.append(msg)
            continue

        last = merged[-1]

        # 检查是否可以合并
        if msg["role"] == last["role"] and msg["role"] in ("user", "assistant"):
            # 合并 content
            if last.get("content") and msg.get("content"):
                # 转换为统一格式
                last_content = last["content"]
                msg_content = msg["content"]

                if isinstance(last_content, str) and isinstance(msg_content, str):
                    # 两个都是字符串，直接拼接
                    last["content"] = last_content + "\n" + msg_content
                else:
                    # 转换为列表格式合并
                    if isinstance(last_content, str):
                        last_content = [{"type": "text", "text": last_content}]
                    elif not isinstance(last_content, list):
                        last_content = []

                    if isinstance(msg_content, str):
                        msg_content = [{"type": "text", "text": msg_content}]
                    elif not isinstance(msg_content, list):
                        msg_content = []

                    last["content"] = last_content + msg_content

                # 合并 tool_calls
                if last.get("tool_calls") and msg.get("tool_calls"):
                    last["tool_calls"].extend(msg["tool_calls"])
            elif msg.get("content") and not last.get("content"):
                last["content"] = msg["content"]
                last["tool_calls"] = msg.get("tool_calls", last.get("tool_calls"))
        else:
            merged.append(msg)

    # Step 5: 确保第一条消息不是 assistant 或 tool
    if merged and merged[0]["role"] in ("assistant", "tool"):
        # OpenAI 要求第一条消息必须是 system 或 user
        merged.insert(0, {
            "role": "user",
            "content": "[Conversation start]"
        })

    # Step 6: 清理空 content 和 None 值
    for msg in merged:
        if msg.get("content") is None and not msg.get("tool_calls") and msg.get("role") != "tool":
            msg["content"] = ""
        if msg.get("tool_calls") == []:
            msg.pop("tool_calls", None)

    return merged