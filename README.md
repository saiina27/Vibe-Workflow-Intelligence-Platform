# Vibe — AI Backend with Memory, RAG, Tool Calling & MCP

Vibe is a production-style AI backend built with FastAPI and PostgreSQL. It evolved from a persistent conversational AI into a tool-using, context-aware developer assistant with long-term memory, RAG, multi-provider LLM routing, and an MCP-standard integration layer for GitHub and Slack.

**Current milestone: Sprint 12 — MCP Integration ✅**

🔗 **Live demo:** https://vibe-workflow-intelligence-platform.vercel.app (React frontend on Vercel, FastAPI backend on Render)

## ✨ What is Vibe?

Vibe is built around one core idea: an AI assistant shouldn't just generate text — it should **remember**, **retrieve knowledge**, **use tools**, and **interact with the developer ecosystem**.

The system progressively adds:
- Persistent conversations
- Workspace-scoped memory
- Automatic memory extraction
- Semantic memory recall
- Conversation summarization
- Knowledge-base RAG
- Multi-provider LLM routing
- Native tool calling
- Tool permissions and execution logs
- MCP-based external integrations: GitHub (per-user PAT, read-only) and Slack (OAuth + PKCE)

## 🏗️ Architecture

```
                     ┌─────────────────────┐
                     │      Client/API     │
                     └──────────┬──────────┘
                                ▼
                     ┌─────────────────────┐
                     │  FastAPI REST Layer │
                     └──────────┬──────────┘
                                ▼
                     ┌─────────────────────┐
                     │    Service Layer    │
                     │ Auth/Chat/Memory/   │
                     │ Knowledge/OAuth     │
                     └──────────┬──────────┘
                                │
                ┌───────────────┴────────────────┐
                ▼                                 ▼
      ┌──────────────────┐             ┌──────────────────────┐
      │    AI Gateway     │             │      PostgreSQL       │
      │ Provider Router    │             │ Users · Workspaces    │
      │ Retry / Fallback   │             │ Chats · Messages      │
      │ Gemini / Groq      │             │ Memories · Knowledge  │
      └────────┬───────────┘             │ Tool Logs · OAuth     │
               ▼                          └───────────────────────┘
      ┌──────────────────┐
      │ Tool-Calling Engine│
      └────────┬───────────┘
               │
      ┌────────┴─────────┐
      ▼                   ▼
┌──────────────────┐   ┌───────────────────────────────┐
│  Native AI Tools  │   │           MCP Layer            │
│  MemoryTool       │   │ MCP Client · Server Manager     │
│  KnowledgeTool     │   │ Tool Discovery · Plugin Registry│
│  WebSearchTool     │   │ Permission Mgmt · OAuth          │
└──────────────────┘   └────────────────┬─────────────────┘
                                          │
                            ┌─────────────┴─────────────┐
                            ▼                             ▼
                   ┌─────────────────┐          ┌─────────────────┐
                   │   GitHub MCP     │          │    Slack MCP     │
                   │ PRs · Issues     │          │ Search · Convos  │
                   │ Commits          │          │ Team Context     │
                   └─────────────────┘          └─────────────────┘
```

**MCP design principle:** the MCP layer is provider-independent. Integration-specific behavior (GitHub, Slack) is isolated at the boundary while the core MCP components (`client`, `server_manager`, `tool_discovery`, `registry`, `permissions`) stay reusable — so new MCP servers can be added later without touching the core.

```
Vibe Core
   ↓
MCP Layer
   ├── MCP Client
   ├── MCP Server Manager
   ├── Tool Discovery
   ├── Plugin Registry
   ├── Permission Management
   └── OAuth / Integration Authentication
          ↓
External MCP Servers
   ├── GitHub
   └── Slack
```

## 🚀 Sprint Progress

### Phase 1 — Foundation + AI Memory

| Sprint | Focus | Highlights |
|---|---|---|
| 1 ✅ | Foundation | FastAPI, PostgreSQL, SQLAlchemy, Alembic, JWT auth, protected routes, current-user system |
| 2 ✅ | Chat System | Workspaces, chats, persistent messages, conversation service, Gemini-powered AI chat endpoint |
| 3 ✅ | Workspace Memory | Memory CRUD, memory types, memory repository/service, workspace-scoped persistence |
| 4 ✅ | Intent Detection | Intent classifier for `CHAT`, `MEMORY`, `QUESTION`, `TASK`, `SUMMARY`, `KNOWLEDGE` |
| 5 ✅ | Conversation Summary | Automatic summaries, context management, long-chat optimization |
| 6 ✅ | Memory Extraction | Gemini-based automatic memory extraction and classification |
| 6.5 ✅ | AI Gateway | Provider-independent gateway — Gemini + Groq, routing, retry, fallback, usage metrics, prompt caching |
| 7 ✅ | Smart Memory Recall | Memory embeddings, `pgvector` similarity search, context injection, memory ranking |
| 8 ✅ | Advanced Memory | Duplicate detection, memory expiry, relevance scoring, lifecycle management |
| 9 ✅ | Chat Intelligence | Auto-generated chat titles, topic detection, archive/restore, conversation metadata |
| 10 ✅ | RAG Knowledge System | Document upload → text extraction → chunking → embeddings → `pgvector` → semantic retrieval → LLM context |

```
Document → Text Extraction → Chunking → Embeddings → pgvector → Semantic Search → Relevant Chunks → LLM
```

### Phase 2 — Tool-Using AI

**Sprint 11 — Tool-Calling Engine ✅**

Vibe moved from a text-only AI system to one that executes real tools.

- **Core framework:** `BaseTool`, `ToolRegistry`, `ToolRouter`, `ToolExecutor` — tool metadata, schemas, execution, and result handling
- **Native tools:**
  - 🧠 `MemoryTool` — wraps the existing memory-retrieval system as an executable AI tool
  - 📚 `KnowledgeTool` — wraps the RAG / `pgvector` knowledge system
  - 🌐 `WebSearchTool` — live web information (via Tavily)
- **Function calling:** native tool calling on both Gemini and Groq, LLM-driven tool selection, argument parsing, bounded multi-iteration tool loop (max ~5 iterations) before a final answer
- **Permissions:** user-level and workspace-level allow/deny rules, checked before every execution — a request-level restriction can narrow permissions but never grant what a higher-level policy denies
- **Logging:** every call is recorded in `ToolCallLog` — tool name, parameters, result, success/failure, latency, user, workspace, timestamp
- **Design choice:** deliberately excludes toy tools (calculator, weather, UUID generator, currency, maps) in favor of tools that give the AI real context or capability

```
User → LLM → Tool Selection → Arguments → Tool Execution → Tool Result → LLM → Final Answer
```

**Sprint 12 — MCP Integration ✅**

Connects Vibe to the external developer ecosystem via the Model Context Protocol.

- **MCP Core:** MCP client, server manager, server configuration, tool discovery, dynamic MCP-tool adaptation, plugin registry with enable/disable lifecycle, MCP permission management, user/workspace-scoped MCP runtimes
- **🐙 GitHub MCP:** connects to GitHub's hosted MCP server (`https://api.githubcopilot.com/mcp/`, streamable HTTP) using a per-user Personal Access Token. **Strictly read-only**: the model only sees allowlisted read tools, chosen per request by intent (see *GitHub Read-Only Tool Groups*). Covers commits, branches, files/README, pull requests, issues, repo/code search, releases and tags.
  > *Example: "Check my repo Vibe and tell me the latest updates." (Vibe resolves the exact repo name, lists recent commits and answers in a table.)*
- **💬 Slack MCP:** connects over Streamable HTTP with **PKCE-based OAuth**, supports searching Slack and retrieving relevant conversations for developer/team context.
  > *Example: "Search Slack for the discussion about the failing deployment and summarize what the team decided."*

```
OAuth Integration → Encrypted Access Token → MCP Integration Manager → MCP Server Manager
   → MCP Client → MCP Tool Discovery → MCP Tool Adapter → Tool Registry → AI Tool-Calling Engine → LLM
```

## 🔐 OAuth & Security

**GitHub PAT (per-user)**
```
User pastes PAT in the UI → POST /oauth/github/pat → PAT validated against the GitHub API
   → Fernet-encrypted storage → Hosted GitHub MCP (Bearer token) → read-only tools
```

**Slack OAuth (with PKCE)**
```
Generate Code Verifier → Generate S256 Challenge → Persist OAuth State + Verifier
   → Slack Authorization → Callback → Validate State → Exchange Code + Verifier → Encrypted Token Storage
```

Security mechanisms in place:
- Authenticated OAuth connect endpoints
- OAuth state persistence + CSRF protection via state validation
- PKCE (S256) for the Slack MCP OAuth flow
- Fernet-encrypted storage for GitHub PATs and Slack OAuth tokens
- User-scoped integration runtimes
- Workspace/user permission checks before every tool execution
- Read-only GitHub access: allowlisted tool groups only; write tools are never exposed to the model
- GitHub write tools are blocked at execution time on every path; in the streaming chat path, any tool call outside the exposed set is also blocked

## 🐙 GitHub Read-Only Tool Groups

Sending all 45 GitHub MCP tools to the LLM wastes tokens and would expose write tools. Vibe instead picks the **read-only group(s) matching the request** (usually one), based on the user's latest message, and always adds the core tools (`search_web`, `search_knowledge`, `search_memory`).

| Intent | Tools exposed |
|---|---|
| Commits, branches, files/README, PR list, repo name lookup (default) | `get_me`, `list_commits`, `get_commit`, `list_branches`, `get_file_contents`, `list_pull_requests`, `search_repositories` |
| Issues | `get_me`, `list_issues`, `issue_read`, `search_issues`, `search_repositories` |
| Repo / code search | `get_me`, `search_repositories`, `search_code` |
| Releases / tags | `get_me`, `list_releases`, `get_latest_release`, `list_tags`, `get_release_by_tag` |
| PR detail (files changed, reviews) | `get_me`, `list_pull_requests`, `pull_request_read` |

Engineering notes:
- Read-only is enforced twice: write tools (`create_*`, `update_*`, `delete_*`, `push_*`, `merge_*`, ...) are never exposed to the model, and a guard in the executor blocks them even if a provider asks for one by name.
- Intent is detected from the latest user message only, not the system prompt or chat history. Non-GitHub questions (PDF, memory, web) get a fixed set of core tools.
- Multi-topic questions (for example issues and releases) combine groups, capped at 12 tools to fit Groq's token budget.
- When a tool result is cut to fit the token budget, the model is told it was shortened and says so instead of claiming it saw the whole file.
- Partial repo names (for example "my repo vibe") are resolved with `search_repositories` before any other call.
- If a provider asks for a tool that was not exposed, the stream ends with a clear message instead of crashing the chat.
- Groq free-tier limits: per-minute 429s are retried using the server's own wait hint, and only the last 8 messages go into the prompt.
- Answers use tables for commits/branches/issues/PRs/repos and state only what tools returned.

## 🧩 Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── routes/          # auth, users, workspaces, chats, messages, memories, knowledge, oauth, health
│   │   └── router.py
│   ├── ai/
│   │   ├── providers/       # Gemini, Groq, provider registry
│   │   ├── tools/           # BaseTool, ToolRegistry, ToolRouter, ToolExecutor + native tools
│   │   ├── gateway.py, tool_calling.py, intent_detector.py
│   │   ├── memory_extractor.py, memory_retriever.py, knowledge_retriever.py
│   │   ├── embedding_service.py, summary_generator.py, chat_title_generator.py
│   │   └── ...
│   ├── mcp/
│   │   ├── client.py, server_manager.py, registry.py
│   │   ├── tool_discovery.py, tool_adapter.py, permissions.py
│   │   ├── integration_manager.py, runtime.py
│   │   ├── slack_search_tool.py, slack_conversation_retriever.py, slack_context.py
│   │   └── oauth/            # base.py, github.py, slack.py, encryption.py
│   ├── models/                # SQLAlchemy models
│   ├── schemas/                # Pydantic request/response schemas
│   ├── repositories/            # Data-access layer
│   ├── services/                  # Business logic layer
│   ├── dependencies/               # Auth + DB dependency injection
│   ├── core/                        # Settings (config.py)
│   └── db/                           # Session/engine setup
├── alembic/                            # Database migrations
├── tests/
├── requirements.txt
└── alembic.ini
```

## 🗄️ Data Layer

PostgreSQL via SQLAlchemy ORM with Alembic migrations. Core tables: users, workspaces, chats, messages, workspace memories, memory embeddings, conversation summaries, knowledge sources, knowledge chunks, external integrations, OAuth states, and tool call logs. `pgvector` powers semantic retrieval for both memory and knowledge embeddings.

## 🔗 API Surface

| Area | Prefix | Notes |
|---|---|---|
| Health | `/` , `/ai-metrics` | Liveness + AI provider usage metrics |
| Auth | `/auth` | JWT login — `POST /auth/login` |
| Users | `/users` | Register — `POST /users/`, profile — `GET /users/me` |
| Workspaces | `/workspaces` | Create/list workspaces |
| Chats | `/workspaces/{workspace_id}/chats` | Create/list, `POST /{chat_id}/ask` (AI chat), archive/restore, filter by topic/status |
| Messages | `/chats/{chat_id}/messages` | Send + list messages |
| Memories | `/workspaces/{workspace_id}/memories` | Full CRUD |
| Knowledge | `/workspaces/{workspace_id}/knowledge` | Upload, list, delete, semantic search |
| OAuth / Integrations | `/oauth` | GitHub: `GET /github/status`, `POST /github/pat`, `POST /github/disconnect` (PAT-based). Slack: `GET /slack/connect`, `/slack/callback` |

All non-auth routes are protected via a `get_current_user` JWT dependency.

## ⚙️ Tech Stack

| Layer | Tools |
|---|---|
| Backend | Python, FastAPI, Uvicorn, Pydantic |
| Database | PostgreSQL, SQLAlchemy, Alembic, pgvector, psycopg2 |
| AI / LLM | Gemini, Groq, multi-provider AI Gateway, function/tool calling, embeddings, RAG, semantic search |
| MCP | MCP Python SDK, MCP Client, Server Manager, Tool Discovery, Tool Adapter, Plugin Registry, Permissions, GitHub MCP, Slack MCP |
| Security | JWT, OAuth 2.0 + PKCE (Slack), per-user GitHub PAT, Fernet-encrypted tokens, OAuth state/CSRF protection |
| Dev tooling | pytest, pytest-asyncio, Docker, Git/GitHub, Render (backend), Vercel (frontend) |

## 🧪 Testing

The test suite covers auth/workspace authorization, native tool permissions, MCP plugin registry, MCP permissions, MCP tool adaptation, MCP integrations, GitHub OAuth, MCP server management and tool discovery, GitHub/Slack runtimes, MCP tool-execution authorization, end-to-end MCP tool calling, multi-iteration tool loops, tool-result bounding, and MCP failure handling — **206 automated pytest test cases** across the test modules, plus a separate Sprint 12 acceptance script for real GitHub/Slack integration validation.

```bash
pytest -q
```

**Sprint 12 real-integration acceptance test** — `tests/test_mcp_acceptance.py` is a manual/async acceptance script that validates configured OAuth integrations, persisted integrations, real MCP connections, tool discovery, and real tool execution. It requires valid, connected credentials and is intentionally kept separate from the normal pytest suite.

## 🛠️ Local Setup

**1. Clone the repository**
```bash
git clone https://github.com/saiina27/Vibe-Workflow-Intelligence-Platform.git
cd Vibe-Workflow-Intelligence-Platform/backend
```

**2. Create a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure PostgreSQL** — create a database with the `pgvector` extension enabled.

**5. Configure environment variables** — create a `.env` file in `backend/`:
```env
APP_NAME=Vibe
APP_VERSION=1.0.0
DEBUG=true

HOST=0.0.0.0
PORT=8000

DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<database>

SECRET_KEY=<your-secret-key>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

GEMINI_API_KEY=<your-gemini-api-key>
GEMINI_MODEL=gemini-3.5-flash

GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=openai/gpt-oss-20b

TAVILY_API_KEY=<your-tavily-api-key>

PRIMARY_PROVIDER=gemini
FALLBACK_PROVIDER=groq

# Slack OAuth (optional). GitHub uses a per-user PAT entered in the UI.
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_REDIRECT_URI=
SLACK_MCP_URL=https://mcp.slack.com/mcp
OAUTH_ENCRYPTION_KEY=<your-encryption-key>
```
> Variable names must match `app/core/config.py` exactly (case-insensitive). Never commit real secrets, API keys, or the `.env` file.

**6. Run migrations**
```bash
alembic upgrade head
```

**7. Start the API**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Interactive API docs: `http://localhost:8000/docs`

## 🔄 How Vibe Thinks

```
User Message → Authentication → Workspace/Conversation Context → Intent + Context Processing
   → Memory Retrieval ─┐
   → Knowledge Retrieval ┤→ AI Gateway → Provider Router → Gemini / Groq → Final Response → Persistence
   → MCP / Native Tools ─┘
```

**Tool-using request:**
```
User → LLM → Tool Decision → Permission Check → Tool Execution → Tool Result → LLM → Final Answer
```

**MCP tool call:**
```
LLM → MCP Tool → Permission Layer → MCP Tool Adapter → MCP Client → External MCP Server → Tool Result → LLM
```

## 🎯 Sprint 12 Scope

**Included in V1:** MCP Client, Server Manager, Tool Discovery, Plugin Registry, Permission Management, GitHub MCP (PR/issue/commit/dev context), Slack MCP (search + conversation retrieval), GitHub PAT auth, Slack OAuth (PKCE), provider-independent MCP architecture.

**Deferred (not in V1):** Notion, Jira, Google Drive, Gmail, Calendar, Filesystem — these can be added later through the same MCP integration boundary without redesigning the core.

## 🧠 Design Principles

1. **Provider independence** — LLM providers and MCP providers sit behind stable interfaces.
2. **Real tools over toy demos** — tools are chosen for the context/action value they add, not novelty.
3. **Persistent context** — memory, summaries, knowledge, and external developer context all feed into responses.
4. **Permission-first execution** — nothing executes without a permission check first.
5. **User-scoped integrations** — external MCP runtimes are tied to the authenticated user, not one global credential.
6. **Dynamic MCP tool discovery** — tools are discovered from connected servers and adapted into Vibe's tool system, not hardcoded.
7. **Separation of concerns** — `API → Services → AI/MCP → Repositories → Database`, each layer with one job.

## 📈 Project Evolution

```
Sprint 1 (Foundation) → Sprint 2 (Chat) → Sprint 3–5 (Memory + Intent + Summaries)
   → Sprint 6–8 (Memory Extraction + AI Gateway + Semantic Recall) → Sprint 9 (Chat Intelligence)
   → Sprint 10 (RAG Knowledge System) → Sprint 11 (Tool-Calling Engine) → Sprint 12 (MCP: GitHub + Slack)
```

Vibe evolved from a basic AI chat backend into a context-aware system combining conversation + long-term memory + a knowledge base + web search + LLM tool calling + a developer-ecosystem integration layer.

## 📌 Current Status

| Area | Status | Area | Status |
|---|---|---|---|
| FastAPI backend | ✅ | Native tool calling | ✅ |
| PostgreSQL + SQLAlchemy + Alembic | ✅ | Tool permissions & execution logging | ✅ |
| JWT authentication | ✅ | MCP Client / Server Manager | ✅ |
| Workspaces & persistent chat | ✅ | MCP Tool Discovery / Plugin Registry | ✅ |
| Workspace memory & extraction | ✅ | MCP Permissions | ✅ |
| Semantic memory recall | ✅ | GitHub MCP (PAT, read-only) | ✅ |
| Conversation summaries | ✅ | Slack MCP + OAuth (PKCE) | ✅ |
| Chat intelligence (titles/topics) | ✅ | Slack search/context retrieval | ✅ |
| RAG knowledge system | ✅ | **Sprint 12 (MCP Integration)** | **✅** |
| Gemini + Groq + AI Gateway | ✅ | | |

## ⚠️ Known Limitations

- **GitHub is read-only by design.** Vibe never creates issues, PRs or commits; it says so instead of offering to.
- **No CI / checks data.** Questions like "why did my PR fail?" are not supported, because no such tool is exposed.
- **Long tool results are shortened** (3,000 characters) before going to the model, and Vibe tells the user when that happened.
- **Free-tier LLM limits.** Groq allows 8,000 tokens per minute and 200,000 per day, and Gemini sometimes returns 503, so tool-calling traffic mostly runs on Groq. Per-minute 429s are retried; daily limits are not.
- **Slack** is implemented (OAuth + PKCE, search tools) but is not connected on the live demo account, so Slack answers are not part of the demo.

## 🚧 Future Extensions

The architecture is intentionally prepared for more MCP-compatible integrations: **Notion, Jira, Google Drive, Gmail, Calendar, Filesystem.** None are part of the current V1 scope.

## 👩‍💻 Author

**Saina Yadav** — Backend Developer | Python Developer | AI/LLM Engineer
Focused on production-style backend systems, AI infrastructure, retrieval systems, tool-using agents, and MCP-based developer integrations.

## ⭐ Project Highlights

Vibe demonstrates an end-to-end backend combining **FastAPI + PostgreSQL + SQLAlchemy + pgvector + Gemini + Groq + RAG + Tool Calling + MCP + OAuth**, structured as a progressive multi-sprint backend system rather than a single isolated AI demo.

---
> `.venv/` and `uploads/` are local/runtime artifacts — keep them out of version control (`.gitignore`) and never commit real API keys or the `.env` file.