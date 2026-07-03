# 🤖 AI Information Collection

AI 信息聚合推送系统 — 自动从 12 个信息源抓取最新 AI 资讯和工具，经 LLM 深度策展后通过邮件推送。

## 核心功能

- **多源聚合**：GitHub Trending、HuggingFace Papers、RSS（量子位/机器之心）、Product Hunt、Hacker News、PulseMCP、Claude Plugins、框架更新、AI 编程工具 Changelog、开源模型发布、官方博客指南
- **深度策展**：LLM 对每篇文章生成中文摘要、内容类型标签、重要性评分（1-5）、个性化推荐理由
- **智能排序**：可直接安装的工具（MCP/Skill/CodingTool）自动加权+1，确保优先展示
- **三种推送**：日刊（8条）、周刊（18条+趋势分析）、月刊（全量+趋势报告）
- **成本极低**：约 ¥0.50-1.00/月（DeepSeek V3 API + Resend 免费邮件 + GitHub Actions 免费）
- **零运维**：GitHub Actions 定时触发，状态自动 git commit，无需服务器

## 快速开始

### 1. Fork 本仓库

### 2. 配置 Secrets

在 GitHub 仓库的 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 |
|--------|------|
| `LLM_API_KEY` | DeepSeek API Key（[获取](https://platform.deepseek.com)） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | `deepseek-chat` |
| `SMTP_HOST` | `smtp.resend.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USERNAME` | Resend SMTP 用户名（[获取](https://resend.com)） |
| `SMTP_PASSWORD` | Resend API Key |
| `EMAIL_FROM` | 发件人地址（需在 Resend 验证） |
| `EMAIL_TO` | 收件人地址（你的邮箱） |
| `PH_DEV_TOKEN` | Product Hunt API Token（可选，[获取](https://producthunt.com)） |
| `GITHUB_TOKEN` | GitHub Personal Token（可选，提高 API 限流） |

### 3. 启用 Workflows

仓库默认不启用定时任务。进入 **Actions** 标签页，启用以下 workflow：
- `Daily AI Digest`
- `Weekly AI Digest`
- `Monthly AI Trend Report`

### 4. 手动测试

进入 **Actions → Manual Test Run → Run workflow**，选择 `daily` 模式 + `dry_run=true`，检查输出质量。

## 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 逐源测试（dry-run，不发送邮件）
python -m src.main --mode daily --dry-run --verbose

# 查看生成的 HTML
# macOS/Linux: open /tmp/digest-daily-*.html
# Windows: start C:\Users\xxx\AppData\Local\Temp\digest-daily-*.html

# 运行测试
pytest
```

## 项目结构

```
├── .github/workflows/     # GitHub Actions 定时任务
├── src/
│   ├── main.py            # CLI 入口 + 流水线编排
│   ├── config.py          # YAML 配置加载
│   ├── aggregator/        # 12 个信息源抓取器
│   ├── curator/           # LLM 策展流水线
│   │   ├── models.py      # 数据模型
│   │   ├── deduplicator.py # 四级去重
│   │   ├── llm_client.py  # LLM 客户端
│   │   ├── processor.py   # 批量策展
│   │   └── ranker.py      # 排序加权
│   ├── digest/            # 邮件组合与发送
│   │   ├── composer.py    # Jinja2 渲染
│   │   ├── sender.py      # SMTP 发送
│   │   └── templates/     # HTML 邮件模板
│   └── state/             # 状态持久化
│       ├── manager.py     # JSON 文件读写
│       └── schema.py      # 状态模型
├── config/                # YAML 配置（源、分类、提示词）
├── data/                  # 运行时状态（自动 git commit）
└── tests/                 # 单元测试
```

## 定制指南

### 添加信息源

编辑 `config/sources.yaml`，参考已有源的格式添加新源：

```yaml
sources:
  my_new_source:
    enabled: true
    priority: "core"       # core | degraded | auxiliary
    url: "https://..."
```

然后在 `src/aggregator/` 中实现对应的 `SourceProtocol` 子类，在 `src/main.py` 的 `create_all_aggregators()` 中注册。

### 调整 LLM 策展风格

编辑 `config/prompts.yaml`，修改 `system_prompt`、`importance_guide`、`batch_curation` 等字段。

### 调整推送频率 & 数量

编辑 `src/config.py` 中的默认值或 `.github/workflows/*.yml` 中的 cron 表达式。

## 降噪设计

| 策略 | 说明 |
|------|------|
| **三级优先度** | core（全参与）→ degraded（加质量过滤）→ auxiliary（仅交叉验证） |
| **HuggingFace Papers** | 只推有 Papers with Code 链接 + GitHub ≥ 500 star 的论文 |
| **Hacker News** | 只抓 score > 100 的帖子，过滤 Ask HN/招聘帖 |
| **TechCrunch** | 标记为辅助源，不计入推送配额 |
| **四级去重** | URL 精确 → URL 规范化 → 标题模糊 → 跨源引用提取 |

## License

MIT
