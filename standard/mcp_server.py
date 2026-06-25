from mcp.server.fastmcp import FastMCP
mcp = FastMCP("math-string-tools")


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

if __name__ == "__main__":
    mcp.run(transport="sse")