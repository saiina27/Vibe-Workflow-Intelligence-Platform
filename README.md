# Vibe

**An AI assistant for developers that remembers what happened in your project, and why.**

🔗 **Try it live:** https://vibe-workflow-intelligence-platform.vercel.app (create an account on the sign-up page)

---

## The problem

When you read old code, you often ask: *"Why did we build it this way?"*

The answer is scattered. The code is on GitHub, the discussion was on Slack, the thinking happened in an AI chat, and nobody wrote the decision down. Vibe brings these pieces together so you can just ask.

## What you can ask Vibe

| You ask | What Vibe does |
|---|---|
| "What changed on 5 Oct?" | Looks up your saved project history (commits and pull requests) |
| "Why did we choose Groq as the fallback provider?" | Finds the decision you recorded, with the reason and the alternatives |
| "What did the team say about the deployment on Slack?" | Searches your Slack workspace |
| "Explain how the provider cooldown works" | Finds the right file in your code, reads it, and explains it |
| "What did we discuss earlier about rate limiting?" | Searches your past Vibe chats |
| "Show the open issues in my repo" | Reads GitHub and answers in a table |
| "Summarize my uploaded PDF" | Searches your own documents |

Vibe is built to say where an answer came from, and to admit when it did not check something.

## Features

- **Chat with memory.** Remembers facts, preferences and decisions for each workspace.
- **Your documents.** Upload PDFs or text files and ask questions about them.
- **GitHub (read-only).** Commits, branches, files, pull requests, issues, releases, repository search.
- **Slack (read-only search).** Finds relevant messages and channels.
- **Developer history.** Saves your commits and pull requests so Vibe can answer "what happened on this date?" without asking GitHub every time. An Activity panel shows the same history.
- **Decision memory.** Records what was decided, why, and what else was considered. It never invents a reason.
- **Code index.** Remembers the names of functions and classes in your Python code, so Vibe can find the right file when you ask how something works.
- **Explain mode.** Explanations come in four parts: what it is, why it is this way, how it works, alternatives.
- **Tool Activity panel.** You can see which tools Vibe used for each answer.

## How it works

A React web app sends your question to a FastAPI backend, which coordinates AI models and tools.

The main components are:

- **Frontend:** React, hosted on Vercel.
- **Backend:** FastAPI, hosted on Render.
- **Database:** PostgreSQL, hosted on Neon.
- **AI providers:** Gemini and Groq.
- **Integrations:** GitHub and Slack, with read-only access.

For each question, the AI decides which tools it needs, the backend runs them, and the AI writes the answer from the results.

## Built to run on free AI plans

Vibe is designed so that a developer does not need to pay for AI API keys:

- **Two AI providers.** If one is busy or out of quota, Vibe pauses it for a while and uses the other.
- **Small prompts.** Only the instructions a question needs are sent. A simple question now needs roughly half the AI input it needed before.
- **Trimmed tool results.** Noise is removed and long lists are cut at whole items. The AI is told when something was cut.
- **Saved history.** Past activity comes from Vibe's own database, not from a new GitHub call every time.

## Safety

- GitHub access is **read-only**, and this is enforced twice: write tools are never shown to the AI, and a guard blocks them even if the AI asks for one.
- The Slack permission is search only.
- GitHub and Slack tokens are encrypted, and every connection belongs to one user.
- The code index stores only names of functions and classes, not your code.
- Commit author emails are removed before data goes to the AI model.

## Known limits

- Free AI plans have limits (Groq about 8,000 tokens per minute and 200,000 per day, Gemini's free plan about 20 requests per day), so heavy use can hit them.
- AI can still be wrong. Vibe's checks reduce mistakes but do not remove them.
- The code index covers Python files only, and when Vibe reads a file it sees roughly the first 3,000 characters.
- History is saved when you press **Sync now**. It does not update by itself.
- Vibe cannot answer questions about CI or test results, and it does not change anything on GitHub or Slack, by design.

## Roadmap

**Done:** accounts and chat, memory, document search, multi-provider AI gateway, tool calling, GitHub and Slack integrations, deployment, developer history, decision memory, code index, and a test suite of 375 automated tests (pytest).

**Next:** deeper code understanding, more security and testing work (rate limiting, protection against prompt injection, a fixed set of evaluation questions), and a demo video.

**Later, only when needed:** workflow orchestration (LangGraph) and multiple cooperating agents. These are postponed on purpose until a real multi-step workflow needs them.

## Project structure

- `backend/` — FastAPI app: AI gateway, tools, GitHub and Slack integrations, database models, tests.
- `frontend/` — React web app: chat, memory, documents, Activity panel.
- `docs/TECHNICAL.md` — detailed engineering notes, API list and local setup.

## Run it locally

See **Local Setup** in [docs/TECHNICAL.md](docs/TECHNICAL.md).

## Author

**Saina Yadav** — Backend Developer | Python Developer | AI/LLM Engineer
