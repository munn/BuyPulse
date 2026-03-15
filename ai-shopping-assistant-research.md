# AI购物助手产品调研与规划文档

> 最后更新：2026-03-14
> 用途：供Claude Code后续开发参考

---

## 一、产品定位与关键决策

### 愿景
全能AI购物助手平台，覆盖deal推送、新品推荐、产品咨询、价格监控等全场景。

### V1切入点
**Amazon价格监控 + 降价提醒**（Telegram Bot形态）

### 关键决策记录
| 决策项 | 选择 | 备注 |
|--------|------|------|
| 目标市场 | 美国市场优先 | 后续考虑中国市场 |
| 商业模式 | CPS佣金（联盟分成）为主 | Amazon Associates |
| 核心用户 | 通用型，所有人 | V1不限定族裔/人群 |
| 团队 | 一个人 + Claude Code | |
| 电商平台 | 先只做Amazon | 后续扩展 |
| 价格数据 | **CCC图表图片分析（已验证）** | 不爬页面，下载图表PNG做OCR |
| Phase 1重点 | **先建爬虫体系** | Bot是Phase 2 |

---

## 二、Phase 1：爬虫体系（当前重点）

### 目标
建立自有的Amazon商品历史价格数据库，不依赖任何第三方API。

### 数据采集方案（2026-03-15 验证）

#### 核心发现：CCC图表是服务器端渲染的PNG图片
- CCC产品页面（camelcamelcamel.com）有Cloudflare强保护+CAPTCHA
- 但**图表图片服务**（charts.camelcamelcamel.com）保护很弱
- 不需要Playwright/浏览器渲染，纯HTTP GET即可

#### 图表图片URL格式
```
https://charts.camelcamelcamel.com/us/{ASIN}/amazon-new-used.png?force=1&zero=0&w=2000&h=800&desired=false&legend=1&ilt=1&tp=all&fo=0
```
- chart-type: `amazon`, `new`, `used`, `amazon-new`, `amazon-new-used` 等
- tp: `all`(全部历史), `3m`, `6m`, `1y`
- w/h: 自定义尺寸（实际返回2x，如w=2000返回3200px）

#### 图表内含数据
- 价格曲线（Amazon自营/第三方新品/第三方二手）
- **图例文字（OCR可提取精确值）**：最低价+日期、最高价+日期、当前价+日期
- 产品完整名称
- Y轴价格刻度、X轴时间刻度

#### 反爬测试结果
| 测试项 | 结果 |
|--------|------|
| Cloudflare | 有，但仅轻量保护 |
| robots.txt | `Allow: /`（允许爬取） |
| UA过滤 | `python-requests`/`Go-http-client`→403；`httpx`/`aiohttp`/`curl`→200 |
| 浏览器UA | 403（TLS指纹不匹配被检测为伪装） |
| 频率限制 | burst 5个后429；1 req/s稳定通过；429恢复需~60s |
| CAPTCHA | 无 |
| JS Challenge | 无 |

#### 技术选型（更新后）

**数据采集**：Python httpx/aiohttp（不需要Crawl4AI/Playwright）
- 异步HTTP下载PNG图片
- 像素分析：追踪曲线颜色(绿/蓝/红)提取完整价格时间序列（所有拐点）
- 图例OCR：提取最低/最高/当前价+日期，用于校验
- 原始PNG图片存储到磁盘（备查+可重新解析）

**代理IP**：初期可能不需要
- 单IP 1 req/s = 86,400 ASIN/天
- 规模化后用Decodo并行加速

**运行环境**：Hetzner US VPS（CPX22, ~$8-10/月）
- 先用Hetzner试水，代码成熟后横评Contabo/DO/Vultr
- 2vCPU/4GB RAM/40GB SSD，美国Virginia机房

**数据库**：PostgreSQL（同一台VPS）

**当前价格**：Amazon Creators API（PA-API后继）
- 免费，需Associates账号+30天内10笔销售
- 2026年5月前必须从PA-API迁移
- 价格数据最多缓存24小时（Associates协议）

#### 数据采集流程（更新后）
```
ASIN种子库（Amazon畅销榜）
    ↓
请求调度器（≤1 req/s per IP）
    ↓
HTTP GET → charts.camelcamelcamel.com（图表PNG）
    ↓
保存原始PNG到磁盘
    ↓
像素分析 → 提取完整价格时间序列（所有拐点）
  ├── OCR Y轴标签 → 像素↔价格映射
  ├── OCR X轴标签 → 像素↔日期映射
  └── 逐列追踪颜色 → (date, price) 序列
    ↓
图例OCR → 最低/最高/当前价（校验用）
    ↓
存入PostgreSQL（price_history + price_summary）
```

#### 数据库核心表
- **products** — ASIN基本信息 + CCC图片存储路径
- **price_history** — 从图表提取的完整价格时间序列（每个拐点一行）
- **price_summary** — 图例OCR的最低/最高/当前值（快速查询+校验）
- **daily_snapshots** — Phase 2+ 自建积累（Creators API每日价格）

**后期补充：**
- Amazon Creators API — 实时当前价格（合规）
- CCC RSS Feed `/top_drops/feed` — Top 20降价商品（结构化XML）
- Slickdeals/DealNews — 促销事件

### 数据更新策略
- 热门（Top 1万）：每天
- 一般（1-10万）：每周
- 长尾（10万+）：按需（用户查询触发）

### 安全原则
- 爬虫与affiliate账号**完全隔离**（不同IP/域名/主体）
- 控制请求速率，对目标站友好
- 对方要求停止就停

### 规模估算（更新后）
- 先抓Top 50万热门ASIN
- 每张图表PNG约50-65KB，总计约25-32GB
- 单IP 1 req/s → ~6天爬完；3个代理IP并行 → ~2天
- 初期无代理成本，规模化后Decodo ~$2.20/GB

### Phase 1 开发步骤（更新后）
1. 购买Hetzner US VPS + 安装PostgreSQL
2. 设计数据库schema
3. 写CCC图表下载器 + OCR提取器
4. 小规模测试（100 ASIN）
5. 构建ASIN种子库（Amazon畅销榜）
6. 规模化爬取（考虑代理IP并行）
7. 数据质量验证
8. VPS横评（Contabo/DO/Vultr）

---

## 三、AI爬虫工具调研

### AI原生框架

| 工具 | 类型 | 价格 | 特点 | 推荐度 |
|------|------|------|------|--------|
| **Crawl4AI** | 开源自托管 | 免费 | Python/Playwright，58K星 | ⭐⭐⭐ |
| Firecrawl | 商业SaaS | $16/月起 | 最成熟，YC背景 | ⭐⭐ |
| Jina Reader | 免费API | 免费100万token | 最简单，r.jina.ai/前缀 | ⭐ |
| ScrapeGraphAI | 开源 | 免费+LLM费 | 自然语言驱动 | ⭐ |
| Cloudflare /crawl | 云服务 | Workers计费 | 2026.3.10发布，太新 | ⭐ |
| Spider.cloud | 商业API | $0.48/1K页 | Rust引擎，一站式 | ⭐⭐ |

### 传统框架
- Scrapy：经典Python分布式爬虫
- Playwright/Puppeteer：浏览器自动化（Crawl4AI底层）

---

## 四、代理IP调研

### 国际（爬美国网站用）

| 服务商 | IP池 | 住宅价格 | 成功率 | 试用 | 推荐 |
|--------|------|----------|--------|------|------|
| **Decodo** | 6500万+ | ~$2.20/GB | 99.68% | 3天 | ⭐⭐⭐ |
| Bright Data | 1.5亿+ | $10.5/GB | 99%+ | 7天 | ⭐⭐ 贵 |
| Oxylabs | 1亿+ | $8-10/GB | 99.95% | 7天 | ⭐⭐ 贵 |
| IPRoyal | 较大 | 较便宜 | 好 | 无 | ⭐ |

### 国内（爬国内网站时用）

| 服务商 | 价格 | 特点 |
|--------|------|------|
| 辣椒HTTP | 静态9.9元/月起，动态5元/GB起 | 评测排名高 |
| 快代理 | 中等 | 600万+IP，业务分池 |
| 青果网络 | 0.003元/个 | 存活率99% |

---

## 五、Amazon合规要点

### 绝对不能做
- **不能直接爬Amazon.com** — Associates协议明确禁止data mining/robots，违反即封号
- **不能长期存储PA-API/Creators API价格数据** — 协议要求最多缓存24小时
- **不能伪装浏览器UA爬取** — Cloudflare TLS指纹检测会识别

### 合规获取当前价格：Creators API
- PA-API 5.0 将于2026年5月废弃，需迁移到Creators API（OAuth 2.0）
- 免费使用，但需要Associates账号+过去30天内至少10笔shipped sales
- 初始限额：1 TPS / 8,640 TPD → 批量查询可达86,400 ASIN/天
- 收入越高限额越大

### 历史价格数据的合规路径
- CCC图表图片分析（当前方案）— 图表服务robots.txt允许，技术上可行
- 自建积累 — 每天用Creators API查当前价格，日积月累形成历史数据
- Keepa API（备选）— €49/月，完整历史数据，合规

### 风险评估
| 行为 | 风险等级 | 后果 |
|------|---------|------|
| 爬Amazon.com | 极高 | Associates封号、法律风险 |
| 爬CCC产品页面 | 中等 | IP被封、CAPTCHA |
| 下载CCC图表PNG | 低 | 可能加强保护 |
| 用Creators API | 无 | 合规 |

---

## 六、多平台渠道策略

### 美国私域
- **Telegram Bot** — V1主阵地，API完全开放，免费
- WhatsApp — 西语用户，需opt-in
- Discord — 社群补充
- Web App — 自有阵地

### 美国引流
- X：被动回复+deal播报
- Instagram：DM自动回复+Reels
- Reddit：内容引导到私域
- Pinterest：产品Pin+SEO

### 中国私域
- 企业微信（最稳妥）+ 公众号 + 小程序

### 中国引流
- 小红书/抖音/快手/B站

### 中国CPS
- 淘宝联盟/京东联盟/多多进宝

---

## 六、开发优先级

### Phase 1：价格数据采集 ← 当前
### Phase 2：Telegram Bot MVP
### Phase 3：功能扩展（AI咨询/deal推送/多平台）

---

## 七、成本估算（更新后）

| 项目 | Phase 1 | Phase 2+ |
|------|---------|----------|
| VPS (Hetzner US) | ~$8-10/月 | 可能需要第二台 |
| 代理IP (Decodo) | 初期不需要 | ~$10-30/月（按需） |
| Telegram Bot API | - | 免费 |
| Amazon Creators API | - | 免费（需10笔/月销售） |
| Claude API | - | $20-50/月 |
| **总计** | **~$10/月** | **~$40-90/月** |

> 相比原方案（$70-135/月）大幅降低，主要因为不需要Playwright和代理IP。
