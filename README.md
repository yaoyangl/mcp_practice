# MCP 实践项目：DeepSeek API + SSE 传输

用 Python 从零搭建 MCP Server 和 MCP Client/Host，以 DeepSeek API（`deepseek-v4-flash`）作为 LLM 大脑，
通过 **SSE（Server-Sent Events）传输**连接 Server 与 Client。包含标准版（仅工具）和完整版（工具 + 资源 + 提示词）两个版本。

## 目录

- [一、MCP 是什么](#一mcp-是什么)
- [二、三个角色](#二三个角色)
- [三、三大能力原语](#三三大能力原语)
- [四、SSE 传输 vs stdio 传输](#四sse-传输-vs-stdio-传输)
- [五、架构与数据流](#五架构与数据流)
- [六、代码讲解](#六代码讲解)
- [七、运行指南](#七运行指南)
- [八、依赖](#八依赖)
- [九、注意事项](#九注意事项)

---

## 一、MCP 是什么

MCP（Model Context Protocol）是 Anthropic 提出的开放协议，用于让大模型应用以标准化方式连接外部数据源和工具。

核心解决的问题是"工具集成的 N×M 困局"：假设有 N 个大模型应用、M 个外部工具，没标准时每个应用要为每个工具写一套对接代码，共 N×M 套。MCP 把"工具怎么描述、怎么发现、怎么调用"统一成一套协议，Server 只要遵循协议暴露能力，任何 Host 都能即插即用，N×M 变成 N+M。

类比：MCP 之于 AI 工具集成，就像 USB-C 之于硬件接口。

## 二、三个角色

| 角色 | 职责 | 本项目对应 |
|------|------|-----------|
| **Server** | 把"能力"以标准化方式暴露出去 | `mcp_server.py`，用 FastMCP 注册工具/资源/提示词 |
| **Client** | 连接 Server，发现并调用能力 | `mcp_client.py` 里的 `ClientSession`，通过 SSE 连接 |
| **Host** | 宿主应用，内含 LLM + Client，编排整条链路 | `mcp_client.py` 本身，调用 DeepSeek API 当 LLM 大脑 |

Host 通过 Client 连接 Server，Server 暴露能力，Host 里的 LLM 决定何时用这些能力。本项目里 Host 和 Client 合并在 `mcp_client.py` 一个文件中。

## 三、三大能力原语

MCP Server 可暴露三种"能力原语"，区别的核心在于**控制权归谁**：

| 原语 | 谁主动 | 适合做什么 | 本项目示例 |
|------|--------|-----------|-----------|
| **Tool** 工具 | LLM 自己决定 | 执行动作、计算、查询 | `add` / `string_reverse` / `word_stats` |
| **Resource** 资源 | 应用主动读取 | 暴露只读数据、背景知识 | `knowledge://{topic}` |
| **Prompt** 提示词 | 用户主动选择 | 固化工作流、最佳实践 | `summarize` / `translate` |

Tool 的控制权在 LLM——大模型在推理中自己判断"要不要调这个工具"。Resource 的控制权在应用——Host 主动读取、注入上下文。Prompt 的控制权在用户——从模板菜单选一个、填参数、生成提示词。

标准版只演示 Tool，完整版三个全用。

## 四、SSE 传输 vs stdio 传输

MCP 支持多种传输方式，本项目用的是 **SSE（Server-Sent Events）**：

| | SSE 传输（本项目） | stdio 传输 |
|---|---|---|
| **通信方式** | HTTP 长连接，Server 是一个 Web 服务 | 标准输入输出，Server 是子进程 |
| **Server 启动** | 独立运行，监听 `localhost:8000` | 被 Client 自动拉起 |
| **Client 连接** | `sse_client("http://localhost:8000/sse")` | `stdio_client(server_params)` |
| **适用场景** | 远程/多 Client 共享一个 Server | 本地单机，最简单 |
| **运行步骤** | 先启动 Server，再运行 Client | 只运行 Client 即可 |

SSE 模式下，Server 是一个独立运行的 Web 服务（FastMCP 内部用 uvicorn 启动），Client 通过 HTTP 连接。这意味着你可以先启动 Server，然后用多个 Client 连接同一个 Server——这在实际部署中更灵活。

## 五、架构与数据流

### 整体架构

```
                    ┌─────────────────────────────────┐
                    │  Host (mcp_client.py)            │
                    │                                  │
                    │  ┌──────────┐    ┌───────────┐  │
                    │  │ DeepSeek │    │ MCP Client │  │
                    │  │   API    │◄──►│(ClientSess)│  │
                    │  │ LLM 大脑 │    └─────┬─────┘  │
                    │  └──────────┘          │        │
                    └────────────────────────┼────────┘
                                             │
                                  SSE (HTTP, localhost:8000/sse)
                                             │
                    ┌────────────────────────▼────────┐
                    │  Server (mcp_server.py)          │
                    │                                  │
                    │  🔧 Tools: add / reverse / stats │
                    │  📄 Resources: knowledge://{topic}│
                    │  💬 Prompts: summarize / translate│
                    └──────────────────────────────────┘
```

### 一次工具调用的数据流

以标准版为例，用户问"帮我算 123 + 456，再把结果反转"：

1. **连接**：Client 通过 `sse_client(SSE_URL)` 连接到 Server 的 SSE 端点，`session.initialize()` 握手。
2. **发现工具**：`session.list_tools()` 拿到 Server 暴露的全部工具。
3. **格式转换**：`mcp_tool_to_openai()` 把 MCP 工具转成 DeepSeek/OpenAI 的 function calling 格式（MCP 的 `inputSchema` 和 OpenAI 的 `parameters` 都是 JSON Schema，直接搬运）。
4. **首次调用 LLM**：把用户问题 + 工具列表发给 DeepSeek。
5. **LLM 决策**：DeepSeek 判断"需要调 add"，返回 `tool_call: add(a=123, b=456)`。
6. **MCP 执行**：Host 通过 `session.call_tool("add", {"a":123,"b":456})` 让 Client 向 Server 发起调用，Server 执行返回 `579`。
7. **结果拼回**：工具结果以 `role="tool"` 追加到对话。
8. **再次调用 LLM**：DeepSeek 拿到 `579`，判断"还需要反转"，返回 `tool_call: string_reverse(text="579")`。
9. **循环**：执行 `string_reverse` 得到 `975`，拼回对话，再调 LLM。这次不再返回 tool_call，循环结束。
10. **最终回答**：DeepSeek 的 `msg.content` 就是自然语言回答。

`mcp_client.py` 里的 `while msg.tool_calls:` 循环就是第 5-9 步——大模型可能一次返回多个 tool_call，也可能调完一轮还要再调，循环直到不再需要工具。

## 六、代码讲解

### standard/mcp_server.py — 标准版 Server

用 `FastMCP("math-string-tools")` 创建 Server 实例，用 `@mcp.tool()` 装饰器注册 3 个工具：

- `add(a, b)` — 整数加法
- `string_reverse(text)` — 字符串反转
- `word_stats(text)` — 统计字符数、单词数、行数

FastMCP 自动从函数签名（类型注解）生成 JSON Schema，从 docstring 生成工具描述。最后 `mcp.run(transport="sse")` 以 SSE 方式启动，Server 变成一个监听 `localhost:8000` 的 Web 服务。

### standard/mcp_client.py — 标准版 Client/Host

用 `load_dotenv()` 从 `.env` 加载 `DEEPSEEK_API_KEY`，创建 `OpenAI` 客户端指向 DeepSeek。通过 `sse_client("http://localhost:8000/sse")` 连接 Server，发现工具后进入"调 LLM → 有 tool_call 就通过 MCP 执行 → 结果拼回 → 再调 LLM"的循环。单轮执行一个预设问题。

### full/mcp_server.py — 完整版 Server

在标准版 3 个工具基础上，多了两类原语：

- **Resource**：`@mcp.resource("knowledge://{topic}")` 注册，URI 里 `{topic}` 是模板参数。Client 读 `knowledge://mcp-intro` 时 FastMCP 自动提取参数。资源适合暴露只读数据。
- **Prompt**：`@mcp.prompt()` 注册，`summarize(text)` 和 `translate(text, target_lang)` 返回组装好的提示词文本。

### full/mcp_client.py — 完整版 Client/Host

相比标准版多了四个能力：多轮对话（`while True` 循环）、资源注入（启动时 `read_resource` 读知识库注入上下文）、提示词模板（输入 `prompt` 命令调用模板）、错误处理（工具出错回传 LLM 而非崩溃）。工具调用循环抽成了 `chat_with_tools()` 函数。

## 七、运行指南

### 前置准备

确保 `.env` 文件（在 `standard/` 和 `full/` 各有一个）中配置了 DeepSeek API Key：

```
DEEPSEEK_API_KEY=sk-你的key
```

### 运行标准版

SSE 模式需要**先启动 Server，再运行 Client**，两个终端：

终端 1 — 启动 Server：
```bash
cd standard
python mcp_server.py
```
Server 会启动并监听 `localhost:8000`。

终端 2 — 运行 Client：
```bash
cd standard
python mcp_client.py
```
Client 连接 Server，自动执行预设问题"帮我算 123+456 再反转"，观察工具调用闭环。

### 运行完整版

同样两个终端：

终端 1：
```bash
cd full
python mcp_server.py
```

终端 2：
```bash
cd full
python mcp_client.py
```

交互命令：直接输入问题和助手多轮对话；输入 `prompt` 使用提示词模板（summarize / translate）；输入 `quit` 退出。

### 验证 Server 是否正常

Server 启动后，可在浏览器访问 `http://localhost:8000` 确认服务在运行。

## 八、依赖

本项目未包含 `requirements.txt`，需要的依赖如下：

```
mcp>=1.0
openai>=1.0
python-dotenv>=1.0
```

安装：
```bash
pip install mcp openai python-dotenv
```

## 九、注意事项

### 完整版 Client 资源读取属性

`full/mcp_client.py` 第 110 行用的是 `knowledge.content[0].text`，而 MCP SDK 的 `ReadResourceResult` 属性名是 `contents`（复数）。如果运行时此处报 `AttributeError`，把 `content` 改成 `contents` 即可。

### SSE 端口占用

Server 默认监听 `8000` 端口。如果该端口被占用，Server 会启动失败。关闭占用端口的进程，或修改 `mcp_server.py` 中的端口配置后重试。

### Windows 中文显示

如果控制台中文乱码，运行前设置：
```bash
set PYTHONIOENCODING=utf-8
```

---

## 项目结构

```
mcp_practice/
├── standard/             标准版（仅 Tool）
│   ├── .env                DeepSeek API Key
│   ├── mcp_server.py       3 个工具，SSE 传输
│   └── mcp_client.py       DeepSeek Host + 单轮工具调用
├── full/                 完整版（Tool + Resource + Prompt）
│   ├── .env                DeepSeek API Key
│   ├── mcp_server.py       工具 + 资源 + 提示词，SSE 传输
│   └── mcp_client.py       多轮对话 + 资源注入 + 模板 + 错误处理
└── .git/                 Git 仓库（remote: github.com/yaoyangl/mcp_practice）
```

## 技术栈

- **MCP Python SDK**（`mcp`）：FastMCP 高层 API，SSE 传输
- **OpenAI Python SDK**（`openai`）：调用 DeepSeek API（兼容 OpenAI 接口）
- **DeepSeek API**：模型 `deepseek-v4-flash`，支持 function calling
- **python-dotenv**：从 `.env` 文件加载环境变量
- **传输方式**：SSE（Server-Sent Events），HTTP 长连接
