#!/usr/bin/env python3
"""
行业深度报告生成器 v3 — AI 应用 / AI Agent 行业
读取 industry_pipeline.py 输出的 prompt 文件（含原始数据），
自动调用 DeepSeek 生成深度分析报告。

依赖：openai（pip install openai）
输出：output/report_{date}_final.md
"""

import sys
import json
import io
import os
import re
from datetime import datetime, timezone, timedelta
from openai import OpenAI

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BJT = timezone(timedelta(hours=8))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_deepseek_client():
    """从 openclaw.json 加载 DeepSeek 客户端"""
    config_path = os.path.join(os.path.expanduser('~'), '.openclaw', 'openclaw.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        providers = cfg.get('models', {}).get('providers', {})
        ds = providers.get('DeepSeek', {})
        api_key = ds.get('apiKey', '')
        base_url = ds.get('baseUrl', 'https://api.deepseek.com/v1')
        if not api_key:
            print('⚠️  未找到 DeepSeek API Key', file=sys.stderr)
            return None
        return OpenAI(api_key=api_key, base_url=base_url)
    except Exception as e:
        print(f'⚠️  读取配置失败: {e}', file=sys.stderr)
        return None


def call_deepseek(client, prompt, model='deepseek-v4-flash'):
    """用 openai 库调用 DeepSeek"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {'role': 'system', 'content': '你是一个专注于 AI 应用 / AI Agent 行业的深度市场分析师。请基于提供的行业资讯生成深度分析报告。'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.7,
            max_tokens=8192,
        )
        content = resp.choices[0].message.content
        pt = resp.usage.prompt_tokens if resp.usage else 0
        ct = resp.usage.completion_tokens if resp.usage else 0
        from api_log import log_call
        log_call('industry_report', model, pt, ct)
        usage = {
            'prompt_tokens': pt,
            'completion_tokens': ct,
            'total_tokens': pt + ct,
        }
        return content, usage
    except Exception as e:
        print(f'\u26a0\ufe0f  DeepSeek API 调用失败: {e}', file=sys.stderr)
        return None, None


def find_latest_prompt():
    """找到最新的 industry_daily_{date}.md 文件（即 pipeline 的输出）"""
    candidates = []
    for f in os.listdir(OUTPUT_DIR):
        m = re.match(r"industry_daily_(\d{4}-\d{2}-\d{2})\.md$", f)
        if m:
            candidates.append((m.group(1), os.path.join(OUTPUT_DIR, f)))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0]


def build_deep_report_prompt(raw_prompt_text):
    """基于原始 prompt 增加深度分析要求，生成长报告 prompt"""
    extra_requirements = """
## 额外要求：本次生成深度分析报告

除以上模板外，额外要求：

### 📈 7日趋势（如有历史数据）
如果今天有之前报告的留存，对比最近7天信号变化：
- 热度上升/下降的领域
- 新出现的玩家/产品
- 被淘汰的趋势

### 💰 赚钱机会评分卡
每个赚钱机会增加评分：
- **可行性**：⭐️⭐️⭐️⭐️⭐️
- **门槛**：低/中/高
- **竞争**：蓝海/浅红/红海
- **预期月收入**：xxx
- **推荐入局时机**：立即/1个月内/3个月内/观望

### 📋 本周重点关注
列出 3-5 个值得持续关注的事件/公司/趋势。

### 🔮 下周预测
基于现有数据，对下周 AI 应用/AI Agent 领域做出 3 条预测。

### 🎯 入场建议优先级
对所有赚钱机会按推荐度排序，给出"最值得做"TOP3。

要求：
1. 以上所有分析必须基于今日采集的真实数据
2. 严禁编造不存在的数据
3. 如果某个板块数据不足，如实写"今日数据不足以支撑此分析"
"""
    return raw_prompt_text + extra_requirements


def save_report(date_str, content):
    """保存深度报告"""
    path = os.path.join(OUTPUT_DIR, f"report_{date_str}_final.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    cn = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
    return path, cn


def main():
    # 查找最新的 prompt 文件
    date_str, prompt_path = find_latest_prompt()
    if not prompt_path:
        print("❌ 未找到 industry_daily_*.md 文件，请先运行 industry_pipeline.py", file=sys.stderr)
        sys.exit(1)

    print(f"📄 读取 prompt 文件: {prompt_path}", file=sys.stderr)
    with open(prompt_path, "r", encoding="utf-8") as f:
        raw_prompt = f.read()

    # 构建深度报告 prompt
    deep_prompt = build_deep_report_prompt(raw_prompt)

    # 统计原始数据
    hn = len(re.findall(r"\[HN\]", raw_prompt))
    kr36 = len(re.findall(r"\[36氪\]", raw_prompt))
    tmt = len(re.findall(r"\[钛媒体\]", raw_prompt))
    ai_tags = len(re.findall(r"🤖", raw_prompt))
    print(f"   数据统计: HN={hn} 36氪={kr36} 钛媒体={tmt} AI相关={ai_tags}", file=sys.stderr)

    # 自动调用 DeepSeek
    print("\n🤖 自动调用 AI 生成深度报告...", file=sys.stderr)
    client = load_deepseek_client()
    if not client:
        # fallback：只保存 prompt
        depth_path = os.path.join(OUTPUT_DIR, f"prompt_deep_{date_str}.md")
        with open(depth_path, "w", encoding="utf-8") as f:
            f.write(deep_prompt)
        print(f"⚠️  API 不可用，仅保存 prompt: {depth_path}", file=sys.stderr)
        print(json.dumps({"status": "prompt_only", "date": date_str, "prompt_file": depth_path}, ensure_ascii=False))
        sys.exit(0)

    content, usage = call_deepseek(client, deep_prompt)
    if not content:
        print("❌ AI 生成失败", file=sys.stderr)
        sys.exit(1)

    final_path, cn = save_report(date_str, content)
    input_tokens = usage.get('prompt_tokens', 0)
    output_tokens = usage.get('completion_tokens', 0)

    print(f"✅ 深度报告已生成: {final_path}", file=sys.stderr)
    print(f"   中文字数: {cn} | Token: {input_tokens}in / {output_tokens}out", file=sys.stderr)

    # JSON 输出供调用方读取
    print(json.dumps({
        "status": "ok",
        "date": date_str,
        "final_file": final_path,
        "auto_generated": True,
        "prompt_length": len(deep_prompt),
        "content_length": len(content),
        "cn_chars": cn,
        "tokens": usage,
        "stats": {
            "hacker_news": hn,
            "kr36": kr36,
            "tmtpost": tmt,
            "ai_related": ai_tags,
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
