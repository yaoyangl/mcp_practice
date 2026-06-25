from mcp.server.fastmcp import FastMCP
mcp = FastMCP("full-llm-toolkit")

@mcp.tool()
def add(a:int, b:int)->int:
    """两个数相加，返回它们的和。当用户问加法时使用这个工具"""
    return a+b

@mcp.tool()
def string_reverse(text:str)->str:
    """把输入的字符串反转后返回。当用户要求翻转/倒叙一段文字时使用"""
    return text[::-1]

@mcp.tool()
def word_stats(text:str)->str:
    """统计一段文字的字符数、单词书和行数。当用户问文本统计信息时使用"""
    char_count = len(text)
    word_count = len(text.split())
    line_cont = len(text.splitlines())
    return f"字符数为：{char_count},单词数为:{word_count}，行数为:{line_cont}"

KNOWLEDGE_BASE = {
    "mcp-intro": (
        "MCP（Model Context Protocol）是 Anthropic 提出的开放协议，"
        "用于让大模型应用以标准化方式连接外部数据源和工具，"
        "解决每个工具都要单独集成的'N×M'问题。"
    ),
    "deepseek-intro": (
        "DeepSeek 是一家中国 AI 公司，提供高性能大模型 API。"
        "其接口兼容 OpenAI 格式，支持 function calling，"
        "在国内访问稳定、性价比高。"
    ),
}

@mcp.resource("knowledge://{topic}")
def get_knowledge(topic:str)->str:
    """根据主题名读取知识库条目。可用主题：mcp-intro、deepseek-intro"""
    return KNOWLEDGE_BASE.get(topic,f"未找到{topic}")

@mcp.prompt()
def summarize(text: str) -> str:
    """生成一个'请总结以下文本核心要点'的提示词模板。"""
    return (
        "请用中文简洁地总结下面这段内容的核心要点（不超过 3 条），"
        "每条用一句话概括：\n\n"
        f"{text}"
    )


@mcp.prompt()
def translate(text: str, target_lang: str = "英文") -> str:
    """生成一个翻译提示词模板，默认翻译成英文。"""
    return f"请把下面这段内容翻译成{target_lang}，只输出译文：\n\n{text}"

if __name__ == "__main__":
    mcp.run(transport="sse")