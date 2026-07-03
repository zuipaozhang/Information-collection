# AI 信息聚合推送系统 — 架构与流程文档

> 本文档面向维护者和后续优化，描述系统完整架构、数据流、模块职责和可优化节点。

---

## 目录

1. [系统全景图](#1-系统全景图)
2. [数据流逐层详解](#2-数据流逐层详解)
3. [模块职责图](#3-模块职责图)
4. [信息源明细](#4-信息源明细)
5. [LLM 策展核心逻辑](#5-llm-策展核心逻辑)
6. [状态管理机制](#6-状态管理机制)
7. [邮件渲染链路](#7-邮件渲染链路)
8. [部署与调度](#8-部署与调度)
9. [可优化节点清单](#9-可优化节点清单)

---

## 1. 系统全景图

```
  ┌────────────────────────── 调度层 ──────────────────────────┐
  │  GitHub Actions Cron                                       │
  │  日刊 cron(0 8 * * *)  周刊 cron(0 9 * * 1)  月刊 cron(0 10 1 * *) │
  └──────────────────────────────────────────────────────────┬─┘
                                                             │
  ┌──────── 信息源层 (12 个异步抓取器) ────────┐              │
  │  ┌──────────────── 新闻资讯 (7) ─────────────┐           │
  │  │ 核心源: GitHub Trending / 量子位 / 机器之心  │          │
  │  │       Product Hunt / HuggingFace Papers     │          │
  │  │ 降噪源: Hacker News (score>100)             │          │
  │  │ 辅助源: TechCrunch AI (仅交叉验证)            │          │
  │  └────────────────────────────────────────────┘           │
  │  ┌──────────────── 工具发现 (5) ─────────────┐           │
  │  │ PulseMCP / Claude Plugins / Framework Watch│          │
  │  │ Coding Tools / OSS Models                  │          │
  │  └────────────────────────────────────────────┘           │
  │  ┌──────────────── 知识源 (1) ───────────────┐           │
  │  │ 官方 Blog (Anthropic/OpenAI/Google)        │          │
  │  └────────────────────────────────────────────┘           │
  └──────────────────────┬───────────────────────────────────┘
                         │ asyncio.gather 并发 → 117 raw items
                         ▼
  ┌──────────────── 去重层 ──────────────────────────────────┐
  │  Stage 1: URL 精确匹配  (seen_urls.json)                  │
  │  Stage 2: URL 规范化     (去 UTM / http→https / 去斜杠)  │
  │  Stage 3: 标题模糊匹配   (thefuzz ≥ 85%)                 │
  │  Stage 4: 跨源引用提取   (arXiv ID / DOI / GitHub repo)  │
  └──────────────────────┬───────────────────────────────────┘
                         │ 117 → ~110 unique
                         ▼
  ┌──────────────── 策展层 (LLM 批量) ────────────────────────┐
  │  每批 8 篇文章 → DeepSeek V3                               │
  │  输出: 中文标题 / 中文摘要 / content_type / 分类标签         │
  │       重要性评分(1-5) / 推荐理由 / 安装命令                  │
  └──────────────────────┬───────────────────────────────────┘
                         │ ~110 → 110 curated
                         ▼
  ┌──────────────── 排序层 ──────────────────────────────────┐
  │  1. 工具加权: mcp_server/claude_skill/coding_tool +1 分   │
  │  2. 价格加权: 降价 model_release +1 分                     │
  │  3. 多样性惩罚: 同类别连续降 0.2 分                         │
  │  4. 来源上限: 同源最多 3 条                                 │
  │  5. 日刊 Top 8 / 周刊 Top 18 / 月刊 Top 50                 │
  └──────────────────────┬───────────────────────────────────┘
                         │ 8 / 18 / 50 selected
                         ▼
  ┌──────────────── 邮件层 ──────────────────────────────────┐
  │  Jinja2 模板 → HTML + 纯文本 → Resend HTTP API            │
  │  日刊分区: 可安装工具 → 编程工具 → 框架 → 模型 → 方法 → 论文 │
  └──────────────────────┬───────────────────────────────────┘
                         │
                         ▼
  ┌──────────────── 状态层 ──────────────────────────────────┐
  │  data/seen_urls.json      去重记录 (>10000条自动清理90天前) │
  │  data/digest_history.json 推送历史                         │
  │  data/curated_archive/    周归档 (月刊趋势分析数据来源)      │
  │  GitHub Actions 自动 git commit 回仓库                     │
  └──────────────────────────────────────────────────────────┘
```

---

## 2. 数据流逐层详解

### 2.1 数据获取阶段

```
src/main.py → create_all_aggregators() → 12 个 SourceProtocol 实例
    │
    ├── RSSFetcher (量子位 RSS)
    ├── ScrapingFetcher (机器之心，RSS 已下线切爬虫)
    ├── GitHubTrendingSource (爬虫)
    ├── HuggingFacePapersSource (REST API)
    ├── HackerNewsSource (Firebase API)
    ├── ProductHuntSource (GraphQL API)
    ├── MCPPulseSource (页面爬虫 + dev.to RSS)
    ├── ClaudePluginsSource (GitHub API)
    ├── FrameworkWatchSource (GitHub Releases API)
    ├── CodingToolsSource (GitHub Releases + 爬虫)
    ├── OSSModelsSource (HF Models API)
    └── OfficialBlogsSource (RSS + 爬虫 fallback)
    
    ↓ asyncio.gather 并发执行所有 fetch()
    
RawArticle {
    title, url, description, source, content_type,
    priority (core|degraded|auxiliary), auxiliary flag,
    published_at, metadata, fetch_time
}
```

**关键设计决策**：每个 fetcher 的 fetch() 方法**永远不抛异常**，失败返回空列表。借此实现 graceful degradation。

**可优化点**：
- 当前等待所有源完成才进入下一步。可以通过 asyncio 队列改造为流式处理——某个源先完成先进入去重/策展
- HF Papers 和 HN 当前有过滤但代码判断较简单，可增强

---

### 2.2 去重阶段

```
src/curator/deduplicator.py → Deduplicator.deduplicate(articles)
    │
    ├── 遍历每篇文章
    ├── canonicalize_url(url)
    │   ├── 小写 scheme + host
    │   ├── 去 80/443 默认端口
    │   ├── 去 fragment (#section)
    │   ├── 去 utm_*/ref/fbclid/gclid 等追踪参数
    │   └── 去末尾斜杠
    │
    ├── Stage 1+2: 查 seen_urls.json 全量历史 + 当前批次
    │
    ├── Stage 3: 标题模糊匹配 (仅跨不同源)
    │   └── fuzz.token_sort_ratio ≥ 85 → 视为重复
    │
    └── Stage 4: 跨源引用提取
        ├── 正则提取 arXiv ID  → "arxiv:2501.xxxxx"
        ├── 正则提取 DOI       → "doi:10.xxxx/xxxxx"
        └── 正则提取 GitHub repo → 小写比较
```

**可优化点**：
- 当前 Stage 3 只在当前批次内比较（不查历史），高频率出现的事件会被不同天的日报重复推送
- 可以引入语义去重（embedding similarity），但成本会增加

---

### 2.3 LLM 策展阶段

```
src/curator/processor.py → CurationProcessor.curate_all(articles)
    │
    ├── 按 priority 排序: CORE → DEGRADED → (AUXILIARY 已排除)
    │
    ├── 分 batch (每批 8 篇)
    │
    ├── 对每批: curate_batch(batch, batch_id)
    │   ├── 构建 prompt  (config/prompts.yaml → batch_curation)
    │   ├── LLM 调用     (DeepSeek V3, temperature=0.1)
    │   ├── JSON 解析    (自动处理 markdown 代码块包裹)
    │   ├── 校验评分范围 (1-5)、分类在允许集合
    │   ├── 应用加权     (SORTING_BONUS + price_change bonus)
    │   └── 失败重试     (拆分 batch 重试一次)
    │
    └── 累加 token 计数和成本
```

**LLM 成本估算**：
```
日刊 30 篇文章 ÷ 8/批 ≈ 4 次 API 调用
每次: ~4K input + ~1K output tokens
DeepSeek V3: ¥0.00027/1K input + ¥0.0011/1K output
日均: 4 × (0.00108 + 0.0011) ≈ ¥0.009
月均: 30 × 0.009 ≈ ¥0.27 (加上周刊+月刊约 ¥0.50-1.00)
```

**可优化点**：
- prompt 质量是内容质量的核心变量。[config/prompts.yaml](config/prompts.yaml) 里的 `system_prompt`、`importance_guide` 可直接修改
- 可以换更便宜的模型（如 DeepSeek V2.5 或 Qwen3-72B）进一步降成本
- 评分差异化不明显时（都评 3-4 分），收紧 importance_guide 中的标准描述

---

### 2.4 排序阶段

```
src/curator/ranker.py → Ranker.select_top(articles, n=8)
    │
    ├── 过滤: 排除 AUXILIARY priority 项
    │
    ├── 分组: installable (MCP/Skill/CodingTool) 独立排序
    │
    ├── 应用 diversity:
    │   ├── 同源超过 3 条 → -2.0 分 (近乎排除)
    │   └── 同类别与前一条 → -0.2 分
    │
    ├── 保证比例: 至少 40% 为可安装工具 (如有)
    │
    └── 返回 Top N
```

**可优化点**：
- 当前 40% 比例是硬编码的，可移到配置项
- 多样性惩罚只对比前一条，可以扩展为滑动窗口（最近 3 条同类别惩罚递增）

---

### 2.5 邮件渲染阶段

```
src/digest/composer.py → DigestComposer.compose_daily()
    │
    ├── 遍历 articles → _item_to_template_data()
    │   └── 映射 content_type → 中文标签 + 图标
    │
    ├── 拆分: installable_items / tech_items
    │
    ├── Jinja2 渲染 daily.html (继承 base.html)
    │   ├── base.html    共享 header/footer/响应式CSS
    │   ├── daily.html    [🔌可安装工具] → [📊技术与趋势]
    │   ├── weekly.html   趋势速览 + 高分回顾 + 分布图
    │   └── monthly.html  趋势报告 + Top 10 + 工具汇总
    │
    ├── 生成 plain text 降级版本 (正则去 HTML 标签)
    │
    └── 返回 (html_body, text_body, subject)
```

**模板变量映射**：
```
CuratedArticle  →  模板变量
────────────────────────────────────
chinese_title     title
chinese_summary   summary (2-3 句)
importance_score  ★ 星级显示 (1-5)
content_type      图标 + 中文标签
recommendation_reason  💡 推荐理由
install_command    📦 安装命令
original.url       🔗 原文链接
original.source    🏷️ 来源标签
```

**可优化点**：
- 当前 CSS 使用 inline style 保证 Gmail 兼容，但牺牲了易维护性
- 邮件布局可以改为更紧凑的卡片式
- plain text 版本生成方式较原始（正则去标签），可以手写 text 模板

---

### 2.6 邮件投递阶段

```
src/digest/sender.py → EmailSender.send()
    │
    ├── 构建 MIME multipart/alternative
    │   ├── text/plain  (纯文本)
    │   └── text/html   (富文本)
    │
    ├── Resend HTTP API  POST /emails
    │   └── Authorization: Bearer {SMTP_PASSWORD}
    │
    └── 重试: 3 次指数退避 (2s/4s/8s)
```

**可优化点**：
- 当前 from 地址用的是 Resend 测试地址 `onboarding@resend.dev`，域名验证后切换到自定义域名
- 可以添加 Batch API（一次调用发多封，如果后续支持多收件人）

---

## 3. 模块职责图

```
src/
├── main.py                 ─── 流水线编排 (7 步)
│   ├── run_digest(mode)    主流程: 1.抓→2.去→3.策→4.排→5.组→6.发→7.存
│   └── create_all_aggregators()  聚合器工厂
│
├── config.py               ─── 配置加载
│   └── AppConfig           单例，YAML + 环境变量
│
├── aggregator/             ─── 数据获取层
│   ├── base.py             SourceProtocol 接口 + RawArticle + 工具函数
│   ├── rss_fetcher.py      RSSFetcher + ScrapingFetcher + 工厂函数
│   ├── github_trending.py  爬虫: BeautifulSoup 解析 github.com/trending
│   ├── huggingface_papers.py REST: huggingface.co/api/daily_papers
│   ├── hacker_news.py      Firebase: hacker-news.firebaseio.com/v0
│   ├── product_hunt.py     GraphQL: api.producthunt.com/v2
│   ├── mcp_pulse.py        爬虫 + dev.to RSS
│   ├── claude_plugins.py   GitHub API: commits + releases
│   ├── framework_watch.py  GitHub Releases API (10 个框架)
│   ├── coding_tools.py     GitHub Releases + 页面爬虫
│   ├── oss_models.py       HF Models API: trending + watch_families
│   └── official_blogs.py   RSS + 爬虫 fallback
│
├── curator/                ─── LLM 策展层
│   ├── models.py           ContentType 枚举 / RawArticle / CuratedArticle / SORTING_BONUS
│   ├── deduplicator.py     四级去重引擎 (2 个内部方法)
│   ├── llm_client.py       OpenAI 兼容客户端 (chat_completion + with_json)
│   ├── processor.py        批量策展: 分批 → LLM → JSON 解析 → 加权 → 重试
│   └── ranker.py           排序: 加权+多样性+比例保证+soruce cap
│
├── digest/                 ─── 邮件层
│   ├── composer.py         Jinja2 渲染 + 统计计算 + HTML→Text
│   ├── sender.py           Resend HTTP API (+ 原 SMTP fallback 已移除)
│   └── templates/          4 个 HTML 模板 (base / daily / weekly / monthly)
│
├── state/                  ─── 状态层
│   ├── schema.py           Pydantic: SeenURLStore / DigestHistory / WeeklyArchive
│   └── manager.py          JSON CRUD + 归档 + 过期清理 (>90天 or >10000条)
│
config/
├── sources.yaml             12 个信息源定义 (enabled/priority/参数)
├── categories.yaml          13 个分类 + 10 个 content_type 元数据
└── prompts.yaml             LLM 系统提示词 + 策展 + 趋势分析模板

data/                       ─── 运行时状态 (Git 自动提交)
├── seen_urls.json            去重记录
├── digest_history.json       推送历史
└── curated_archive/          周归档 YYYY-Www.json

.github/workflows/          ─── 调度
├── daily_digest.yml          cron(0 8 * * *) UTC 08:00 = BJ 16:00
├── weekly_digest.yml         cron(0 9 * * 1) 周一 BJ 17:00
├── monthly_trends.yml        cron(0 10 1 * *) 每月1日 BJ 18:00
└── manual_test.yml           workflow_dispatch
```

---

## 4. 信息源明细

### 4.1 数据获取方式分类

| 获取方式 | 源 | 稳定性 | 说明 |
|---------|-----|--------|------|
| **RSS (feedparser)** | 量子位 | 🟢 稳定 | 标准 RSS 2.0 |
| | OpenAI Blog | 🟢 稳定 | |
| | Google AI Blog | 🟢 稳定 | |
| **页面爬虫 (BS4)** | GitHub Trending | 🟡 偶尔改版 | 解析 `article.Box-row` |
| | 机器之心 | 🔴 无 RSS | JS 渲染页面，目前只能抓到部分静态内容 |
| | PulseMCP | 🟡 需认证 | 搭配 dev.to RSS 做社区内容 |
| | Cursor changelog | 🟡 | 静态 changelog |
| | Anthropic Research | 🟡 | 动态加载 JS |
| **REST API** | HuggingFace Papers | 🟢 稳定 | `/api/daily_papers` |
| | HuggingFace Models | 🟢 稳定 | `/api/models?sort=trending` |
| | Hacker News | 🟢 稳定 | Firebase 公开 API |
| **GraphQL** | Product Hunt | 🟢 稳定 | 需 PH_DEV_TOKEN |
| **GitHub API** | Claude Plugins | 🟢 稳定 | /repos/{repo}/commits + /releases |
| | Framework Watch | 🟢 稳定 | /repos/{repo}/releases |
| | Coding Tools | 🟢 稳定 | /repos/anthropics/claude-code/releases |

### 4.2 三级优先级

| 优先级 | 特征 | 包含源 | 行为 |
|--------|------|--------|------|
| **core** | 全参与 | GitHub Trending / 量子位 / PH / PulseMCP 等 | 去重 → 策展 → 排序 → 推送 |
| **degraded** | 加过滤门槛 | HF Papers (PWC+500★) / HN (score>100) | 去重 → 策展 → 排序 → 推送 (评分可能偏低) |
| **auxiliary** | 仅交叉验证 | TechCrunch AI | 去重 → 不策展 → 不推送 → 仅统计匹配条数 |

---

## 5. LLM 策展核心逻辑

### 5.1 一次策展的完整调用链

```
processor.curate_all(articles)
    │
    ├── 1. 排序: CORE → DEGRADED
    │
    ├── 2. 分 batch: 每 8 篇一组
    │
    ├── 3. processor.curate_batch(batch, id)
    │   │
    │   ├── 3a. _format_articles_for_prompt()
    │   │   └── 每篇提取: id / title / description[:300] / source / original_content_type
    │   │
    │   ├── 3b. prompt 渲染
    │   │   └── system_prompt + batch_curation 模板 + articles JSON
    │   │
    │   ├── 3c. llm_client.chat_completion_with_json()
    │   │   ├── AsyncOpenAI 调用 (temperature=0.1)
    │   │   ├── 自动去 markdown 代码块
    │   │   └── 解析 JSON array
    │   │
    │   ├── 3d. _parse_llm_response()
    │   │   ├── 遍历 results → 映射 id → 构建 CuratedArticle
    │   │   ├── ContentType 字符串 → 枚举映射
    │   │   ├── 校验 importance_score ∈ [1,5]
    │   │   ├── _apply_sorting_bonus() → weighted_score
    │   │   └── has_price_change 额外 +1
    │   │
    │   └── 3e. 失败处理
    │       └── 拆分为 2 个子 batch 各重试一次
    │
    └── 4. 汇总 all_curated + 统计
```

### 5.2 ContentType 判断流程

```
LLM 在 prompt 中根据 content_type_guide 判断:

原始源标签 (来自 aggregator) → LLM 重分类 (可能修正)
    github_trending  → dev_tool or research
    mcp_pulse        → mcp_server
    claude_plugins   → claude_skill
    framework_watch  → agent_framework
    coding_tools     → coding_tool
    oss_models       → open_source_model
    official_blogs   → guide (model_release 如有标题关键词)
    rss_量子位        → industry or research (LLM 判断)
    huggingface_papers → research
    hacker_news      → industry or guide (score≥200 含长文关键词)
    product_hunt     → dev_tool
```

### 5.3 评分加权链

```
LLM 原始评分 (1-5)
    │
    ├── +1.0  if content_type ∈ {MCP_SERVER, CLAUDE_SKILL, CODING_TOOL}
    ├── +0.5  if content_type == OPEN_SOURCE_MODEL
    ├── +1.0  if has_price_change == true (模型降价)
    └── +0    else
    │
    → weighted_score (上限仍是 5.0)
    │
    → Ranker 排序 (再叠加多样性调整)
```

---

## 6. 状态管理机制

### 6.1 文件结构

```
data/
├── seen_urls.json          ┌──────────────────────┐
│   {                       │  {url: {              │
│     "version": 1,         │    canonical_url,     │
│     "urls": {...},        │    first_seen,        │
│     "stats": {            │    last_seen,         │
│       total_unique_urls,  │    source,            │
│       last_pruned         │    content_type,      │
│     }                     │    times_seen,        │
│   }                       │    included_in[] }    │
│                           │  }                    │
├── digest_history.json     └──────────────────────┘
│   {
│     "digests": [
│       {digest_type, date, items_count, by_type,
│        message_id, sent_at, llm_model, tokens_used, cost_rmb},
│       ...
│     ]
│   }
│
└── curated_archive/
    ├── 2026-W27.json
    ├── 2026-W28.json
    └── ...
        {week, start_date, end_date,
         items: [{title, url, chinese_title, chinese_summary,
                  content_type, categories, importance_score,
                  weighted_score, install_command, ...}],
         category_counts, content_type_counts}
```

### 6.2 状态生命周期

```
程序启动 → StateManager(data/) 初始化
    │
    ├── load_seen_urls()  从 seen_urls.json 加载
    ├── load_history()    从 digest_history.json 加载
    │
抓取阶段 → 每个 URL 经过 canonicalize_url
去重阶段 → mark_as_seen(canonical_url, source, content_type)
    │
策展+排序 → archive_curated_items(selected, week_label)
发送完成 → record_digest_sent(type, date, items, message_id, ...)
    │
save_all()
    ├── 自动 prune: total_unique_urls > 10000 → 清理 90 天前的条目
    ├── 写 seen_urls.json
    └── 写 digest_history.json
    │
GitHub Actions → git add data/ → git commit → git push
```

### 6.3 状态依赖关系

```
去重器  ←── seen_urls.json
策展器  ←── (无状态依赖，仅依赖 LLM API)
排序器  ←── (无状态依赖)
月报    ←── curated_archive/ (30 天历史数据)
```

---

## 7. 邮件渲染链路

### 7.1 模板继承关系

```
base.html (共享布局)
├── <style> inline CSS
├── Header: title_tag + 日期
├── {% block content %}
└── Footer: Generated by... + Unsubscribe

    daily.html (extends base)
    ├── 🔌 可直接安装/使用 (installable section)
    │   ├── [mcp_server] ★★★★☆
    │   │   ├── chinese_title + summary
    │   │   ├── 💡 recommendation_reason
    │   │   ├── 📦 install_command
    │   │   └── 🔗 原文链接
    │   └── [claude_skill] / [coding_tool] 同格式
    │
    ├── 📊 技术与趋势 (tech_items section)
    │   └── [agent_framework] / [model_release] / [guide] 紧凑格式
    │
    └── 📊 今日统计 (stats footer)

    weekly.html (extends base)
    ├── 📈 本周趋势速览 (trend_summary)
    ├── 📦 本周新上架工具 (installable)
    ├── 🏆 本周最高评分 (top_rated: 3 items)
    ├── 📊 技术与趋势 (tech_items)
    └── 📊 分类分布 (content_type bar chart)
    
    monthly.html (extends base)
    ├── 📊 月度趋势报告 (trend_analysis full text)
    ├── 📋 本月高分 Top 10
    ├── 📦 本月新工具汇总
    └── 📊 分类统计
```

### 7.2 Composer → Template 数据映射

```python
composer.compose_daily(articles, total_fetched, cost_rmb, ...)
    │
    ├── items_data = [_item_to_template_data(a) for a in articles]
    │   └── {chinese_title, chinese_summary, content_type, 
    │        content_type_label, categories, importance_score,
    │        weighted_score, recommendation_reason,
    │        install_command, url, source_label}
    │
    ├── installable = [d for d if content_type ∈ INSTALLABLE_TYPES]
    ├── tech_items  = [d for d if content_type ∈ TECH_TYPES]
    │
    ├── stats = {total_fetched, curated_count, installable_count,
    │            framework_count, tech_count, cost_rmb, auxiliary_matches}
    │
    └── template.render(installable=..., tech_items=..., stats=...)
        → html_body
```

---

## 8. 部署与调度

### 8.1 运行环境

```
GitHub Actions Ubuntu Runner
├── Python 3.12
├── pip install requirements.txt
├── 可用 Secrets 11 个
├── 权限: contents: write (push data/)
├── 超时: daily 30min / weekly 45min / monthly 60min
└── 防重复: concurrency group
```

### 8.2 调度时间线

```
UTC 时间        北京时间      事件
──────────     ─────────     ──────────────
00:00          08:00         
...
08:00          16:00 ─── 日刊 cron 触发
                        python -m src.main --mode daily
                        
09:00 (周一)   17:00 ─── 周刊 cron 触发  
                        python -m src.main --mode weekly
                        
10:00 (1日)    18:00 ─── 月刊 cron 触发
                        python -m src.main --mode monthly
```

### 8.3 为什么是下午 4 点

美国 AI 圈活跃时间（Pacific Time 夜间到早晨）对应北京时间凌晨到上午。下午 4 点推送能把当天美国夜间发布的信息 + 国内白天信息都收全。

---

## 9. 可优化节点清单

### 9.1 内容质量优化

| 节点 | 现状 | 优化方向 | 改动位置 |
|------|------|---------|---------|
| **策展 prompt** | 通用中文 prompt | 添加"忽略公关稿/低质翻译"等负向规则 | `config/prompts.yaml` → `system_prompt` |
| **评分差异化** | 多数评 3-4 分 | 收紧评分标准，强制 1-5 均匀分布 | `config/prompts.yaml` → `importance_guide` |
| **去重漏网** | 仅批次内模糊匹配 | 加入 seen_urls 的标题向量索引，跨天去重 | `src/curator/deduplicator.py` |
| **机器之心抓取** | JS 渲染页面，爬虫效果差 | 用 playwright/puppeteer 等 headless browser | `src/aggregator/rss_fetcher.py` |
| **分类准确度** | LLM 有时分错 | 添加 few-shot examples 到 prompt | `config/prompts.yaml` → `content_type_guide` |

### 9.2 工具发现优化

| 节点 | 现状 | 优化方向 | 改动位置 |
|------|------|---------|---------|
| **PulseMCP** | 页面爬虫不稳定 | PulseMCP 已开放 API，申请 API key 接入 | `src/aggregator/mcp_pulse.py` |
| **GitHub MCP topic** | 已砍掉 | 重新加入，用 `github.com/topics/mcp` + GitHub API | 新建 `github_topics.py` |
| **Ollama** | 没接入 | 接入 Ollama 新模型通知 | `src/aggregator/oss_models.py` |
| **GitHub Trending 覆盖** | 仅 Python/JS | 检查 description 匹配关键词，语言覆盖偏窄 | `config/sources.yaml` → `ai_keywords` |

### 9.3 性能与成本优化

| 节点 | 现状 | 优化方向 | 改动位置 |
|------|------|---------|---------|
| **LLM 模型** | DeepSeek V3 (~¥1/月) | 切 DeepSeek V2.5 或 Qwen3-72B 更便宜 | `LLM_MODEL` secret |
| **并发抓取** | 全等最慢源 | 流式处理：先完成的先进入下游 | `src/main.py` → `run_digest()` |
| **去重速度** | O(n²) fuzzy 比较 | 对长文章 (>100字) 只比较前 50 字符 | `src/curator/deduplicator.py` |
| **缓存 LLM 结果** | 无缓存 | 相同 title+source 的条目缓存策展结果 | 新建 `src/curator/cache.py` |

### 9.4 邮件体验优化

| 节点 | 现状 | 优化方向 | 改动位置 |
|------|------|---------|---------|
| **邮件样式** | inline CSS | 迁移到更现代的邮件框架 (MJML) | `src/digest/templates/` |
| **日报长度** | 固定 8 条 | 根据当天信息密度动态调整 (5-12) | `src/curator/ranker.py` |
| **个性化标记** | 无 | 标记哪些是"本周新出现"的 tools | `src/digest/composer.py` |
| **暗黑模式** | 基础适配 | 完整 dark mode 测试 + `prefers-color-scheme` | `base.html` |

### 9.5 工程健壮性

| 节点 | 现状 | 优化方向 | 改动位置 |
|------|------|---------|---------|
| **源失败监控** | 仅日志 | 连续 3 天失败自动发告警 issue | `.github/workflows/` |
| **LLM fallback** | 无 | 主模型不可用时自动切备用模型 | `src/curator/llm_client.py` |
| **域名配置** | 测试地址 | 切换到自定义域名 `digest@xxx.com` | GitHub Secrets |
| **测试覆盖** | 15 个去重+排序测试 | 扩充聚合器 mock 测试、集成测试 | `tests/` |
