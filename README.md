# EchoReview

An AI-powered Code Review platform that learns your team's standards, captures institutional knowledge from historical PRs, and delivers expert-level review comments on every new pull request.

## Features

### 🔐 OAuth Integration
- One-click sign-in with **GitHub** and **GitLab**
- Secure token storage, multi-platform support

### 📥 Smart PR Collection
- Automatically imports your team's best PRs (past N days, configurable)
- Structured parsing of:
  - Full unified diffs
  - Line-level review comments with surrounding code context
  - General discussion comments
  - **Adoption tracking**: detects whether each review comment was addressed in subsequent commits

### 🧠 Team Knowledge Base
Powered by LLMs, the knowledge base is automatically built from your historical review data:

| Type | Description |
|------|-------------|
| `code_standard` | Coding conventions enforced by your team |
| `common_issue` | Recurring bugs or antipatterns found in reviews |
| `historical_dispute` | Points of debate with eventual consensus |
| `project_context` | Project-specific decisions and constraints |
| `best_practice` | Positive patterns and recommended approaches |

### 🤖 AI Code Review (Webhook-Triggered)
When a new PR is opened or updated:
1. Webhook fires → EchoReview fetches the diff
2. Relevant knowledge items are selected
3. Similar historical PRs are identified
4. LLM generates line-level review comments that:
   - Explain **why** an issue matters (not just "this is wrong")
   - Reference **historical context** from past discussions
   - Suggest **concrete fixes** with code examples
   - Link to **similar PRs** where this was previously discussed
5. Comments are posted directly to GitHub/GitLab

## Architecture

```
frontend (Next.js 15)
    ↕ REST API
backend (FastAPI + Python)
    ├── OAuth: GitHub / GitLab
    ├── PR Collector (structured diff + comment parsing)
    ├── Knowledge Extractor (LLM: GPT-4o / Claude)
    ├── Review Generator (LLM + knowledge retrieval)
    ├── Webhook Handler (auto-trigger on PR events)
    └── REST API
         ↕
PostgreSQL + pgvector (embeddings)
Redis (task queue / caching)
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- GitHub OAuth App or GitLab Application credentials
- OpenAI API key (or Anthropic)

### 1. Clone and configure

```bash
git clone https://github.com/typing233/EchoReview.git
cd EchoReview
cp .env.example .env
# Edit .env with your credentials
```

### 2. Create OAuth Apps

**GitHub**: Go to [GitHub Developer Settings](https://github.com/settings/developers) → New OAuth App
- Homepage URL: `http://localhost:3000`
- Callback URL: `http://localhost:3000/auth/callback`

**GitLab**: Go to [GitLab Profile > Applications](https://gitlab.com/-/profile/applications)
- Redirect URI: `http://localhost:3000/auth/callback`
- Scopes: `api`, `read_user`

Add the Client ID and Secret to `.env`.

### 3. Start with Docker Compose

```bash
docker-compose up -d
```

Services will start at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### 4. Local Development (without Docker)

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Usage

1. **Connect** your GitHub/GitLab account via OAuth
2. **Add repositories** you want to monitor
3. **Collect PRs** — click "Collect PRs" to import historical data (runs in background)
4. **Browse the Knowledge Base** — review extracted team standards and patterns
5. **Setup Webhook** — enable auto-review for new PRs on GitHub/GitLab
6. **Manual Review** — trigger AI review on any collected PR

## API Reference

Full interactive documentation available at `http://localhost:8000/docs`.

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/github/url` | Get GitHub OAuth URL |
| GET | `/api/auth/github/callback` | GitHub OAuth callback |
| GET | `/api/auth/gitlab/url` | Get GitLab OAuth URL |
| GET | `/api/auth/gitlab/callback` | GitLab OAuth callback |
| GET | `/api/auth/me` | Get current user |
| GET | `/api/repositories/available` | List repos from platform |
| POST | `/api/repositories` | Add repository |
| GET | `/api/repositories` | List repositories |
| POST | `/api/repositories/{id}/collect` | Trigger PR collection |
| POST | `/api/repositories/{id}/webhook` | Register webhook |
| GET | `/api/prs/{repo_id}` | List PRs |
| GET | `/api/prs/{repo_id}/{pr_number}` | Get PR details |
| POST | `/api/prs/{repo_id}/{pr_number}/review` | Manual AI review |
| GET | `/api/knowledge/{repo_id}` | List knowledge items |
| POST | `/api/webhooks/github` | GitHub webhook receiver |
| POST | `/api/webhooks/gitlab` | GitLab webhook receiver |

## Configuration

See `.env.example` for all configuration options. Key settings:

| Variable | Description |
|----------|-------------|
| `GITHUB_CLIENT_ID` | GitHub OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth app secret |
| `GITLAB_CLIENT_ID` | GitLab OAuth app client ID |
| `GITLAB_CLIENT_SECRET` | GitLab OAuth app secret |
| `LLM_PROVIDER` | `openai` or `anthropic` |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Model name (default: `gpt-4o`) |
| `WEBHOOK_SECRET` | Shared secret for webhook HMAC verification |
| `PR_COLLECTION_DAYS` | How many days back to collect PRs (default: 90) |
| `PR_MIN_REVIEW_COMMENTS` | Min review comments for "quality" PR (default: 2) |

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) — async Python web framework
- [SQLAlchemy 2](https://docs.sqlalchemy.org/en/20/) — async ORM
- [PostgreSQL](https://postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) — database + vector similarity
- [Alembic](https://alembic.sqlalchemy.org/) — database migrations
- [OpenAI](https://platform.openai.com/) / [Anthropic](https://anthropic.com/) — LLM providers
- [Redis](https://redis.io/) — background tasks / caching

**Frontend**
- [Next.js 15](https://nextjs.org/) — React framework
- [Tailwind CSS](https://tailwindcss.com/) — styling
- [Zustand](https://github.com/pmndrs/zustand) — state management
- [Lucide React](https://lucide.dev/) — icons

## License

MIT