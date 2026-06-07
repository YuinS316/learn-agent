# 提取openai返回的content中的字符串数据
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