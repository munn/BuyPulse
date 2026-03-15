# CPS Project - AI Shopping Assistant

## 项目概述
Amazon价格监控+降价提醒，通过CPS佣金(Amazon Associates)变现。
历史价格数据来源：CamelCamelCamel图表图片分析；当前价格来源：Amazon Creators API（合规）。

## 核心文档
- `ai-shopping-assistant-research.md` — 完整产品调研和规划（必读）

## 当前阶段：Phase 1 — 价格数据采集
目标：通过CCC图表图片分析建立Amazon商品历史价格数据库

### 技术栈
- **数据采集**：HTTP下载CCC图表PNG + OCR/像素分析提取价格（不需要Playwright）
- **当前价格**：Amazon Creators API（PA-API后继，2026年5月前迁移）
- **代理IP**：初期可能不需要（单IP 1req/s可达86,400 ASIN/天），规模化后用Decodo
- **数据库**：PostgreSQL（价格时间序列）
- **运行环境**：Hetzner US VPS（CPX22, ~$8-10/月）先行，后续横评Contabo/DO/Vultr
- **不用家里电脑跑爬虫**，VPS为主

### 数据采集方案（已验证 2026-03-15）
- **CCC图表服务**：`charts.camelcamelcamel.com/us/{ASIN}/amazon-new-used.png`
  - 不需要Playwright，纯HTTP GET
  - robots.txt: `Allow: /`
  - 有Cloudflare但保护很轻：UA过滤 + 频率限制
  - 安全速率：1 req/s per IP（burst 5个后429，恢复需~60s）
  - UA注意：`python-requests`和`Go-http-client`被403，用`httpx`/`aiohttp`
- **数据提取（两层）**：
  - 像素分析：追踪曲线颜色提取完整价格时间序列（所有拐点）→ 存入price_history表
  - 图例OCR：提取最低/最高/当前价+日期 → 用于校验和快速查询
- **图片存储**：原始PNG保存到磁盘（备查+可重新解析）
- **不给用户展示CCC图片**，自建数据和可视化
- **不爬CCC产品页面**（Cloudflare强保护+CAPTCHA）
- **不直接爬Amazon**（保护affiliate账号，违反Associates协议）

### Amazon合规要点
- PA-API 2026年5月废弃，需迁移到Creators API（OAuth 2.0）
- 价格数据最多缓存24小时（Associates协议要求）
- 需要30天内10笔shipped sales才能访问API
- 禁止直接爬取Amazon.com

### Phase 1 步骤
1. 购买Hetzner US VPS + 安装PostgreSQL
2. 设计数据库schema
3. 写CCC图表下载器 + OCR提取器
4. 小规模测试（100 ASIN）
5. 构建ASIN种子库（Amazon畅销榜）
6. 规模化爬取（考虑代理IP并行）
7. 数据质量验证
8. VPS横评（加入Contabo/DO/Vultr对比）

### 安全原则
- 爬虫与affiliate账号完全隔离（不同IP/域名/主体）
- 控制请求速率（≤1 req/s per IP），友好爬取
- 对方要求停止就停
- 不伪装浏览器UA（避免触发Cloudflare TLS指纹检测）

## 后续阶段
- Phase 2：Telegram Bot MVP（对接价格数据库 + Creators API实时价格）
- Phase 3：AI咨询/deal推送/多平台扩展
