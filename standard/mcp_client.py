import os
from dotenv import load_dotenv
import asyncio
import json
from openai import OpenAI
from mcp import ClientSession,StdioServerParameters
from mcp.client.sse import sse_client
load_dotenv()
llm = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)
SSE_URL = "http://localhost:8000/sse"

def mcp_tool_to_openai(tool)->dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        },
    }
async def main():
    user_question = "帮我算一下 123 + 456 等于多少，再把那个结果反转一下告诉我。"
    print(f"[用户提问] {user_question}\n")
    async with sse_client(SSE_URL) as (read, write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            tools_result  = await session.list_tools()
            openai_tools = [mcp_tool_to_openai(t) for t in tools_result.tools]
            print(f"[发现工具] {[t['function']['name'] for t in openai_tools]}")
            messages = [{"role":"user","content":user_question}]
            response = llm.chat.completions.create(
                model = "deepseek-v4-flash",
                messages = messages,
                tools = openai_tools,

            )
            msg = response.choices[0].message

            while msg.tool_calls:
                messages.append({
                    "role":"assistant",
                    "content":msg.content or "",
                    "tool_calls":[{
                        "id":c.id,
                        "type":"function",
                        "function":{
                            "name":c.function.name,
                            "arguments":c.function.arguments,
                        },

                    }
                for c in msg.tool_calls],
                })
                for call in msg.tool_calls:
                    tool_name = call.function.name
                    tool_args = json.loads(call.function.arguments)
                    print(f"  [大模型调用工具] {tool_name}({tool_args})")
                    result = await session.call_tool(tool_name, tool_args)
                    tool_text = result.content[0].text
                    print(f"  [工具返回] {tool_text}")
                    messages.append({
                        "role":"tool",
                        "tool_call_id":call.id,
                        "content":tool_text,
                    })
                response = llm.chat.completions.create(
                    model = "deepseek-v4-flash",
                    messages = messages,
                    tools = openai_tools,
                )
                msg = response.choices[0].message
            print(f"\n[最终回答] {msg.content}")


if __name__ == "__main__":
    asyncio.run(main())