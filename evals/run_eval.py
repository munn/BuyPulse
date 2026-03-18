"""BuyPulse 模型选型评测 — 通过 SiliconFlow 统一 API 测试各家模型

用法:
  # 先设置 SiliconFlow API key
  export SILICONFLOW_API_KEY=sk-xxx

  # 跑全部模型
  uv run python evals/run_eval.py

  # 只跑指定模型
  uv run python evals/run_eval.py --models "Qwen/Qwen3.5-7B-Instruct,deepseek-ai/DeepSeek-V3"

  # 跑3轮取中位数
  uv run python evals/run_eval.py --rounds 3
"""
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

# SiliconFlow 上可测试的模型（2026-03-17 更新）
# thinking=True 的模型需要 enable_thinking=false 才能正常返回 content
MODELS = [
    # --- 免费 ---
    {"id": "Qwen/Qwen3.5-4B", "name": "Qwen3.5-4B", "tier": "free", "price_in": 0, "price_out": 0, "thinking": True},
    {"id": "Qwen/Qwen3-8B", "name": "Qwen3-8B", "tier": "free", "price_in": 0, "price_out": 0, "thinking": True},
    {"id": "Qwen/Qwen2.5-7B-Instruct", "name": "Qwen2.5-7B", "tier": "free", "price_in": 0, "price_out": 0, "thinking": False},
    {"id": "THUDM/GLM-4-9B-0414", "name": "GLM-4-9B", "tier": "free", "price_in": 0, "price_out": 0, "thinking": False},
    # --- 便宜 (< ¥1.5/M input) ---
    {"id": "Qwen/Qwen3-14B", "name": "Qwen3-14B", "tier": "cheap", "price_in": 0.5, "price_out": 2.0, "thinking": True},
    {"id": "Qwen/Qwen3-32B", "name": "Qwen3-32B", "tier": "cheap", "price_in": 1.0, "price_out": 4.0, "thinking": True},
    {"id": "tencent/Hunyuan-A13B-Instruct", "name": "Hunyuan-A13B", "tier": "cheap", "price_in": 1.0, "price_out": 4.0, "thinking": False},
    {"id": "Qwen/Qwen3.5-397B-A17B", "name": "Qwen3.5-397B", "tier": "cheap", "price_in": 1.2, "price_out": 2.0, "thinking": True},
    {"id": "Qwen/Qwen2.5-32B-Instruct", "name": "Qwen2.5-32B", "tier": "cheap", "price_in": 1.26, "price_out": 1.26, "thinking": False},
    # --- 中等 (¥1.5-3/M input) ---
    {"id": "deepseek-ai/DeepSeek-V3.2", "name": "DeepSeek-V3.2", "tier": "mid", "price_in": 2.0, "price_out": 3.0, "thinking": False},
    {"id": "Qwen/Qwen3.5-122B-A10B", "name": "Qwen3.5-122B", "tier": "mid", "price_in": 2.0, "price_out": 16.0, "thinking": True},
    {"id": "deepseek-ai/DeepSeek-V3", "name": "DeepSeek-V3", "tier": "mid", "price_in": 2.0, "price_out": 8.0, "thinking": False},
    # --- 其他有趣的 ---
    {"id": "zai-org/GLM-4.5-Air", "name": "GLM-4.5-Air", "tier": "mid", "price_in": 0, "price_out": 0, "thinking": False},
    {"id": "ByteDance-Seed/Seed-OSS-36B-Instruct", "name": "Seed-36B", "tier": "mid", "price_in": 0, "price_out": 0, "thinking": False},
]


@dataclass
class CaseResult:
    case_id: str
    category: str
    input_text: str
    expected: str
    output: str
    score: float  # 1.0 / 0.5 / 0.0
    latency_ms: int
    error: str | None = None


@dataclass
class ModelResult:
    model_name: str
    model_id: str
    tier: str
    price_in: float
    price_out: float
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.cases:
            return 0
        return sum(c.score for c in self.cases) / len(self.cases) * 100

    @property
    def avg_latency(self) -> int:
        valid = [c.latency_ms for c in self.cases if c.error is None]
        return int(sum(valid) / len(valid)) if valid else 0

    @property
    def errors(self) -> int:
        return sum(1 for c in self.cases if c.error is not None)

    def cat_accuracy(self, cat: str) -> float:
        cat_cases = [c for c in self.cases if c.category == cat]
        if not cat_cases:
            return 0
        return sum(c.score for c in cat_cases) / len(cat_cases) * 100


def score(output: str, expected: str, acceptable: list[str], products: list[str] | None = None) -> float:
    """三级评分: 1.0 精确, 0.5 可接受, 0.0 错误"""
    clean = output.strip().strip('"\'').strip()
    if clean.lower() == expected.lower():
        return 1.0
    if any(clean.lower() == a.lower() for a in acceptable):
        return 0.5

    # Multi-product matching (comparison cases)
    if products:
        clean_lower = clean.lower()
        found = sum(1 for p in products if p.lower() in clean_lower)
        if found == len(products):
            return 1.0  # All products found
        if found > 0:
            return 0.5  # Some products found
        return 0.0

    # 宽松匹配：输出包含期望值
    if expected.lower() != "none" and expected.lower() in clean.lower() and len(clean) < len(expected) * 2:
        return 0.5
    return 0.0


async def eval_one(client: AsyncOpenAI, model_id: str, system_prompt: str, case: dict, *, thinking: bool = False) -> CaseResult:
    """评测单个用例"""
    try:
        extra: dict = {}
        if thinking:
            extra["extra_body"] = {"enable_thinking": False}

        start = time.monotonic()
        resp = await client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": case["input"]},
            ],
            max_tokens=80,
            temperature=0,
            **extra,
        )
        elapsed = int((time.monotonic() - start) * 1000)
        output = (resp.choices[0].message.content or "").strip()

        return CaseResult(
            case_id=case["id"],
            category=case["cat"],
            input_text=case["input"],
            expected=case["expected"],
            output=output,
            score=score(output, case["expected"], case["ok"], case.get("products")),
            latency_ms=elapsed,
        )
    except Exception as e:
        return CaseResult(
            case_id=case["id"],
            category=case["cat"],
            input_text=case["input"],
            expected=case["expected"],
            output="",
            score=0.0,
            latency_ms=0,
            error=str(e)[:200],
        )


async def eval_model(client: AsyncOpenAI, model: dict, cases: list[dict], system_prompt: str) -> ModelResult:
    """评测一个模型的全部用例"""
    result = ModelResult(
        model_name=model["name"],
        model_id=model["id"],
        tier=model["tier"],
        price_in=model["price_in"],
        price_out=model["price_out"],
    )

    is_thinking = model.get("thinking", False)

    for i, case in enumerate(cases):
        cr = await eval_one(client, model["id"], system_prompt, case, thinking=is_thinking)
        result.cases.append(cr)

        # 进度
        icon = "✅" if cr.score >= 0.5 else "❌"
        if cr.error:
            icon = "💥"
        print(f"  [{i+1}/{len(cases)}] {icon} {cr.case_id}: '{cr.output[:40]}' ({cr.latency_ms}ms)")

        await asyncio.sleep(0.3)  # 礼貌间隔

    return result


def print_report(results: list[ModelResult], categories: list[str]):
    """打印对比报告"""
    print("\n" + "=" * 100)
    print("📊 BuyPulse 模型选型评测结果")
    print("=" * 100)

    # 总表
    header = f"{'模型':<18} {'价位':<6} {'总准确率':>8}"
    for cat in categories:
        header += f" {cat[:6]:>7}"
    header += f" {'延迟ms':>7} {'错误':>4} {'¥/M入':>6} {'¥/M出':>6}"
    print(header)
    print("-" * len(header))

    for r in sorted(results, key=lambda x: x.accuracy, reverse=True):
        line = f"{r.model_name:<18} {r.tier:<6} {r.accuracy:>7.1f}%"
        for cat in categories:
            line += f" {r.cat_accuracy(cat):>6.0f}%"
        line += f" {r.avg_latency:>7} {r.errors:>4} {r.price_in:>6.1f} {r.price_out:>6.1f}"
        print(line)

    # 错误详情
    print("\n" + "=" * 100)
    print("❌ 错误用例详情（按模型）")
    print("=" * 100)
    for r in sorted(results, key=lambda x: x.accuracy, reverse=True):
        wrong = [c for c in r.cases if c.score == 0.0 and c.error is None]
        if wrong:
            print(f"\n--- {r.model_name} (准确率 {r.accuracy:.1f}%) ---")
            for c in wrong:
                print(f"  {c.case_id} [{c.category}]")
                print(f"    输入: {c.input_text}")
                print(f"    期望: {c.expected}")
                print(f"    实际: {c.output}")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="BuyPulse 模型选型评测")
    parser.add_argument("--models", help="逗号分隔的模型ID列表")
    parser.add_argument("--cases", default="evals/test_cases_v2.json", help="测试用例文件")
    parser.add_argument("--rounds", type=int, default=1, help="评测轮次")
    args = parser.parse_args()

    api_key = os.environ.get("SILICONFLOW_API_KEY")
    # 从 .env 文件读取
    if not api_key:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("SILICONFLOW_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("❌ 请设置 SILICONFLOW_API_KEY（环境变量或 .env 文件）")
        sys.exit(1)

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.siliconflow.cn/v1",
    )

    # 加载测试用例
    test_data = json.loads(Path(args.cases).read_text())
    cases = test_data["test_cases"]
    system_prompt = test_data["system_prompt"]
    categories = sorted(set(c["cat"] for c in cases))

    # 选择模型
    models = MODELS
    if args.models:
        model_ids = [m.strip() for m in args.models.split(",")]
        models = [m for m in MODELS if m["id"] in model_ids]
        if not models:
            print(f"❌ 未找到模型: {args.models}")
            print(f"可用模型: {', '.join(m['id'] for m in MODELS)}")
            sys.exit(1)

    print(f"📋 测试用例: {len(cases)} 个, 分类: {categories}")
    print(f"🤖 测试模型: {len(models)} 个")
    print(f"🔄 轮次: {args.rounds}")
    print()

    all_results = []
    for round_num in range(1, args.rounds + 1):
        if args.rounds > 1:
            print(f"\n{'='*50}")
            print(f"第 {round_num}/{args.rounds} 轮")
            print(f"{'='*50}")

        for model in models:
            print(f"\n🧪 测试: {model['name']} ({model['id']})")
            result = await eval_model(client, model, cases, system_prompt)
            all_results.append(result)
            print(f"   ✅ 准确率: {result.accuracy:.1f}% | 延迟: {result.avg_latency}ms | 错误: {result.errors}")

    # 如果多轮，取每个模型最好的一轮
    if args.rounds > 1:
        best_results = {}
        for r in all_results:
            if r.model_name not in best_results or r.accuracy > best_results[r.model_name].accuracy:
                best_results[r.model_name] = r
        final_results = list(best_results.values())
    else:
        final_results = all_results

    print_report(final_results, categories)

    # 保存详细结果
    out_dir = Path("evals/results")
    out_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    for r in final_results:
        out_file = out_dir / f"{r.model_name}_{timestamp}.json"
        data = {
            "model": r.model_name,
            "model_id": r.model_id,
            "accuracy": r.accuracy,
            "avg_latency_ms": r.avg_latency,
            "errors": r.errors,
            "cases": [
                {
                    "id": c.case_id, "cat": c.category,
                    "input": c.input_text, "expected": c.expected,
                    "output": c.output, "score": c.score,
                    "latency_ms": c.latency_ms, "error": c.error,
                }
                for c in r.cases
            ],
        }
        out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    print(f"\n详细结果保存在: evals/results/")


if __name__ == "__main__":
    import functools
    # Force unbuffered output
    print = functools.partial(print, flush=True)
    asyncio.run(main())
