#!/usr/bin/env python3
"""
行业多维角色解析器 v1 — AI 应用 / AI Agent 行业
读取 industry_pipeline.py 输出的 final 日报，
以 4 个角色视角自动解析，用 DeepSeek 生成。
不再依赖 cron agentTurn。

依赖：openai（pip install openai）
输出：output/multiview_{date}.md
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
                {'role': 'system', 'content': '你是一个多维度的 AI 行业分析师。请从不同角色视角深入解析提供的行业日报。'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.8,
            max_tokens=8192,
        )
        content = resp.choices[0].message.content
        pt = resp.usage.prompt_tokens if resp.usage else 0
        ct = resp.usage.completion_tokens if resp.usage else 0
        from api_log import log_call
        log_call('industry_multiview', model, pt, ct)
        usage = {
            'prompt_tokens': pt,
            'completion_tokens': ct,
            'total_tokens': pt + ct,
        }
        return content, usage
    except Exception as e:
        print(f'\u26a0\ufe0f  DeepSeek API 调用失败: {e}', file=sys.stderr)
        return None, None


def find_latest_report():
    """找到最新的 industry_daily_{date}_final.md"""
    candidates = []
    for f in os.listdir(OUTPUT_DIR):
        m = re.match(r"industry_daily_(\d{4}-\d{2}-\d{2})_final\.md$", f)
        if m:
            candidates.append((m.group(1), os.path.join(OUTPUT_DIR, f)))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates:
        return candidates[0]
    # fallback：找非 final 版
    for f in os.listdir(OUTPUT_DIR):
        m = re.match(r"industry_daily_(\d{4}-\d{2}-\d{2})\.md$", f)
        if m:
            candidates.append((m.group(1), os.path.join(OUTPUT_DIR, f)))
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0] if candidates else (None, None)


def build_multiview_prompt(report_text):
    """构建多维角色解析 prompt"""
    return f"""你正在分析以下「AI 应用」行业日报。请以 4 个角色的视角分别深入剖析这份报告。

【报告正文】
{report_text[:12000]}

【解析要求】

### 👨‍💼 投资者视角
- 哪些信息信号最值得关注
- 报告中遗漏了什么关键数据
- 基于现有数据，会做出什么投资判断
- 给小哥的建议（可操作、具体）

### 👨‍🔬 技术专家视角
- 技术趋势判断是否准确
- 可能高估/低估了什么技术
- 哪些技术信号被忽略

### 🧑‍💻 创业者视角
- 赚钱机会的判断是否靠谱
- 有没有遗漏的细分机会
- 实际执行的难度评估
- 会从哪里切入

### 🧑‍💼 从业者视角
- 对AI从业者来说最有价值的信息
- 技能方向建议
- 职业发展判断

### 综合优化建议
- 数据源：漏了什么、质量如何
- 分析质量：盲点、偏见、幻觉检查
- 赚钱信号：可行性交叉验证
- 下一版改进方向

要求：
1. 每个视角必须基于报告中的真实数据，严禁编造
2. 每个视角至少 3 个具体观点
3. 语言犀利，不要和稀泥
4. 如果某视角缺乏足够数据支撑，明确说"现有数据不足以支撑该视角的深度分析"
"""


def save_multiview(date_str, content):
    """保存多维解析报告"""
    path = os.path.join(OUTPUT_DIR, f"multiview_{date_str}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 行业多维角色解析 · {date_str}\n")
        f.write(f"**解析对象**: industry_daily_{date_str}_final.md（AI 应用行业日报）\n")
        f.write(f"**解析时间**: {datetime.now(tz=BJT).strftime('%Y-%m-%d %H:%M')} (Asia/Shanghai)\n")
        f.write(f"**生成方式**: DeepSeek 自动调用\n\n---\n\n")
        f.write(content)
    cn = len([c for c in content if '\u4e00' <= c <= '\u9fff'])
    return path, cn


def main():
    # 找最新日报
    date_str, report_path = find_latest_report()
    if not report_path:
        print("❌ 未找到 industry_daily* 文件，请先运行 industry_pipeline.py", file=sys.stderr)
        sys.exit(1)

    print(f"📄 读取日报: {report_path}", file=sys.stderr)
    with open(report_path, "r", encoding="utf-8") as f:
        report_text = f.read()

    print(f"   长度: {len(report_text)} 字符", file=sys.stderr)
    print(f"   日期: {date_str}", file=sys.stderr)

    # 构建 prompt
    prompt = build_multiview_prompt(report_text)
    print(f"🧠 Prompt 已构建: {len(prompt)} 字符", file=sys.stderr)

    # 调用 DeepSeek
    print("\n🤖 自动调用 AI 生成多维角色解析...", file=sys.stderr)
    client = load_deepseek_client()
    if not client:
        print("❌ DeepSeek API 不可用", file=sys.stderr)
        sys.exit(1)

    content, usage = call_deepseek(client, prompt)
    if not content:
        print("❌ AI 生成失败", file=sys.stderr)
        sys.exit(1)

    final_path, cn = save_multiview(date_str, content)
    input_tokens = usage.get('prompt_tokens', 0)
    output_tokens = usage.get('completion_tokens', 0)

    print(f"✅ 多维角色解析已生成: {final_path}", file=sys.stderr)
    print(f"   中文字数: {cn} | Token: {input_tokens}in / {output_tokens}out", file=sys.stderr)

    # JSON 输出
    print(json.dumps({
        "status": "ok",
        "date": date_str,
        "source_file": report_path,
        "final_file": final_path,
        "auto_generated": True,
        "content_length": len(content),
        "cn_chars": cn,
        "tokens": usage,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
