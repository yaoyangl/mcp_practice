from click import prompt
from dotenv import load_dotenv
import asyncio
import json
import os
from openai import OpenAI
from mcp import ClientSession
from mcp.client.sse import sse_client

load_dotenv()

llm = OpenAI( api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
SSE_URL = "http://localhost:8000/sse"

def mcp_tool_to_openai(tool)->dict:
    return {
        "type":"function",
        "function":{
            "name":tool.name,
            "description":tool.description or "",
            "parameters":tool.inputSchema,
        },
    }
async def chat_with_tools(session,openai_tools,messages):
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
            "tool_calls":[
                {
                    "id":c.id,
                    "type":"function",
                    "function":{
                        "name":c.function.name,
                        "arguments":c.function.arguments,
                    },
                }
                for c in msg.tool_calls
            ],
        })
        for call in msg.tool_calls:
            tool_name = call.function.name
            tool_args = json.loads(call.function.arguments)
            print(f"  [大模型调用工具] {tool_name}({tool_args})")
            try:
                result = await session.call_tool(tool_name,tool_args)
                tool_text = result.content[0].text
            except Exception as e:
                tool_text = f"工具执行出错：{e}"
                print(f"  [工具出错] {e}")

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
    return msg.content or ""

async def main():
    async with sse_client(SSE_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 工具列表
            tool_result = await session.list_tools()
            openai_tools = [mcp_tool_to_openai(t) for t in tool_result.tools]
            print(f"[发现工具] {[t['function']['name'] for t in openai_tools]}")

            # 静态资源
            try:
                res_res = await session.list_resources()
                static_uris = [str(r.uri) for r in res_res.resources]
                if static_uris:
                    print(f"[资源 static]   {static_uris}")
            except Exception:
                pass

            # 资源模板
            try:
                tmpl_res = await session.list_resource_templates()
                tmpl_uris = [str(t.uriTemplate) for t in tmpl_res.resourceTemplates]
                print(f"[资源 templates] {tmpl_uris}")
            except Exception:
                print("[资源 resources] （本 server 未暴露资源）")

            # 提示词
            try:
                prompts_res = await session.list_prompts()
                print(f"[提示词 prompts] {[p.name for p in prompts_res.prompts]}")
            except Exception:
                print("[提示词 prompts] （本 server 未暴露提示词）")

            # ===== 资源注入 —— 移到外面 =====
            system_content = "你是一个智能助手，可以调用工具帮助用户。"
            try:
                knowledge = await session.read_resource("knowledge://mcp-intro")
                kb_text = knowledge.content[0].text
                system_content += f"\n\n[背景知识] {kb_text}"
                print(f"\n[已注入背景知识] {kb_text[:50]}...")
            except Exception:
                print("\n[提示] 未读取到资源，跳过背景知识注入。")

            messages = [{"role": "user", "content": system_content}]
            print("\n多轮对话已启动。直接输入问题；输入 prompt 用提示词模板；输入 quit 退出。\n")

            # ===== 多轮对话循环 —— 也在外面 =====
            while True:
                try:
                    user_input = input("你:").strip()
                except (EOFError, KeyboardInterrupt):
                    print("再见")
                    break
                if not user_input:
                    continue
                if user_input.lower() == "quit":
                    print("再见")
                    break

                # 提示词模板分支
                if user_input.lower() == "prompt":
                    name = input("  用哪个模板？(summarize/translate): ").strip()
                    text = input("  要处理的文本: ").strip()
                    args = {"text": text}
                    if name == "translate":
                        lang = input("  目标语言（默认英文）: ").strip()
                        if lang:
                            args["target_lang"] = lang
                    try:
                        prompt_result = await session.get_prompt(name, args)
                        rendered = prompt_result.messages[0].content.text
                        print(f"  [模板生成] {rendered[:80]}...")
                        user_input = rendered
                    except Exception as e:
                        print(f"  [模板出错] {e}")
                        continue

                messages.append({"role": "user", "content": user_input})
                try:
                    reply = await chat_with_tools(session, openai_tools, messages)
                    messages.append({"role": "assistant", "content": reply})  # 注意：这里应该用 assistant 角色
                    print(f"助手: {reply}\n")
                except Exception as e:
                    messages.pop()
                    print(f"[调用出错] {e}\n")

if __name__ == "__main__":
    asyncio.run(main())


