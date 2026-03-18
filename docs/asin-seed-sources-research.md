# ASIN 种子库来源研究报告

> 研究日期：2026-03-17
> 目标：找到获取大量有效 Amazon ASIN 的公开来源，用于种子库建设

## 核心结论

**CamelCamelCamel top_drops 页面是唯一需要的来源**，一个来源即可满足 Phase 1 的全部种子需求。

## 一、各来源评估

### 1. CamelCamelCamel top_drops — 最佳来源

| 属性 | 详情 |
|------|------|
| URL | `https://camelcamelcamel.com/top_drops?p={page}` |
| 难度 | Easy |
| 预估数量 | **8,000-10,000 唯一 ASIN** |
| Playwright | 不需要，纯 HTTP GET |
| 封禁风险 | 低-中（Cloudflare 轻保护，curl_cffi 已验证通过） |
| ASIN 质量 | 极高 — 所有 ASIN 100% 在 CCC 上有价格历史 |

**已验证的事实：**
- 每页 20 个 ASIN，在 `/product/{ASIN}` 链接中
- 默认视图（无分类过滤）约 420 页有效内容
- 29 个分类可选，但分类过滤**只对前 3-5 页有效**，之后返回全局结果
- robots.txt **没有禁止** `/top_drops` 路径
- 使用 `curl_cffi`（Chrome TLS 指纹）可稳定访问
- 速率 1.2 req/s 安全

**最优策略：**
1. 先爬默认视图（无分类）所有页面 → ~8,400 ASIN
2. 再爬每个分类的前 5 页 → 补充 ~500-1,500 新 ASIN
3. 总耗时约 10 分钟

**分类 slug 列表（已验证）：**
```
appliances, artscraftssewing, automotive, baby, beauty, books,
cellphones, clothing, electronics, grocery, health, homekitchen,
industrial, jewelry, kindle, moviestv, music, musicalinstruments,
office, other, patio, petsupplies, shoes, software, sports,
tools, toys, videogames
```

### 2. CCC popular / most_tracked — 不可行
- 返回 **403 Forbidden**
- 有更强的 Cloudflare 保护

### 3. Keepa — 不可行
- 纯 SPA 应用（React + WebSocket）
- 静态 HTML 无任何产品数据
- 需要完整 JS 执行环境
- 有 Cloudflare 保护

### 4. Slickdeals — 低效
- 前端 JavaScript 重度渲染，静态 HTML 无 Amazon 链接
- RSS feed 返回 404
- 需要 Playwright 才能获取实际 deal 内容
- 即使能爬，Amazon 链接密度低

### 5. Amazon Best Sellers — 禁止
- 直接爬取 Amazon.com 违反 Associates 协议
- **绝对不能用**

### 6. Honey / Capital One Shopping — 不可行
- 返回 403
- 需要登录

### 7. Wirecutter (NYT) — 受限可行
- WebFetch 被 nytimes.com 封禁
- VPS 上用 httpx/curl_cffi 可能可行（需测试）
- 每篇评测文章包含 5-20 个 Amazon dp 链接
- 预估 500-2,000 ASIN（高质量编辑精选产品）
- 实现复杂度中等（需爬文章列表 + 进入每篇文章）

### 8. Reddit — 辅助来源
- JSON API：`https://www.reddit.com/r/{sub}/.json?limit=100`
- 帖子 URL 和 selftext 中包含 `amazon.com/dp/{ASIN}`
- 目标 subreddits：r/buildapcsales, r/deals, r/AmazonDeals
- 预估 1,000-3,000 ASIN
- Reddit API 限制：~60 req/min，最多翻 40 页（~1000 帖）
- 偏向 PC 硬件品类

### 9. Google Shopping — 不可行
- 需要现代浏览器渲染
- 静态访问被重定向

### 10. Woot.com（Amazon 子公司）— 低效
- 产品页使用自有 slug，不含 ASIN
- 需要额外解析获取 Amazon 链接
- 产品数量有限

### 11. Dealsplus / BigBangPrice — 不可行
- 连接被拒绝（ECONNREFUSED）
- 可能已关闭

## 二、推荐执行计划

### 第一步：CCC top_drops（必做，~10 分钟）
```bash
cd /Users/victor/claudecode/cps

# 1. 先测试 3 页确认能工作
python spikes/asin_seed_harvester.py --test

# 2. 确认 OK 后执行 smart harvest
python spikes/asin_seed_harvester.py --smart

# 3. 输出在 spikes/asin_harvest/all_asins.txt
```

### 第二步：Reddit 补充（可选，~5 分钟）
```bash
# 测试
python spikes/reddit_asin_harvester.py --test

# 全量
python spikes/reddit_asin_harvester.py --all
```

### 第三步：导入数据库
```bash
# 生成的 all_asins.txt 可直接被 SeedManager.import_from_file() 导入
# SeedManager 已支持去重和验证
```

## 三、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| CCC Cloudflare 封禁 | 中 | curl_cffi Chrome 指纹 + 1.2s 间隔 |
| CCC 结构变化 | 低 | ASIN regex 简单稳定 |
| Reddit API 限流 | 低 | 1.5s 间隔远低于限制 |
| ASIN 已过期/下架 | 低 | CCC chart API 会返回 404，下载器已处理 |
| 违反 robots.txt | 无 | top_drops 路径未被禁止 |

## 四、Spike 文件

- `/Users/victor/claudecode/cps/spikes/asin_seed_harvester.py` — CCC top_drops 爬虫
- `/Users/victor/claudecode/cps/spikes/reddit_asin_harvester.py` — Reddit 补充爬虫
