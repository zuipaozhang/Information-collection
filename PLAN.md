# AI 信息聚合推送系统 — 完整方案

---

## 一、项目背景与目标

搭建一个自动化的 AI 信息聚合推送系统。核心目标有两个：

1. **技术敏感度**：保持对 AI 最新技术、模型、工具的敏感度，不错过重要变化
2. **提效工具发现**：找到能直接使用的工具，避免自己重复搭建

用户痛点：AI 工具变化极快，每天冒出大量新东西（新 MCP server、新 Claude Code 技能、新 Agent 框架版本、Claude Code 自身更新），靠人工刷 Twitter/公众号效率太低。需要一个 **筛选 → 策展 → 推送** 的自动化管道。

---

## 二、信息追踪范围（十大维度）

### 核心维度 — 可直接使用的工具（高优先级）

| 维度 | content_type | 关注什么 | 拿到后做什么 | 排序权重 |
|------|-------------|---------|-------------|---------|
| 🔌 MCP 服务器 | `mcp_server` | 新 server 发布、trending、分类 | **直接 `claude mcp add` 安装使用** | +1 分 |
| 🧩 Claude Code 技能/插件 | `claude_skill` | 新 skill 和 plugin 上架 | **`/plugin install` 直接使用** | +1 分 |
| ⌨️ AI 编程工具 | `coding_tool` | Claude Code / Cursor / Copilot 更新 | **直接影响你的开发效率** | +1 分 |

### 扩展维度 — 技术选型参考（中优先级）

| 维度 | content_type | 关注什么 | 拿到后做什么 |
|------|-------------|---------|-------------|
| 🤖 Agent 框架 | `agent_framework` | LangGraph/CrewAI/MAF/OpenAI SDK 版本更新 | **评估是否升级或迁移** |
| 🛠️ AI 开发工具 | `dev_tool` | AI IDE/低代码/向量库/部署工具更新 | **替换或升级现有工具链** |
| 🧠 模型发布 | `model_release` | 新模型/能力变化/价格调整 | **切换 API endpoint** |
| 📦 开源模型 | `open_source_model` | Qwen/Llama/DeepSeek/Mistral 新权重发布 | **本地部署体验** |

### 知识维度 — 判断方向（基础优先级）

| 维度 | content_type | 关注什么 | 拿到后做什么 |
|------|-------------|---------|-------------|
| 📖 方法论/指南 | `guide` | Anthropic/OpenAI/Google 官方最佳实践长文 | **改进你使用 AI 的方式** |
| 📄 论文/技术 | `research` | 有代码 + 有 star 的高质量论文 | **判断技术方向** |
| 📰 行业新闻 | `industry` | 商业落地、融资、政策 | **判断技术成熟度和投入时机** |

---

## 三、信息源矩阵（12 个源，含降权/精简说明）

### 3.1 源变更总览

| 源 | 原状态 | 调整后状态 | 变更原因 |
|----|--------|-----------|---------|
| GitHub Trending | ✅ 保留 | ✅ **保留** | 开源项目发现的核心渠道 |
| HuggingFace Papers | ✅ 保留 | ⚠️ **降权** | 噪音大，只推有代码+有 GitHub stars 的论文 |
| 量子位 RSS | ✅ 保留 | ✅ **保留** | 国内最快 AI 资讯 |
| 机器之心 RSS | ✅ 保留 | ✅ **保留** | 技术深度最好的中文源 |
| TechCrunch AI | ✅ 保留 | ⚠️ **降为辅助** | 与中文源重复报道，只做交叉验证，不计入推送配额 |
| Product Hunt | ✅ 保留 | ✅ **保留** | 新产品首发地 |
| Hacker News | ✅ 保留 | ⚠️ **提高门槛** | 只抓 score > 100 的帖子，过滤 Ask HN/招聘帖 |
| PulseMCP | ✅ 保留 | ✅ **保留** | MCP server 最全目录 |
| Claude Plugins Registry | ✅ 保留 | ✅ **保留** | Claude Code 插件发现 |
| ~~GitHub Topics~~ | ✅ 保留 | ❌ **砍掉** | 与 GitHub Trending + PulseMCP 高度重叠 |
| Framework Watch | ✅ 保留 | ✅ **保留** | Agent 框架版本监控 |
| 🆕 **Coding Tool Changelogs** | — | 🆕 **新增** | Claude Code / Cursor 更新直接影响开发效率 |
| 🆕 **开源模型发布** | — | 🆕 **新增** | HuggingFace Models trending + Ollama 新模型 |
| 🆕 **官方 Blog 指南** | — | 🆕 **新增** | Anthropic/OpenAI/Google 官方方法论文章 |

### 3.2 新闻资讯源

| 源 | 抓取方式 | content_type | 优先级 | 说明 | 鉴权 |
|----|---------|-------------|--------|------|------|
| **GitHub Trending** | 网页爬虫 | `dev_tool` / `research` | 🔴 核心 | AI 相关 repo，描述含关键词 | 无 |
| **HuggingFace Papers** | REST API | `research` | 🟡 降权 | ⚠️ 只推 Papers with Code 有链接 + GitHub ≥ 500 star | 无 |
| **量子位 RSS** | feedparser | `industry` / `research` | 🔴 核心 | 国内最快 | 无 |
| **机器之心 RSS** | feedparser | `industry` / `research` | 🔴 核心 | 技术最深 | 无 |
| **TechCrunch AI RSS** | feedparser | `industry` | ⚪ 辅助 | ⚠️ 只做交叉验证，不计入推送配额 | 无 |
| **Product Hunt AI** | GraphQL | `dev_tool` | 🔴 核心 | AI 分类新产品 | PH_DEV_TOKEN |
| **Hacker News** | Firebase API | `industry` / `guide` | 🟡 降噪 | ⚠️ 只看 score > 100 的 AI 帖子，过滤招聘帖 | 无 |

### 3.3 工具/组件发现源

| 源 | 抓取方式 | content_type | 关键信号 | 鉴权 |
|----|---------|-------------|---------|------|
| **PulseMCP** | 网页/RSS | `mcp_server` | 每周新 server 发布、trending 排行榜 | 无 |
| **Claude Plugins Registry** | GitHub API | `claude_skill` | 新 plugin/skill 上架、star 暴涨 | GitHub Token |
| **Framework Watch** | GitHub Releases API | `agent_framework` | LangGraph/CrewAI/MAF/OpenAI SDK 新版本 | 无 |
| **🆕 Coding Tool Changelogs** | GitHub Releases + 网页 | `coding_tool` | Claude Code / Cursor / Copilot 新版本或新功能 | GitHub Token |
| **🆕 开源模型发布** | HF API + Ollama RSS | `open_source_model` | Qwen/Llama/DeepSeek/Mistral 新权重 | 无 |
| **🆕 官方 Blog 指南** | RSS | `guide` | Anthropic/OpenAI/Google AI 官方方法论文章 | 无 |

### 3.4 Framework Watch 监控列表

| 框架 | GitHub Repo | 2026 状态 |
|------|------------|-----------|
| LangGraph | `langchain-ai/langgraph` | 活跃（v0.3.14） |
| CrewAI | `crewAIInc/crewAI` | 活跃（v1.14.4） |
| Microsoft Agent Framework | `microsoft/agent-framework` | 2026.4 GA，AutoGen 替代品 |
| OpenAI Agents SDK | `openai/openai-agents-python` | 活跃 |
| Mastra | `mastra-ai/mastra` | 活跃（TypeScript 优先） |
| Pydantic AI | `pydantic/pydantic-ai` | 活跃 |
| Deep Agents | `langchain-ai/deepagents` | 2026 新发布 |
| Dify | `langgenius/dify` | 活跃（低代码 AI 平台） |
| vLLM | `vllm-project/vllm` | 活跃（模型推理引擎） |
| llama.cpp | `ggerganov/llama.cpp` | 活跃 |

### 3.5 Coding Tool Changelogs 监控列表

| 工具 | 监控方式 | 说明 |
|------|---------|------|
| **Claude Code** | GitHub `anthropics/claude-code` releases | 新命令、MCP 集成方式变更、hooks 更新、Agent 类型 |
| **Cursor** | cursor.com/changelog (网页爬虫) | 新功能、模型切换、定价变化 |
| **VS Code Copilot** | GitHub `microsoft/vscode-copilot-release` | 新特性、Agent 模式更新 |

### 3.6 开源模型发布监控列表

| 源 | 监控方式 | 关注模型 |
|----|---------|---------|
| **HuggingFace Models Trending** | `huggingface.co/api/models?sort=trending&limit=20` | Qwen / Llama / DeepSeek / Mistral / Phi / Yi / InternLM |
| **Ollama Library** | `ollama.com/library` RSS | 新支持的模型、新版本 |

### 3.7 官方 Blog 指南监控列表

| 源 | RSS/获取方式 | 关注内容 |
|----|------------|---------|
| **Anthropic Research Blog** | `anthropic.com/research/feed` | 模型架构、Agent 设计指南、安全研究 |
| **OpenAI Blog** | `openai.com/blog/rss` | 模型发布、API 更新、最佳实践 |
| **Google AI Blog** | `blog.google/technology/ai/rss` | Gemini 更新、研究突破 |

---

## 四、系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                      信息源层 (12个异步抓取器)                          │
│                                                                      │
│  新闻资讯(7): GitHub Trending / HF Papers(降权) / RSS×2 / TC AI(辅助)  │
│              / ProductHunt / HN(score>100)                            │
│  工具发现(5): PulseMCP / ClaudePlugins / FwWatch / CodingTools / OSS   │
│  知识源(1):   官方Blog指南(Anthropic/OpenAI/Google)                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                    asyncio.gather 并发抓取
                    graceful degradation（某源失败不影响全局）
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   聚合层 → 归一化为 RawArticle                          │
│  title / url / description / source / content_type / published_at     │
│  辅助源(TechCrunch)标记为 auxiliary=true，不参与后续推送排名            │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   去重层 → 四级去重                                    │
│  Stage 1: URL 精确匹配（seen_urls.json）                              │
│  Stage 2: URL 规范化（去 UTM / http→https / 去尾斜杠）                 │
│  Stage 3: 标题模糊匹配（fuzz.token_sort_ratio ≥ 85%）                 │
│  Stage 4: 跨源 DOI/arXiv ID/GitHub repo 提取去重                      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   策展层 → LLM 批量处理 (每批8篇)                       │
│  对每篇文章生成:                                                      │
│  • chinese_title: 中文标题                                           │
│  • chinese_summary: 2-3句中文摘要（是什么 + 为什么重要）               │
│  • content_type: 内容类型确认或修正                                    │
│  • categories: 1-3个分类标签                                         │
│  • importance_score: 1-5 重要性评分                                   │
│  • recommendation_reason: 对你有什么用                               │
│  • install_command: 安装命令（mcp_server/claude_skill/coding_tool）   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   排序层                                              │
│  1. 主要排序: importance_score 降序                                   │
│  2. 直接可用加权: mcp_server / claude_skill / coding_tool 默认 +1 分  │
│  3. 价格信号加权: 涉及降价的 model_release 默认 +1 分                  │
│  4. 多样性惩罚: 连续同类别条目降权                                     │
│  5. 来源上限: 同一来源最多 3 条                                       │
│  6. 日刊: 精选 Top 8 / 周刊: 精选 Top 18 / 月刊: 全量+趋势分析         │
│  7. 辅助源条目不计入主推送配额，仅作交叉验证标记                        │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   摘要层 → 按内容类型分区                               │
│  日刊: 🔌可直接安装 → ⌨️编程工具更新 → 🤖框架更新 → 📖方法指南         │
│        → 🧠模型发布 → 📰行业动态 → 📄论文                             │
│  周刊: + 本周趋势速览 + 最高评分回顾 + 分类分布统计                      │
│  月刊: + 工具生态演进 + 推荐工具栈更新 + 下月展望                       │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   投递层 → Resend SMTP                                 │
│  Jinja2 HTML 模板 → MIME multipart/alternative → SMTP 发送           │
│  纯文本降级版本 → 指数退避重试(3次)                                     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                   状态层 → JSON 文件 → Git 自动提交                     │
│  data/seen_urls.json / digest_history.json / curated_archive/         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 五、项目结构

```
AI-Information-collection/
│
├── .github/workflows/
│   ├── daily_digest.yml       # Cron: 0 8 * * * (北京时间 16:00)
│   ├── weekly_digest.yml      # Cron: 0 9 * * 1 (周一 17:00)
│   ├── monthly_trends.yml     # Cron: 0 10 1 * * (每月1日 18:00)
│   └── manual_test.yml        # workflow_dispatch 手动测试
│
├── src/
│   ├── __init__.py
│   ├── main.py                # CLI 入口: --mode daily|weekly|monthly --dry-run
│   ├── config.py              # YAML 配置加载 + Pydantic 校验
│   │
│   ├── aggregator/
│   │   ├── __init__.py
│   │   ├── base.py            # SourceProtocol 抽象 + RawArticle 数据类 + ContentType 枚举
│   │   │
│   │   │   # ── 新闻资讯源 ──
│   │   ├── github_trending.py    # GitHub Trending 爬虫（AI 关键词过滤）
│   │   ├── huggingface_papers.py # HF Daily Papers（⚠️ 只推有代码+star的）
│   │   ├── rss_fetcher.py        # 泛用 RSS（量子位/机器之心/TechCrunch AI）
│   │   ├── product_hunt.py       # Product Hunt GraphQL
│   │   ├── hacker_news.py        # HN（⚠️ 只看 score>100 的帖子）
│   │   │
│   │   │   # ── 工具/组件发现源 ──
│   │   ├── mcp_pulse.py          # PulseMCP trending + 新发布
│   │   ├── claude_plugins.py     # Claude 插件注册表监控
│   │   ├── framework_watch.py    # Agent 框架版本发布监控
│   │   ├── coding_tools.py       # 🆕 Claude Code/Cursor/Copilot changelog
│   │   ├── oss_models.py         # 🆕 HF Models trending + Ollama 新模型
│   │   └── official_blogs.py     # 🆕 Anthropic/OpenAI/Google 官方博客指南
│   │
│   ├── curator/
│   │   ├── __init__.py
│   │   ├── models.py          # RawArticle / CuratedArticle (Pydantic v2)
│   │   ├── deduplicator.py    # 四级去重引擎
│   │   ├── llm_client.py      # OpenAI 兼容异步客户端 + 指数退避重试
│   │   ├── processor.py       # 批量策展流水线（核心逻辑）
│   │   └── ranker.py          # 评分排序 + 工具加权 + 多样性
│   │
│   ├── digest/
│   │   ├── __init__.py
│   │   ├── composer.py        # Jinja2 邮件渲染
│   │   ├── templates/
│   │   │   ├── base.html      # 共享布局 + 响应式 CSS
│   │   │   ├── daily.html     # 日刊模板（"可直接安装"优先展示）
│   │   │   ├── weekly.html    # 周刊模板（含趋势小结 + 分类统计）
│   │   │   └── monthly.html   # 月刊趋势报告模板
│   │   └── sender.py          # Resend SMTP 发送 + 重试
│   │
│   └── state/
│       ├── __init__.py
│       ├── manager.py         # JSON 文件读写 + 归档 + 过期清理
│       └── schema.py          # 状态文件 Pydantic 模型
│
├── config/
│   ├── sources.yaml           # 12 个信息源定义与参数
│   ├── categories.yaml        # 分类体系 + content_type 枚举
│   └── prompts.yaml           # LLM 提示词模板（含 content_type 区分 + 降权规则）
│
├── data/                      # 自动 git commit 的状态文件
│   ├── .gitkeep
│   ├── seen_urls.json         # 去重记录
│   ├── digest_history.json    # 摘要发送历史
│   └── curated_archive/       # 周归档（供月报趋势分析）
│
├── tests/
│   ├── conftest.py
│   ├── test_aggregator/
│   ├── test_curator/
│   ├── test_digest/
│   └── test_state/
│
├── requirements.txt
├── pyproject.toml
├── PLAN.md
├── README.md
└── .gitignore
```

---

## 六、数据模型

### 6.1 ContentType 枚举

```python
class ContentType(str, Enum):
    # === 可直接使用的工具（排序加权 +1）===
    MCP_SERVER = "mcp_server"               # MCP 服务器
    CLAUDE_SKILL = "claude_skill"           # Claude Code 技能/插件
    CODING_TOOL = "coding_tool"             # 🆕 AI 编程工具更新

    # === 技术选型参考 ===
    AGENT_FRAMEWORK = "agent_framework"     # Agent 框架更新
    DEV_TOOL = "dev_tool"                   # 通用 AI 开发工具
    MODEL_RELEASE = "model_release"         # 商业模型 API 发布/定价变化
    OPEN_SOURCE_MODEL = "open_source_model" # 🆕 开源模型权重发布

    # === 知识与趋势 ===
    GUIDE = "guide"                         # 🆕 官方方法论/最佳实践指南
    RESEARCH = "research"                   # 论文/技术突破（⚠️ 降权，只推高质量）
    INDUSTRY = "industry"                   # 行业新闻/商业/融资
```

### 6.2 排序加权规则

```python
# 基础重要性由 LLM 评定 (1-5)，在此基础上应用加权:

BONUS_RULES = {
    ContentType.MCP_SERVER:       +1,   # 可以直接装
    ContentType.CLAUDE_SKILL:     +1,   # 可以直接装
    ContentType.CODING_TOOL:      +1,   # 直接影响开发效率
    ContentType.OPEN_SOURCE_MODEL: +0.5, # 可以本地部署
}

PENALTY_RULES = {
    ContentType.RESEARCH:  0,    # 无惩罚，但 LLM 给的原始分已较低
    ContentType.INDUSTRY:  0,    # 无惩罚，但辅助源不参与排名
}

# 价格信号特殊加权:
# 如果 model_release 内容涉及降价，LLM 自动 +1 分
```

### 6.3 RawArticle（抓取后的原始条目）

```python
class RawArticle(BaseModel):
    title: str
    url: str
    description: str = ""
    source: str                        # 如 "github_trending", "coding_tools"
    content_type: ContentType          # 初步分类（源自带标签）
    auxiliary: bool = False            # 🆕 辅助源标记（如 TechCrunch）
    published_at: datetime | None = None
    metadata: dict = {}                # 源特有字段（stars/votes/score等）
    fetch_time: datetime
```

### 6.4 CuratedArticle（LLM 策展后的条目）

```python
class CuratedArticle(BaseModel):
    original: RawArticle
    chinese_title: str                          # 中文标题
    chinese_summary: str                        # 2-3 句中文摘要
    content_type: ContentType                   # LLM 确认/修正的类型
    categories: list[str]                       # 1-3 个分类标签
    importance_score: int                       # 1-5（不含加权）
    weighted_score: float                       # 🆕 含加权后的最终分数
    recommendation_reason: str                  # 一句中文推荐理由
    install_command: str | None = None          # 安装命令
    curation_time: datetime
    llm_model_used: str
```

### 6.5 状态文件 Schema

**`seen_urls.json`**：
```json
{
  "version": 1,
  "urls": {
    "https://github.com/xxx/notion-mcp": {
      "canonical_url": "https://github.com/xxx/notion-mcp",
      "first_seen": "2026-07-03T10:00:00Z",
      "last_seen": "2026-07-03T10:00:00Z",
      "source": "mcp_pulse",
      "content_type": "mcp_server",
      "times_seen": 1,
      "included_in": [
        {"digest_type": "daily", "digest_date": "2026-07-03"}
      ]
    }
  },
  "stats": {
    "total_unique_urls": 5000,
    "last_pruned": "2026-07-01T00:00:00Z"
  }
}
```

**清理策略**：当 `total_unique_urls > 10000` 时，丢弃 90 天前的条目，保持文件 < 2MB。

**`digest_history.json`**：
```json
{
  "digests": [
    {
      "digest_type": "daily",
      "date": "2026-07-03",
      "items_count": 8,
      "by_type": {
        "mcp_server": 2, "claude_skill": 1, "coding_tool": 1,
        "agent_framework": 1, "model_release": 1, "open_source_model": 1,
        "guide": 1
      },
      "auxiliary_matches": 3,
      "message_id": "<20260703101500.a1b2c3@ai-digest.local>",
      "sent_at": "2026-07-03T10:15:00Z",
      "llm_model": "deepseek-chat",
      "tokens_used": 12450,
      "cost_rmb": 0.012
    }
  ]
}
```

---

## 七、邮件模板设计

### 7.1 日刊结构

```
┌──────────────────────────────────────────────────────────┐
│       🤖 AI 信息日报 · 2026年7月3日 星期五                  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ━━━ 可直接安装/使用 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                          │
│  🔌 新 MCP 服务器 & 技能                                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │ [mcp_server] ⭐⭐⭐⭐                              │   │
│  │ ### Notion MCP Server — 让 AI 直接读写 Notion    │   │
│  │ 数据库、页面和块，支持搜索和全文检索。               │   │
│  │ 💡 如果你用 Notion 管理项目，Claude 可读写文档库    │   │
│  │ 📦 npx @anthropic-ai/mcp-server-notion           │   │
│  │ 🔗 github.com/anthropic/notion-mcp-server        │   │
│  └──────────────────────────────────────────────────┘   │
│  （mcp_server / claude_skill 卡片 0-4 张）                │
│                                                          │
│  ⌨️ AI 编程工具更新                                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │ [coding_tool] ⭐⭐⭐⭐⭐                             │   │
│  │ ### Claude Code 2.3 发布：新增 Agent 工作树隔离    │   │
│  │ 💡 升级后 agent 可独立运行，不污染你的工作区        │   │
│  │ 📦 npm update @anthropic-ai/claude-code          │   │
│  └──────────────────────────────────────────────────┘   │
│  （coding_tool 卡片 0-2 张）                              │
│                                                          │
│  ━━━ 技术与趋势 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                          │
│  🤖 Agent 框架 / 📦 开源模型 / 🧠 模型发布                │
│  （各 0-2 张卡片）                                        │
│                                                          │
│  📖 方法指南 / 📄 论文 / 📰 行业动态                       │
│  （各 0-2 张卡片）                                        │
│                                                          │
│  ─────────────────────────────────────────────────────   │
│  📊 今日统计                                              │
│  • 共收录 127 条 · LLM 精选 8 条 · API 花费 ¥0.12         │
│  • 可安装 3 | 编程工具 1 | 框架 1 | 模型 2 | 指南 1       │
│  • 交叉验证匹配 3 条（TechCrunch 辅助源）                   │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  Generated by AI Information Collector                   │
│  退订请回复 "unsubscribe"                                 │
└──────────────────────────────────────────────────────────┘
```

### 7.2 周刊结构

在日刊基础上增加：
- **📈 本周趋势速览**：LLM 生成 2-3 段中文趋势分析
- **🏆 本周最高评分 Top 3**：加权后分数最高的条目，附带深度点评
- **📊 分类分布**：各 content_type 条目数和占比
- **📦 本周新上架工具汇总**：所有 mcp_server + claude_skill + coding_tool 条目清单

### 7.3 月刊结构

在周刊基础上增加：
- **📊 月度工具生态演进**：
  - 哪些品类在爆发（MCP server 增长最快？Agent 框架更新最多？开源模型最活跃？）
  - 哪些品类在降温
- **🔄 推荐工具栈更新建议**：当前用什么 → 建议换成什么（基于本月趋势）
- **🔮 下月重点关注信号**：LLM 基于三个月数据生成前瞻性预测
- **📋 本月高分条目 Top 10**：紧凑列表回顾

---

## 八、关键技术决策

| 决策 | 选择 | 原因 |
|------|------|------|
| **状态存储** | JSON 文件（非数据库） | < 1 万条记录，JSON 足够；Git 自带备份 |
| **LLM 调用方式** | 批量处理（每批 8 篇） | 将 ~60 次 API 调用减至 ~8 次，最大成本优化 |
| **并发模型** | 全链路异步 | httpx + aiosmtplib + asyncio.gather |
| **邮件服务** | Resend SMTP | 免费层 3000 封/月 |
| **部署方式** | GitHub Actions | 公开仓库完全免费 |
| **LLM 选型** | DeepSeek V3 | ¥0.27/百万 tokens；中文最优；OpenAI 兼容 |
| **工具发现优先级** | 排序加权 + 独占首区 | mcp_server/claude_skill/coding_tool 默认 +1 分；邮件排第一板块 |
| **信息降噪策略** | 分级处理 | 核心源直接参与排名；降权源加过滤门槛；辅助源仅交叉验证 |
| **去重策略** | 四阶段级联 | URL 精确 + 规范化 + 标题模糊 + 跨源引用提取 |
| **降级策略** | 全链路 graceful degradation | 某源失败不影响全局；某批 LLM 失败跳过该批；SMTP 失败仍写状态 |

---

## 九、配置文件设计

### 9.1 `config/sources.yaml`

```yaml
global:
  max_per_source: 30
  request_timeout: 30
  rate_limit_delay_ms: 500
  user_agent: "AI-Info-Collector/1.0 (GitHub Actions; Digest Bot)"

sources:
  # ========== 新闻资讯源 ==========

  github_trending:
    enabled: true
    priority: "core"            # core | degraded | auxiliary
    since: "daily"
    ai_keywords: ["ai", "llm", "machine-learning", "deep-learning", "nlp", "gpt",
                  "transformer", "diffusion", "langchain", "agent", "rag"]
    max_items: 25

  huggingface_papers:
    enabled: true
    priority: "degraded"        # ⚠️ 降权：只推有代码+有stars的
    endpoint: "https://huggingface.co/api/daily_papers"
    max_items: 25
    quality_filter:
      require_paper_with_code: true    # 必须有 Papers with Code 链接
      min_github_stars: 500            # GitHub repo ≥ 500 stars

  rss_feeds:
    - name: "量子位"
      url: "https://www.qbitai.com/feed"
      enabled: true
      priority: "core"
      language: "zh"
      max_items: 20
    - name: "机器之心"
      url: "https://www.jiqizhixin.com/rss"
      enabled: true
      priority: "core"
      language: "zh"
      max_items: 20

  techcrunch_ai:
    enabled: true
    priority: "auxiliary"       # ⚠️ 辅助：只做交叉验证
    url: "https://techcrunch.com/category/artificial-intelligence/feed/"
    language: "en"
    max_items: 15

  product_hunt:
    enabled: true
    priority: "core"
    topic_slug: "ai"
    max_items: 20

  hacker_news:
    enabled: true
    priority: "degraded"        # ⚠️ 降噪：只看高分帖子
    story_type: "top"
    max_fetch_ids: 100
    min_score: 100              # 只看 score > 100
    exclude_keywords: ["Ask HN", "Who is hiring", "Launch HN"]
    ai_keywords: ["AI", "LLM", "GPT", "OpenAI", "Anthropic", "Claude",
                  "Gemini", "machine learning", "deep learning", "transformer",
                  "RAG", "fine-tuning", "neural network", "AGI", "agent",
                  "MCP", "model context protocol"]
    max_items: 20

  # ========== 工具/组件发现源 ==========

  mcp_pulse:
    enabled: true
    priority: "core"
    trending_url: "https://pulsemcp.com/api/trending"
    newsletter_url: "https://pulsemcp.com/newsletter"
    max_items: 20

  claude_plugins:
    enabled: true
    priority: "core"
    registry_repo: "Kamalnrf/claude-plugins"
    watch_interval_hours: 24
    max_items: 15

  framework_watch:
    enabled: true
    priority: "core"
    repos:
      - "langchain-ai/langgraph"
      - "crewAIInc/crewAI"
      - "microsoft/agent-framework"
      - "openai/openai-agents-python"
      - "mastra-ai/mastra"
      - "pydantic/pydantic-ai"
      - "langchain-ai/deepagents"
      - "langgenius/dify"
      - "vllm-project/vllm"
      - "ggerganov/llama.cpp"
    lookback_days: 1

  # ========== 🆕 新增源 ==========

  coding_tools:
    enabled: true
    priority: "core"
    tools:
      - name: "Claude Code"
        github_repo: "anthropics/claude-code"
        watch: "releases"
      - name: "Cursor"
        changelog_url: "https://www.cursor.com/changelog"
        watch: "changelog"
      - name: "VS Code Copilot"
        github_repo: "microsoft/vscode-copilot-release"
        watch: "releases"
    lookback_days: 1

  oss_models:
    enabled: true
    priority: "core"
    hf_trending:
      endpoint: "https://huggingface.co/api/models"
      params: {sort: "trending", limit: 20}
    ollama_library:
      rss_url: "https://ollama.com/library"
    watch_families: ["Qwen", "Llama", "DeepSeek", "Mistral", "Phi", "Yi", "InternLM", "Gemma"]

  official_blogs:
    enabled: true
    priority: "core"
    feeds:
      - name: "Anthropic Research"
        url: "https://www.anthropic.com/research/feed"
        content_type: "guide"
      - name: "OpenAI Blog"
        url: "https://openai.com/blog/rss"
        content_type: "guide"
      - name: "Google AI Blog"
        url: "https://blog.google/technology/ai/rss"
        content_type: "guide"
    max_items: 10
```

### 9.2 `config/prompts.yaml`（关键变更点）

```yaml
curation:
  system_prompt: |
    你是一位专业的 AI 信息策展人，服务于中文 AI 从业者社区。
    你的任务是对 AI 相关文章进行深度加工。

    重要原则:
    - 所有输出使用简体中文
    - 摘要需要回答"是什么"和"为什么重要"
    - 重要性评分客观，不要都评高分
    - 推荐理由要让读者知道"这对我有什么用"
    - 工具类内容必须给出 install_command
    - 涉及 API 模型定价变化的内容，自动 +1 重要性分
    - 严格返回 JSON 格式

  content_type_guide: |
    内容类型判断标准:
    - mcp_server: MCP 服务器相关（发布、评测、教程）
    - claude_skill: Claude Code 技能或插件
    - coding_tool: AI 编程工具更新（Claude Code/Cursor/Copilot 新版本或新功能）
    - agent_framework: Agent 开发框架的版本发布、功能更新
    - dev_tool: AI IDE、低代码平台、向量数据库、模型部署工具的更新
    - model_release: 商业模型 API 发布、更新、定价变化（降价标记为 high_impact）
    - open_source_model: 开源模型权重发布（Qwen/Llama/DeepSeek/Mistral 等）
    - guide: 官方或社区高质量方法论、最佳实践指南
    - research: 学术论文、深度技术博客（需有代码或工程价值）
    - industry: 行业新闻、商业分析、融资、政策

  importance_guide: |
    重要性评分标准 (1-5):
    5: 突破性进展，行业里程碑
    4: 重要技术创新，核心产品发布，主流框架大版本
    3: 有参考价值的研究成果或应用更新
    2: 一般性行业报道或小型工具更新
    1: 信息量低，边缘相关

    mcp_server / claude_skill / coding_tool 类型默认 LLM 评分 +1（可直接安装使用）
    涉及模型定价下调的 model_release，LLM 评分 +1

  batch_curation: |
    请处理以下 {count} 篇文章。对每一篇提供:
    
    1. chinese_title: 中文标题
    2. chinese_summary: 2-3 句中文摘要（核心内容 + 为什么值得关注）
    3. content_type: 从 {content_types} 中选择
    4. categories: 从 {categories} 中选择 1-3 个
    5. importance_score: 1-5 整数（原始分，不含加权）
    6. recommendation_reason: 一句中文推荐理由
    7. install_command: 安装命令（仅 mcp_server/claude_skill/coding_tool 类型）
    8. has_price_change: 涉及定价变化则为 true
    
    文章列表:
    {articles_json}
    
    只返回 JSON 数组。

  trend_analysis: |
    你是一位 AI 行业分析师。基于 {start_date} 至 {end_date} 的数据撰写月度趋势报告。
    
    数据摘要:
    - 总收录: {total_items} 篇
    - 可直接安装: {installable_items} 篇（MCP {mcp_count} + Skill {skill_count} + 编程工具{coding_count}）
    - 开源模型: {oss_count} 篇 | 商业模型: {model_count} 篇
    - 方法指南: {guide_count} 篇 | 框架更新: {framework_count} 篇
    - 高分条目(≥4分): {high_score_items} 篇
    
    请分析:
    1. 工具生态演进: 哪些品类在爆发，哪些在降温
    2. 关键技术突破: 本月最重要的 3-5 个进展
    3. 值得关注的新项目/产品: 3-5 个
    4. 推荐工具栈更新建议: 基于趋势建议替换方案
    5. 下月重点关注信号
```

---

## 十、部署架构

### 10.1 GitHub Actions 工作流

**`daily_digest.yml`**：
```yaml
name: Daily AI Digest

on:
  schedule:
    - cron: '0 8 * * *'        # UTC 08:00 = 北京时间 16:00
  workflow_dispatch:

permissions:
  contents: write               # 允许 push 状态文件

concurrency:
  group: daily-digest
  cancel-in-progress: false     # 防重复触发

jobs:
  daily-digest:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
      - run: pip install -r requirements.txt
      - name: Run daily digest
        env:
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          LLM_BASE_URL: ${{ secrets.LLM_BASE_URL }}
          LLM_MODEL: ${{ secrets.LLM_MODEL }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USERNAME: ${{ secrets.SMTP_USERNAME }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          EMAIL_FROM: ${{ secrets.EMAIL_FROM }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          PH_DEV_TOKEN: ${{ secrets.PH_DEV_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python -m src.main --mode daily
      - name: Commit state
        if: success() || failure()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          if ! git diff --staged --quiet; then
            git commit -m "chore: update state after daily digest [skip ci]"
            git push
          fi
```

**调度时间说明**：

| 工作流 | Cron | 北京时间 | 说明 |
|--------|------|---------|------|
| 日刊 | `0 8 * * *` | 每天 16:00 | 下午推送，收全当天信息 |
| 周刊 | `0 9 * * 1` | 每周一 17:00 | 周一推送，覆盖上周 |
| 月刊 | `0 10 1 * *` | 每月 1 日 18:00 | 月初推送，分析上月 |

### 10.2 GitHub Secrets

| Secret | 用途 | 获取方式 |
|--------|------|---------|
| `LLM_API_KEY` | DeepSeek API Key | platform.deepseek.com → API Keys |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 固定值 |
| `LLM_MODEL` | `deepseek-chat` | 可选换其他兼容模型 |
| `SMTP_HOST` | `smtp.resend.com` | 固定值 |
| `SMTP_PORT` | `587` | 固定值 |
| `SMTP_USERNAME` | Resend SMTP 用户名 | resend.com → Settings → SMTP |
| `SMTP_PASSWORD` | Resend API Key | resend.com → API Keys |
| `EMAIL_FROM` | 发件人地址 | 需在 Resend 中验证 |
| `EMAIL_TO` | 收件人地址 | 你的个人邮箱 |
| `PH_DEV_TOKEN` | Product Hunt API Token | producthunt.com → Settings → API |
| `GITHUB_TOKEN` | GitHub Personal Token | 用于提高 API 限流（可选） |

---

## 十一、成本估算

| 项目 | 用量 | 月成本 |
|------|------|--------|
| **DeepSeek V3 API** | 日刊 ~18K × 30 = 540K；周刊 ~30K × 4 = 120K；月刊 ~60K × 1 = 60K；合计约 720K tokens/月 | **约 ¥0.50 - ¥1.00** |
| **Resend Email** | 35 封/月 | **¥0（免费层 3000 封）** |
| **GitHub Actions** | ~35 次运行/月，每次 3-5 分钟 | **¥0（公开仓库免费）** |
| **合计** | | **约 ¥0.50 - ¥1.00/月** |

> 新旧方案成本对比：源从 11 个微调至 12 个，但降权策略减少了 LLM 处理量，成本基本持平。

---

## 十二、实施阶段

### Phase 1: 项目骨架 + 配置（预计 2 天）

**创建文件**：
- `pyproject.toml` + `requirements.txt`
- `config/sources.yaml` + `config/categories.yaml` + `config/prompts.yaml`
- `src/config.py`（YAML 加载 + Pydantic 校验）
- `src/curator/models.py`（RawArticle / CuratedArticle / ContentType / 加权规则）
- `src/state/schema.py`
- `.gitignore` + `data/.gitkeep`
- 所有 `__init__.py`

**验证**：`python -c "from src.config import load_config; print(load_config())"` 正常输出。

### Phase 2: 状态管理（预计 1 天）

**创建文件**：`src/state/manager.py`

**功能**：
- seen_urls 读写 / 标记已见
- digest_history 记录
- curated_archive 周归档写入
- 过期清理（> 90 天或 > 10000 条）

### Phase 3: 数据聚合（预计 3 天）

**3.1 新闻资讯源（7 个）**：
- `src/aggregator/base.py` — SourceProtocol + priority 字段
- `src/aggregator/rss_fetcher.py` — 最先做（最简单）
- `src/aggregator/github_trending.py` — 爬虫
- `src/aggregator/huggingface_papers.py` — REST API + quality_filter
- `src/aggregator/hacker_news.py` — Firebase + min_score + 排除关键词
- `src/aggregator/product_hunt.py` — GraphQL
- `src/aggregator/techcrunch.py` — RSS，标记 auxiliary=true

**3.2 工具发现源（5 个）**：
- `src/aggregator/mcp_pulse.py`
- `src/aggregator/claude_plugins.py`
- `src/aggregator/framework_watch.py`
- `src/aggregator/coding_tools.py` — 🆕 GitHub releases + changelog 爬虫
- `src/aggregator/oss_models.py` — 🆕 HF Models API + Ollama RSS
- `src/aggregator/official_blogs.py` — 🆕 Anthropic/OpenAI/Google RSS

**3.3 聚合池**：`asyncio.gather` 并发，按 priority 分级处理结果。

### Phase 4: LLM 策展流水线（预计 2 天）

- `src/curator/llm_client.py` — OpenAI 兼容异步客户端
- `src/curator/deduplicator.py` — 四级去重
- `src/curator/processor.py` — 批量策展核心（含加权计算）
- `src/curator/ranker.py` — 排序 + 加权 + 多样性 + auxiliary 排除

**验证**：5 篇文章真实 LLM 调用，检查加权结果。

### Phase 5: 邮件组合与投递（预计 1 天）

- `src/digest/templates/base.html` — 响应式布局
- `src/digest/templates/daily.html` — 🆕 新的分区顺序（工具优先 → 方法指南 → 技术动态）
- `src/digest/templates/weekly.html`
- `src/digest/templates/monthly.html`
- `src/digest/composer.py`
- `src/digest/sender.py` — Resend SMTP

### Phase 6: 主流水线集成（预计 1 天）

`src/main.py`：配置 → 抓取 → 去重 → 策展 → 排序 → 摘要 → 发送 → 状态。含 `--dry-run`。

### Phase 7: GitHub Actions 部署（预计 1 天）

4 个 workflow YAML + secrets 配置。

### Phase 8: 测试、文档、调优（预计 1 天）

单元测试 + README + 首周 dry-run 质量调优。

---

## 十三、渐进上线计划

| 周次 | 动作 | 检查点 |
|------|------|--------|
| **第 1 周** | 手动触发 + `--dry-run` | 所有 12 个源抓取成功率 > 80%；降权/辅助逻辑正确 |
| **第 2 周** | 启用日刊 cron + dry-run | 7 天连续稳定；GitHub Actions 无报错 |
| **第 3 周** | 日刊正式发送 | 邮件准时到达；内容质量满意；工具发现有用 |
| **第 4 周** | 启用周刊 | 周刊格式正确；趋势分析有价值 |
| **第 5 周** | 启用月刊，全量运行 | 月度报告有洞察；推荐建议可执行 |

---

## 十四、验证方法

| 验证阶段 | 方法 | 通过标准 |
|---------|------|---------|
| **单元测试** | `pytest` 覆盖去重/JSON/模板/排序/加权 | 覆盖率 > 80% |
| **集成测试** | `--dry-run` 端到端 | 无异常退出；HTML 正常渲染 |
| **邮件渲染** | Gmail Web/Mobile、Apple Mail | 无样式错乱；中文正常 |
| **内容质量** | 人工检查 3-5 天日刊 | 摘要准确、评分合理、推荐有用 |
| **降噪效果** | 对比过滤前后的条目数 | 降权源噪音减少 > 50% |
| **稳定性** | 连续 7 天 dry-run | 无源中断超 2 天；无异常堆积 |

---

## 十五、后续扩展方向（非本期范围）

- [ ] **微信推送**：企业微信机器人 Webhook 推送简短摘要
- [ ] **Web 端查看**：Cloudflare Pages 托管归档浏览
- [ ] **个人偏好学习**：根据你安装了哪些 MCP/skill，调整推荐权重
- [ ] **自定义监控关键词**：特别关注 `RAG`、`GUI Agent`、`Computer Use` 等领域
- [ ] **多接收人**：支持订阅管理，推送给团队成员
- [ ] **工具安装统计**：跟踪你实际安装了哪些推荐的工具，优化推荐准确率
- [ ] **中文源扩展**：增加 36氪/极客公园/InfoQ 等 RSS 源
- [ ] **视频内容摘要**：监控热门 AI YouTube 频道，自动生成文字摘要
