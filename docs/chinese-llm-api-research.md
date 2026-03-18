# 中国大模型 API 调研报告

> 调研日期：2026-03-17
> 用途：替代 Claude Haiku 完成 Telegram Bot 中两个简单 NLP 任务
> 1. **搜索意图提取**："AirPods Pro 多少钱？" → 提取 "AirPods Pro"
> 2. **语言检测**：判断消息是英文还是西班牙文（仅2种语言）

## 核心结论

**推荐方案：Qwen3.5-Flash（通过阿里云 DashScope API）**

理由一句话：**¥0.2/百万token 输入 + ¥2/百万token 输出，OpenAI 兼容 API，有海外节点（新加坡/弗吉尼亚），注册送100万 token 免费额度，英文能力强。** 对于搜索意图提取和语言检测这两个极简任务，每次调用约消耗 100-200 token，1000次调用成本约 ¥0.04（不到1分钱），完全够用。

**备选方案：**
- **免费方案**：通过 OpenRouter 使用 StepFun Step-3.5-Flash:free 或 MiniMax M2.5:free（完全免费，但有速率限制）
- **极致便宜**：DeepSeek Chat（¥0.2/百万 input，¥3/百万 output），但服务偶有拥堵
- **统一网关**：SiliconFlow 聚合多家模型，免费模型可选 Qwen3.5-4B / DeepSeek-R1-Distill-7B

---

## 一、各厂商详细调研

### 1. DeepSeek（深度求索）

| 项目 | 详情 |
|------|------|
| **最新模型** | deepseek-chat (DeepSeek-V3.2)，deepseek-reasoner (V3.2 思考模式) |
| **定价（官方）** | 输入：¥0.2/百万token（缓存命中），¥2/百万token（缓存未命中）；输出：¥3/百万token |
| **定价（USD 换算）** | 输入：$0.028-$0.28/M；输出：$0.42/M |
| **免费额度** | 新注册有赠送余额（具体金额需注册查看，历史上为 ¥10-50） |
| **API 兼容** | ✅ OpenAI 兼容，base_url: `https://api.deepseek.com` |
| **速率限制** | 官方声明"不限制用户速率"，尽力服务每个请求 |
| **海外可用性** | ✅ 美国服务器可调用，无地域限制 |
| **英文能力** | 优秀，V3 系列英文能力接近 GPT-4 级别 |
| **延迟** | 高峰期可能排队，非高峰响应快（<2秒短查询） |
| **优点** | 价格极低，英文强，OpenAI 兼容 |
| **缺点** | 高峰期服务不稳定，偶有排队/超时；685B 模型对简单任务过于"重量级" |

### 2. 阿里云通义千问 (Qwen) ⭐ 推荐

| 项目 | 详情 |
|------|------|
| **最新模型** | Qwen3.5-Flash, Qwen3.5-Plus, Qwen3-Max, Qwen-Turbo, Qwen-Long |
| **最便宜模型** | **qwen-flash**: ¥0.15/M 输入, ¥1.5/M 输出（最低价）<br>**qwen3.5-flash**: ¥0.2/M 输入, ¥2/M 输出（推荐，效果更好） |
| **其他定价** | qwen-turbo: ¥0.3/M 输入, ¥0.6/M 输出（非思考模式）<br>qwen-long: ¥0.5/M 输入, ¥2/M 输出 |
| **免费额度** | ✅ 每个模型送 100万 token，90天有效 |
| **API 兼容** | ✅ OpenAI 兼容，base_url: `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **海外节点** | ✅ 新加坡: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`<br>✅ 弗吉尼亚（美国）节点也有 |
| **速率限制** | 未在文档中明确标注（按账户等级递增） |
| **英文能力** | 优秀，Qwen3.5 系列多语言能力强 |
| **延迟** | 阿里云基础设施稳定，短查询 <1秒 |
| **优点** | 最便宜之一、稳定、有海外节点、OpenAI 兼容、免费额度慷慨 |
| **缺点** | 海外节点价格比国内贵 3-4 倍 |

### 3. 智谱 GLM (Z.ai)

| 项目 | 详情 |
|------|------|
| **最新模型** | GLM-5, GLM-5-Turbo, GLM-4.7, GLM-4.7-Flash |
| **定价（OpenRouter）** | GLM-4.7-Flash: $0.06/M 输入, $0.40/M 输出（约 ¥0.43/M, ¥2.9/M）<br>GLM-5-Turbo: $0.96/M 输入, $3.20/M 输出 |
| **官方定价（推测）** | GLM-4-Flash 历史上曾免费，4.7-Flash 价格极低 |
| **免费额度** | GLM-4-Flash 曾经完全免费，当前状态需确认 |
| **API 兼容** | ✅ OpenAI 兼容，base_url: `https://api.z.ai/api/paas/v4`（新加坡） |
| **海外可用性** | ✅ 通过 Z.ai（新加坡节点），全球可用 |
| **英文能力** | 良好，GLM-4.7 系列针对编程和 Agent 优化 |
| **延迟** | Flash 模型针对速度优化，短查询 <1秒 |
| **优点** | Flash 模型极便宜，有全球节点 |
| **缺点** | 官网需 JS 渲染，文档获取不便；品牌知名度不如 Qwen |

### 4. 百度文心 ERNIE

| 项目 | 详情 |
|------|------|
| **最新模型** | ERNIE 4.0, ERNIE-Speed, ERNIE-Lite, ERNIE-Tiny |
| **定价** | ERNIE-Speed: 曾免费（2024年），当前需确认<br>ERNIE-Lite: 曾免费<br>ERNIE-Tiny: 曾免费<br>ERNIE 4.0: ¥30/M 输入 |
| **免费额度** | 历史上 Speed/Lite/Tiny 完全免费，2026年政策需确认 |
| **API 兼容** | ❌ 不是 OpenAI 兼容格式，需用百度自有 SDK |
| **海外可用性** | ⚠️ 主要面向国内，海外访问不稳定 |
| **英文能力** | 中等，以中文为主 |
| **优点** | 历史上有免费模型 |
| **缺点** | API 不兼容 OpenAI、海外不友好、文档混乱（URL 重定向）、英文能力偏弱 |
| **结论** | ❌ 不推荐。API 不兼容 + 海外不稳定 = 集成成本高 |

### 5. Moonshot 月之暗面 (Kimi)

| 项目 | 详情 |
|------|------|
| **最新模型** | Kimi-K2.5（2026年1月发布） |
| **定价（OpenRouter）** | $0.45/M 输入, $2.20/M 输出（约 ¥3.2/M, ¥15.8/M） |
| **官方定价** | moonshot-v1-8k 历史定价约 ¥12/M（偏贵） |
| **免费额度** | 新注册赠 ¥15 |
| **API 兼容** | ✅ OpenAI 兼容 |
| **海外可用性** | ⚠️ 主要面向国内用户 |
| **英文能力** | 良好 |
| **优点** | 模型质量不错 |
| **缺点** | 定价偏贵，不适合"最便宜"需求 |
| **结论** | ❌ 性价比不高，远贵于 Qwen/DeepSeek |

### 6. MiniMax

| 项目 | 详情 |
|------|------|
| **最新模型** | MiniMax-M2.5（2026年2月），M2.1, M2, M1 |
| **定价（OpenRouter）** | M2.5: $0.20/M 输入, $1.20/M 输出（约 ¥1.4/M, ¥8.6/M） |
| **免费方案** | ✅ OpenRouter 上有 M2.5:free（完全免费！） |
| **API 兼容** | ✅ 通过 OpenRouter 使用 OpenAI 兼容格式 |
| **海外可用性** | ✅ 通过 OpenRouter 全球可用 |
| **英文能力** | 良好，多语言支持 |
| **优点** | 有免费版本，模型质量高（SWE-Bench 80.2%） |
| **缺点** | 免费版可能有速率限制；直接用官方 API 文档不够清晰 |

### 7. SiliconFlow 硅基流动

| 项目 | 详情 |
|------|------|
| **定位** | 统一 API 网关，聚合多家模型 |
| **免费模型** | Qwen3.5-4B, DeepSeek-R1-Distill-Qwen-7B, 多个 Qwen/GLM 变体 |
| **付费定价** | ¥0.35 ~ ¥22/百万token（按模型大小） |
| **速率限制** | 6档，RPM 500-10,000，TPM 2,000-5,000,000 |
| **API 兼容** | ✅ OpenAI 兼容 |
| **海外可用性** | ✅ 有国际版 cloud.siliconflow.cn |
| **优点** | 一个 API Key 用多个模型，有免费模型 |
| **缺点** | 免费模型较小（4B/7B），复杂任务准确率可能不够 |
| **适用场景** | 适合试验多个模型、快速切换 |

### 8. 字节跳动豆包 (ByteDance Doubao/Seed)

| 项目 | 详情 |
|------|------|
| **最新模型** | Seed-2.0-Mini, Seed-2.0-Lite, Seed-1.6, Seed-1.6-Flash |
| **定价（OpenRouter）** | Seed-1.6-Flash: $0.075/M 输入, $0.30/M 输出（约 ¥0.54/M, ¥2.15/M）<br>Seed-2.0-Mini: $0.10/M 输入, $0.40/M 输出 |
| **官方定价** | 通过火山方舟平台，具体定价因 JS 渲染无法直接获取 |
| **API 兼容** | ✅ OpenAI 兼容（通过 BytePlus 国际版） |
| **海外可用性** | ✅ BytePlus 新加坡节点，通过 OpenRouter 全球可用 |
| **英文能力** | 良好，Seed 系列多语言 |
| **优点** | 价格有竞争力，Seed-1.6-Flash 针对低延迟优化 |
| **缺点** | 品牌/文档不如 Qwen/DeepSeek 成熟 |

### 9. 01.AI 零一万物 (Yi)

| 项目 | 详情 |
|------|------|
| **状态** | ⚠️ 2025年后逐渐淡出独立 API 市场 |
| **最新模型** | Yi-Lightning（可能已停更） |
| **定价** | 历史定价较便宜，当前 API 服务状态不明 |
| **API 兼容** | ✅ OpenAI 兼容 |
| **结论** | ❌ 不推荐。服务持续性不确定，OpenRouter 上已无 Yi 模型 |

### 10. 阶跃星辰 StepFun

| 项目 | 详情 |
|------|------|
| **最新模型** | Step-3.5-Flash, Step-3, Step-2-mini |
| **定价（官方）** | Step-3.5-Flash: ¥0.7/M 输入, ¥2.1/M 输出<br>Step-2-mini: ¥1/M 输入, ¥2/M 输出 |
| **免费方案** | ✅ Step-3.5-Flash 在 OpenRouter 上有完全免费版本！50 RPM |
| **API 兼容** | ✅ OpenAI 兼容 |
| **海外可用性** | ✅ 通过 OpenRouter 全球可用 |
| **英文能力** | 良好 |
| **速率限制** | 官方 V0 免费档：5并发，10 RPM；OpenRouter 免费版：50 RPM |
| **优点** | 有完全免费版本，196B MoE 模型（仅激活 11B）速度快 |
| **缺点** | 免费版有速率限制 |

---

## 二、价格对比总表（按价格从低到高排序）

> 价格单位：每百万 token，汇率按 $1 = ¥7.2 换算

| 排名 | 厂商/模型 | 输入价格 (¥) | 输出价格 (¥) | 输入价格 ($) | 输出价格 ($) | 1000次调用成本* | 免费额度 |
|------|-----------|-------------|-------------|-------------|-------------|---------------|---------|
| 🆓 | **StepFun Step-3.5-Flash:free** (OpenRouter) | ¥0 | ¥0 | $0 | $0 | ¥0 | 完全免费 |
| 🆓 | **MiniMax M2.5:free** (OpenRouter) | ¥0 | ¥0 | $0 | $0 | ¥0 | 完全免费 |
| 🆓 | **DeepSeek Chat:free** (OpenRouter) | ¥0 | ¥0 | $0 | $0 | ¥0 | 完全免费 |
| 🆓 | **SiliconFlow 免费模型** (Qwen3.5-4B等) | ¥0 | ¥0 | $0 | $0 | ¥0 | 完全免费 |
| 1 | **Qwen-Flash** (阿里云直连) | ¥0.15 | ¥1.5 | $0.021 | $0.21 | ¥0.025 | 100万token/90天 |
| 2 | **Qwen3.5-Flash** (阿里云直连) | ¥0.2 | ¥2 | $0.028 | $0.28 | ¥0.034 | 100万token/90天 |
| 3 | **DeepSeek Chat** (官方, 缓存命中) | ¥0.2 | ¥3 | $0.028 | $0.42 | ¥0.044 | 注册赠送 |
| 4 | **Qwen-Turbo** (阿里云直连) | ¥0.3 | ¥0.6 | $0.042 | $0.083 | ¥0.014 | 100万token/90天 |
| 5 | **Qwen3.5-9B** (OpenRouter) | ¥0.36 | ¥1.08 | $0.05 | $0.15 | ¥0.020 | - |
| 6 | **GLM-4.7-Flash** (OpenRouter) | ¥0.43 | ¥2.88 | $0.06 | $0.40 | ¥0.044 | - |
| 7 | **Qwen-Long** (阿里云直连) | ¥0.5 | ¥2 | $0.069 | $0.28 | ¥0.034 | 100万token/90天 |
| 8 | **ByteDance Seed-1.6-Flash** (OpenRouter) | ¥0.54 | ¥2.16 | $0.075 | $0.30 | ¥0.036 | - |
| 9 | **StepFun Step-3.5-Flash** (官方付费) | ¥0.7 | ¥2.1 | $0.10 | $0.30 | ¥0.037 | - |
| 10 | **ByteDance Seed-2.0-Mini** (OpenRouter) | ¥0.72 | ¥2.88 | $0.10 | $0.40 | ¥0.048 | - |
| 11 | **MiniMax M2.5** (OpenRouter 付费) | ¥1.44 | ¥8.64 | $0.20 | $1.20 | ¥0.13 | - |
| 12 | **StepFun Step-2-mini** (官方) | ¥1 | ¥2 | $0.14 | $0.28 | ¥0.04 | - |
| 13 | **DeepSeek Chat** (OpenRouter) | ¥2.3 | ¥6.4 | $0.32 | $0.89 | ¥0.12 | - |
| 14 | **Moonshot Kimi-K2.5** (OpenRouter) | ¥3.24 | ¥15.84 | $0.45 | $2.20 | ¥0.25 | - |

> *1000次调用成本假设：每次调用平均 100 token 输入 + 50 token 输出（搜索意图提取/语言检测的典型消耗）

### 成本分析

你的两个任务（搜索意图提取 + 语言检测）每次调用大约消耗：
- **输入**：~100 token（用户消息 + system prompt）
- **输出**：~20-50 token（提取的关键词或语言标签）

按每天处理 1000 条消息计算：
- **免费方案**：¥0/月
- **Qwen3.5-Flash**：约 ¥1/月
- **DeepSeek Chat**：约 ¥1.3/月
- **Claude Haiku 对比**：$0.25/M 输入 + $1.25/M 输出 ≈ ¥3/月

**结论：任何一个中国模型都比 Claude Haiku 便宜 3-10 倍。**

---

## 三、综合评估矩阵

| 评估维度 | Qwen3.5-Flash ⭐ | DeepSeek Chat | StepFun Free | MiniMax Free | GLM-4.7-Flash |
|---------|-----------------|---------------|--------------|-------------|---------------|
| **价格** | ★★★★★ | ★★★★★ | ★★★★★+ | ★★★★★+ | ★★★★☆ |
| **稳定性** | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | ★★★★☆ |
| **英文能力** | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| **API兼容** | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★★ |
| **海外可用** | ★★★★★ | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★★☆ |
| **文档质量** | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ |
| **速率限制** | 宽松 | 无限制 | 50 RPM | 未知 | 未知 |
| **延迟** | <1秒 | <2秒 | <2秒 | <2秒 | <1秒 |

---

## 四、推荐方案

### 方案 A：稳定生产级（推荐）

**Qwen3.5-Flash 通过阿里云 DashScope**

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_DASHSCOPE_API_KEY",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    # 海外节点：https://dashscope-intl.aliyuncs.com/compatible-mode/v1
)

# Search intent extraction
response = client.chat.completions.create(
    model="qwen3.5-flash",
    messages=[
        {"role": "system", "content": "Extract the product name from the user's shopping query. Return ONLY the product name, nothing else."},
        {"role": "user", "content": "How much are AirPods Pro?"}
    ],
    max_tokens=50,
    temperature=0
)
# Output: "AirPods Pro"

# Language detection
response = client.chat.completions.create(
    model="qwen3.5-flash",
    messages=[
        {"role": "system", "content": "Detect the language. Reply with exactly 'en' or 'es'."},
        {"role": "user", "content": "Cuanto cuesta el iPhone?"}
    ],
    max_tokens=5,
    temperature=0
)
# Output: "es"
```

**为什么选 Qwen3.5-Flash：**
- 阿里云基础设施 = 企业级稳定性
- 有美国弗吉尼亚 + 新加坡节点，从 US VPS 调用延迟低
- ¥0.2/百万token 输入，年成本 <¥12
- OpenAI SDK 直接兼容，迁移成本零
- 100万 token 免费额度可以测试验证

### 方案 B：零成本方案

**StepFun Step-3.5-Flash:free 通过 OpenRouter**

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_OPENROUTER_KEY",
    base_url="https://openrouter.ai/api/v1",
)

response = client.chat.completions.create(
    model="stepfun/step-3.5-flash:free",
    messages=[...],
    max_tokens=50
)
```

**优点**：完全免费，196B MoE 模型质量不差
**缺点**：50 RPM 限制，OpenRouter 免费模型可能随时下线

### 方案 C：多模型 Fallback

```python
# Primary: Qwen3.5-Flash (cheapest paid, most stable)
# Fallback 1: DeepSeek Chat (if Qwen down)
# Fallback 2: StepFun Free via OpenRouter (emergency)

PROVIDERS = [
    {"base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
     "api_key": "QWEN_KEY", "model": "qwen3.5-flash"},
    {"base_url": "https://api.deepseek.com",
     "api_key": "DEEPSEEK_KEY", "model": "deepseek-chat"},
    {"base_url": "https://openrouter.ai/api/v1",
     "api_key": "OPENROUTER_KEY", "model": "stepfun/step-3.5-flash:free"},
]
```

---

## 五、评估框架

### 5.1 测试用例：搜索意图提取（10例）

| # | 输入 | 期望输出 | 难度 |
|---|------|---------|------|
| 1 | "How much are AirPods Pro?" | AirPods Pro | 简单 |
| 2 | "Find me the best price for Sony WH-1000XM5" | Sony WH-1000XM5 | 简单 |
| 3 | "Is the Samsung Galaxy S24 Ultra on sale?" | Samsung Galaxy S24 Ultra | 中等 |
| 4 | "I want to buy a Kindle Paperwhite" | Kindle Paperwhite | 简单 |
| 5 | "Show me deals on Nike Air Max 90" | Nike Air Max 90 | 简单 |
| 6 | "What's the price history of Dyson V15?" | Dyson V15 | 中等 |
| 7 | "Cheapest Bose QuietComfort headphones" | Bose QuietComfort | 中等 |
| 8 | "Track price for LEGO Star Wars Millennium Falcon 75375" | LEGO Star Wars Millennium Falcon 75375 | 复杂 |
| 9 | "AirPods Pro 2 vs AirPods 3, which is cheaper?" | AirPods Pro 2, AirPods 3 | 复杂 |
| 10 | "Any good deals today?" | (无具体商品/空) | 边界 |

### 5.2 测试用例：语言检测（10例）

| # | 输入 | 期望输出 | 说明 |
|---|------|---------|------|
| 1 | "How much are AirPods Pro?" | en | 纯英文 |
| 2 | "Cuanto cuesta el iPhone?" | es | 纯西班牙文 |
| 3 | "Find me a good deal" | en | 简单英文 |
| 4 | "Busco el mejor precio para audífonos" | es | 西班牙文+特殊字符 |
| 5 | "Price check please" | en | 极短英文 |
| 6 | "Necesito comprar una laptop nueva" | es | 西班牙文完整句子 |
| 7 | "AirPods Pro" | en | 仅产品名（英文默认） |
| 8 | "Me puedes ayudar a encontrar Sony WH-1000XM5?" | es | 西班牙文+英文产品名 |
| 9 | "What's the cheapest?" | en | 简短问句 |
| 10 | "Hola, quiero saber el precio" | es | 西班牙文日常用语 |

### 5.3 评估脚本框架

```python
import time
import json
from openai import OpenAI

# Test cases
INTENT_TESTS = [
    {"input": "How much are AirPods Pro?", "expected": "AirPods Pro"},
    {"input": "Find me the best price for Sony WH-1000XM5", "expected": "Sony WH-1000XM5"},
    # ... more cases
]

LANG_TESTS = [
    {"input": "How much are AirPods Pro?", "expected": "en"},
    {"input": "Cuanto cuesta el iPhone?", "expected": "es"},
    # ... more cases
]

PROVIDERS = {
    "qwen3.5-flash": {
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "api_key": "YOUR_KEY",
        "model": "qwen3.5-flash"
    },
    "deepseek-chat": {
        "base_url": "https://api.deepseek.com",
        "api_key": "YOUR_KEY",
        "model": "deepseek-chat"
    },
    "stepfun-free": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "YOUR_KEY",
        "model": "stepfun/step-3.5-flash:free"
    },
    # Add more providers...
}

def evaluate_provider(provider_name, config, tests, task_type):
    """Evaluate a provider on a set of test cases."""
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    results = []
    total_input_tokens = 0
    total_output_tokens = 0

    for test in tests:
        if task_type == "intent":
            system_prompt = "Extract the product name from the user's shopping query. Return ONLY the product name, nothing else. If no specific product, return 'NONE'."
        else:
            system_prompt = "Detect the language of the message. Reply with exactly 'en' for English or 'es' for Spanish. Nothing else."

        start = time.time()
        response = client.chat.completions.create(
            model=config["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": test["input"]}
            ],
            max_tokens=50,
            temperature=0
        )
        latency = time.time() - start

        output = response.choices[0].message.content.strip()
        correct = output.lower() == test["expected"].lower()

        total_input_tokens += response.usage.prompt_tokens
        total_output_tokens += response.usage.completion_tokens

        results.append({
            "input": test["input"],
            "expected": test["expected"],
            "output": output,
            "correct": correct,
            "latency_ms": round(latency * 1000),
        })

    accuracy = sum(1 for r in results if r["correct"]) / len(results)
    avg_latency = sum(r["latency_ms"] for r in results) / len(results)

    return {
        "provider": provider_name,
        "task": task_type,
        "accuracy": f"{accuracy:.0%}",
        "avg_latency_ms": round(avg_latency),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "details": results
    }

# Run evaluation
for provider_name, config in PROVIDERS.items():
    print(f"\n=== Evaluating {provider_name} ===")
    intent_result = evaluate_provider(provider_name, config, INTENT_TESTS, "intent")
    lang_result = evaluate_provider(provider_name, config, LANG_TESTS, "lang")
    print(f"Intent: {intent_result['accuracy']} accuracy, {intent_result['avg_latency_ms']}ms avg")
    print(f"Lang:   {lang_result['accuracy']} accuracy, {lang_result['avg_latency_ms']}ms avg")
```

### 5.4 评估指标

| 指标 | 如何测量 | 合格标准 |
|------|---------|---------|
| **准确率** | 正确输出 / 总测试数 | ≥90% |
| **平均延迟** | 从发送请求到收到完整响应 | <2000ms |
| **P99 延迟** | 99分位延迟 | <5000ms |
| **每千次成本** | (输入token * 输入单价 + 输出token * 输出单价) * 1000 | <¥0.1 |
| **错误率** | API 超时/错误次数 / 总请求数 | <1% |

---

## 六、执行建议

### 立即可做：

1. **注册阿里云百炼平台**，获取 DashScope API Key + 100万免费 token
2. **注册 OpenRouter**，获取 API Key（免费模型不需要充值）
3. **注册 DeepSeek 平台**，获取 API Key + 免费赠送余额
4. **运行评估脚本**，在 3 个提供商上跑 20 个测试用例
5. **选择最优方案**，集成到 Telegram Bot

### 预估时间线：

- 注册 3 个平台：30 分钟
- 写评估脚本并跑测试：2 小时
- 集成到 Bot（替换 Claude Haiku）：1 小时
- 总计：**半天**

### 不需要做的事：

- ❌ 不需要考虑百度 ERNIE（API 不兼容 + 海外不稳定）
- ❌ 不需要考虑零一万物 Yi（服务持续性不确定）
- ❌ 不需要考虑 Moonshot（性价比不高）
- ❌ 不需要纠结选哪个——先用 Qwen3.5-Flash，不满意再换，OpenAI 兼容格式切换成本为零

---

## 七、注意事项

### 关于"思考模式"

很多新模型默认开启 thinking/reasoning 模式（带 `<think>` 标签），会大幅增加输出 token。对于搜索意图提取和语言检测这种简单任务，**务必关闭思考模式**：
- Qwen: 使用非思考模式（默认）
- DeepSeek: 使用 `deepseek-chat` 而非 `deepseek-reasoner`
- 其他：设置 `temperature=0`, `max_tokens=50` 限制输出

### 关于地域限制

从 US Hetzner VPS 调用中国大模型 API：
- **阿里云 Qwen**：✅ 有弗吉尼亚/新加坡节点，延迟低
- **DeepSeek**：✅ 全球可用，但高峰期可能慢
- **OpenRouter**：✅ 全球可用，中间商模式，稍有延迟加成
- **百度/部分国内厂商**：⚠️ 可能有访问限制或延迟高

### 关于模型选择的思考

你的两个任务（意图提取 + 语言检测）其实非常简单，甚至不需要 LLM：
- **语言检测**：可以用 `langdetect` 或 `lingua` Python 库（零成本、零延迟、离线运行）
- **意图提取**：LLM 确实更灵活，但也可以用正则 + 关键词规则处理 80% 的场景

**混合方案**：语言检测用本地库，搜索意图提取用 LLM，成本直接减半。
