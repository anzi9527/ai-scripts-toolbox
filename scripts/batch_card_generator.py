# -*- coding: utf-8 -*-
"""
batch_card_generator.py — 知识卡片批量生成器 v2 (草稿)

用途：批量调用 DeepSeek API，一次 prompt 生成 25 张知识卡片
方法：按批次组织主题，写入 knowledge/cards/YYYY-MM-DD/ 目录
前置：python3 -m pip install openai
"""

import json
import os
import re
import sys
import time
import argparse
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

CST = timezone(timedelta(hours=8))

# --- 配置 ---
DEFAULT_CARDS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "cards"
CARDS_BASE = Path(os.environ.get("CARDS_DIR", str(DEFAULT_CARDS_DIR)))
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-flash"

# --- 标签体系（44个） ---
ALL_TAGS = [
    "industry:ai应用", "industry:自媒体", "industry:电商", "industry:医疗",
    "industry:新能源", "industry:机器人", "industry:金融", "industry:半导体",
    "industry:航天",
    "tech:大模型", "tech:infra", "tech:agent", "tech:ai应用", "tech:安全",
    "tech:数据工程", "tech:多模态", "tech:rl", "tech:硬件",
    "skill:方法论", "skill:框架", "skill:脚本", "skill:AI视频", "skill:写作",
    "skill:编导",
    "funding:战略投资", "funding:a轮", "funding:b轮", "funding:ipo",
    "funding:pre-a轮",
    "market:营收报告", "market:市场份额", "market:排名榜单", "market:用户增长",
    "market:市场数据",
    "case:产品", "case:运营",
    "policy:ai监管", "policy:行业标准", "policy:数据安全", "policy:知识产权",
    "trend:具身智能", "insight:具身智能", "行业趋势:视频生成",
]
ALL_TAGS_STR = "\n".join(f"- {t}" for t in ALL_TAGS)

# --- 消费者映射（基于标签自动分配） ---
CONSUMER_MAP = {
    "tech:安全": ["gu-she", "gu-coder"],
    "tech:数据工程": ["gu-chong"],
    "tech:infra": ["gu-wei"],
    "tech:agent": ["gu-coder"],
    "tech:大模型": ["gu-chong", "gu-coder"],
    "tech:多模态": ["gu-dao", "gu-chong"],
    "skill:编导": ["gu-dao"],
    "skill:AI视频": ["gu-dao"],
    "skill:脚本": ["gu-dao"],
    "skill:方法论": ["gu-jian", "gu-ce"],
    "skill:框架": ["gu-ce", "gu-jian"],
    "industry:电商": ["gu-chong", "gu-ce"],
    "industry:医疗": ["gu-chong"],
    "industry:金融": ["gu-chong", "gu-ce"],
    "industry:新能源": ["gu-chong"],
    "industry:机器人": ["gu-chong"],
    "industry:半导体": ["gu-chong"],
    "industry:航天": ["gu-chong"],
    "industry:自媒体": ["gu-dao"],
    "policy:数据安全": ["gu-ce", "gu-wei"],
    "policy:ai监管": ["gu-ce"],
    "case:运营": ["gu-ce"],
    "case:产品": ["gu-coder"],
}

# --- 批次定义（含 repeat 字段，支持每子批多次调用） ---
BATCHES = [
    {"name": "A1", "repeat": 5, "count": 25,
     "prompt_context": "AI应用落地案例、大模型技术进展、行业趋势",
     "tags_pool": ["industry:ai应用", "tech:大模型", "tech:ai应用", "market:营收报告"]},
    {"name": "A2", "repeat": 4, "count": 25,
     "prompt_context": "AI Agent框架、多模态模型、强化学习应用",
     "tags_pool": ["tech:agent", "tech:多模态", "tech:rl", "tech:大模型"]},
    {"name": "B1", "repeat": 4, "count": 25,
     "prompt_context": "工作方法论、思维框架、效率工具方法论",
     "tags_pool": ["skill:方法论", "skill:框架"]},
    {"name": "B2", "repeat": 3, "count": 25,
     "prompt_context": "编程脚本技巧、数据分析方法、AI安全攻防",
     "tags_pool": ["skill:脚本", "tech:数据工程", "tech:安全"]},
    {"name": "C1", "repeat": 3, "count": 25,
     "prompt_context": "数据工程管线、基础设施、模型部署运维",
     "tags_pool": ["tech:数据工程", "tech:infra"]},
    {"name": "C2", "repeat": 3, "count": 25,
     "prompt_context": "AI芯片硬件、API工程设计、系统优化",
     "tags_pool": ["tech:硬件", "tech:infra", "tech:ai应用"]},
    {"name": "D1", "repeat": 4, "count": 25,
     "prompt_context": "电商行业策略、医疗AI、金融科技、数据隐私合规",
     "tags_pool": ["industry:电商", "industry:医疗", "industry:金融", "policy:数据安全"]},
    {"name": "D2", "repeat": 4, "count": 25,
     "prompt_context": "新能源技术、机器人行业、半导体产业、航天技术",
     "tags_pool": ["industry:新能源", "industry:机器人", "industry:半导体", "industry:航天"]},
]


def validate_config():
    """P1-4: API Key 前置校验"""
    if not DEEPSEEK_API_KEY:
        print("[fatal] DEEPSEEK_API_KEY is not set. Set env var or hardcode.")
        sys.exit(1)
    if not DEEPSEEK_API_KEY.startswith("sk-"):
        print(f"[fatal] DEEPSEEK_API_KEY looks invalid (starts with '{DEEPSEEK_API_KEY[:6]}...')")
        sys.exit(1)
    print(f"[config] API key: {DEEPSEEK_API_KEY[:8]}...  length={len(DEEPSEEK_API_KEY)}")
    print(f"[config] CARDS_DIR: {CARDS_BASE}")
    print(f"[config] Output date: {datetime.now(CST).strftime('%Y-%m-%d')}")


def resolve_consumers(tags: List[str]) -> List[str]:
    """基于标签自动分配消费者角色"""
    consumers = set()
    for tag in tags:
        mapped = CONSUMER_MAP.get(tag, [])
        for c in mapped:
            consumers.add(c)
    if not consumers:
        consumers.add("gu-ce")  # default
    return sorted(consumers)


def build_prompt(batch: dict, round_num: int = 0) -> str:
    """构建给 DeepSeek 的 prompt，要它生成 25 张卡片"""
    tags_str = "\n".join(f"- {t}" for t in batch["tags_pool"])
    today = datetime.now(CST).strftime('%Y-%m-%d')

    return f"""You are a knowledge card generator. Generate exactly 25 knowledge cards.

## Output format for each card (YAML frontmatter + markdown body):
---
id: card_YYYYMMDD_NNN
type: data|insight|trend|case|profile
status: draft
source:
  name: batch-generator
  date: {today}
tags:
- tag1
- tag2
confidence: high|medium
expires: 2027-01-31
created: {today}
updated: {today}
producer: batch-generator
consumers:
- gu-chong
---
# Title

Content paragraph 1...

Content paragraph 2...

---

## Rules
1. Each card has a unique id (card_YYYYMMDD_001 through _NNN)
2. Each card gets 1-3 tags from the pool below (plus optional extra tags from full reference)
3. Tag pool for this batch:
{tags_str}
4. Full tag reference (may also use these):
{ALL_TAGS_STR}
5. type is one of: data, insight, trend, case, profile
6. Content: 1-3 paragraphs, 2-4 sentences each. Must have real knowledge value.
7. Titles must be specific, do not use "Overview of X" or "Introduction to X" style.
8. No content duplication across cards in this batch — each card must cover a different topic.
9. Include ALL frontmatter fields: id, type, status, source, tags, confidence, expires, created, updated, producer, consumers.

## Topic domain for this batch
{tags_str}

## Today's date
{today}

## Round {round_num + 1} of this batch
Generate cards that cover DIFFERENT subtopics from any previous rounds in this batch.

Push each card inside ```markdown ... ``` blocks.
Start generating 25 cards now:"""


def parse_response(text: str) -> List[str]:
    """解析 API 回复，提取多张卡片的 frontmatter+body"""
    # Step 1: 从 fence 块中提取原始内容
    fence_pattern = r"```(?:markdown)?\s*\n([\s\S]*?)\n```"
    fence_blocks = re.findall(fence_pattern, text)

    if fence_blocks:
        raw = "\n\n".join(fence_blocks)
    else:
        raw = text

    # Step 2: 按 "\n---\n" 后紧跟 "id:" 来分割多卡片
    # 每个卡片以 --- 开头（前一个卡片的结束），含完整的 frontmatter + body
    # DeepSeek 输出格式：
    # ---\nid: xxx\ntype: xxx\n...\n---\n# Title\n\nContent...\n---\nid: yyy\n...
    
    # 用前瞻分割："\n---\n(?=id:)" 或 "\n---\n(?=\n---)" 但更精确的是在行首 --- 处分割
    # 简单方法：按 "\n---\n" 分割，然后配对 frontmatter + body
    segments = raw.split("\n---\n")
    
    cards = []
    i = 0
    while i < len(segments):
        seg = segments[i].strip()
        if not seg:
            i += 1
            continue
        if seg.startswith("---"):
            seg = seg[3:].strip()
        
        # 如果这个 segment 包含 id（是 frontmatter）
        if re.search(r"^id:\s*card_", seg, re.MULTILINE):
            fm = seg
            # 查找 body：下一 segment 或本 segment 中 --- 后的内容
            body = ""
            if i + 1 < len(segments):
                body = segments[i + 1]
                i += 1  # 跳过 body segment
            
            # 构建完整卡片
            card = "---\n" + fm + "\n---\n" + body.strip()
            cards.append(card)
        else:
            # 这个 segment 是 body 副产品，忽略
            pass
        i += 1

    if not cards:
        # Fallback: 按换行后的 --- 分割
        parts = re.split(r"(?m)^---+\s*$", raw)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if re.search(r"^id:\s*card_", p, re.MULTILINE):
                cards.append("---\n" + p + "\n---")

    # 去重
    seen = set()
    unique = []
    for card in cards:
        m = re.search(r"^id:\s*(card_\d{8}_\d{3})", card, re.MULTILINE)
        cid = m.group(1) if m else ""
        if cid and cid not in seen:
            seen.add(cid)
            unique.append(card)

    return unique


def call_deepseek(prompt: str, retries: int = 2) -> Optional[str]:
    """调用 DeepSeek API（subprocess 模式，prompt 通过临时文件传递）"""
    import subprocess
    import tempfile

    script_path = Path(__file__).resolve().parent / "deepseek_api_call.py"

    for attempt in range(retries + 1):
        # 写 prompt 到临时文件（避免命令行编码问题）
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
        tmp.write(prompt)
        tmp.close()

        try:
            result = subprocess.run(
                [sys.executable, str(script_path), tmp.name],
                capture_output=True, text=True, timeout=150,
                env=os.environ,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            else:
                err = result.stderr.strip() or "no output"
                print(f"  [retry] try {attempt+1}/{retries+1}: {err[:80]}")
        except subprocess.TimeoutExpired:
            print(f"  [retry] try {attempt+1}/{retries+1}: timeout")
        except Exception as e:
            print(f"  [retry] try {attempt+1}/{retries+1}: {e}")
        finally:
            try:
                os.remove(tmp.name)
            except:
                pass

        if attempt < retries:
            time.sleep(5)

    print(f"  [fail] all retries exhausted")
    return None


def get_next_card_id(date_str: str) -> int:
    """获取下一个可用卡片序号"""
    date_dir = CARDS_BASE / date_str
    if not date_dir.exists():
        return 1

    max_id = 0
    for f in date_dir.glob("*.md"):
        m = re.search(r"card_(\d{8})_(\d{3})", f.name)
        if m and m.group(1) == date_str.replace("-", ""):
            max_id = max(max_id, int(m.group(2)))
    return max_id + 1


def write_card(content: str, date_str: str, seq: int) -> bool:
    """写入一张卡片文件（原子写入：先写临时文件再 rename）"""
    m = re.search(r"^id:\s*(card_\d{8}_\d{3})", content, re.MULTILINE)
    card_id = m.group(1) if m else f"card_{date_str.replace('-', '')}_{seq:03d}"

    date_dir = CARDS_BASE / date_str
    date_dir.mkdir(parents=True, exist_ok=True)

    filepath = date_dir / f"{card_id}.md"
    if filepath.exists():
        print(f"  [skip] exists: {card_id}")
        return False

    # 修复 card id 序号（只做这一步，其他字段由 prompt 保证）
    content = re.sub(
        r"^id:\s*card_\d{8}_\d{3}",
        f"id: card_{date_str.replace('-', '')}_{seq:03d}",
        content, count=1, flags=re.MULTILINE
    )

    # 原子写入（先写 tmp 再 rename）
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(dir=date_dir, suffix=".tmp", delete=False, mode="w", encoding="utf-8")
        tmp.write(content.strip() + "\n")
        tmp.close()
        os.replace(tmp.name, str(filepath))
        print(f"  [write] {card_id}")
        return True
    except Exception as e:
        print(f"  [error] {card_id}: {e}")
        if tmp and os.path.exists(tmp.name):
            try:
                os.remove(tmp.name)
            except:
                pass
        return False


def run_batch(batch: dict, batch_index: int, date_str: str, dry_run: bool = False) -> int:
    """执行一个批次的单次调用（25张）"""
    print(f"\n{'='*50}")
    print(f"[batch {batch['name']}] idx={batch_index} ctx={batch['prompt_context']}")
    print(f"{'='*50}")

    prompt = build_prompt(batch, batch_index)
    print(f"  [prompt] {len(prompt)} chars")

    if dry_run:
        print(f"  [dry-run] skip API call")
        return 0

    response = call_deepseek(prompt)
    if not response:
        print(f"  [fail] batch {batch['name']}")
        return 0

    print(f"  [response] {len(response)} chars")

    cards = parse_response(response)
    print(f"  [parsed] {len(cards)} raw cards")

    seq = get_next_card_id(date_str)
    written = 0
    for i, card_content in enumerate(cards):
        if write_card(card_content, date_str, seq + written):
            written += 1

    print(f"  [done] batch {batch['name']}: {written}/{len(cards)} written")
    time.sleep(2)
    return written


def rebuild_index():
    """重建 INDEX.md（通过 subprocess 直接运行，不捕获输出以避免编码问题）"""
    index_script = Path(__file__).resolve().parent / "knowledge_index_builder.py"
    if index_script.exists():
        print(f"\n[build] rebuilding INDEX.md... (skipped: run separately due to encoding)")
        print(f"[build] cd auto-money && python knowledge_index_builder.py --index-only")
    else:
        print(f"[skip] no knowledge_index_builder.py found")


def main():
    parser = argparse.ArgumentParser(description="Batch generate knowledge cards")
    parser.add_argument("--mode", choices=["test", "batch", "full", "dry-run"],
                        default="dry-run", help="Execution mode")
    parser.add_argument("--batch", type=str, default=None,
                        help="Specific batch name (e.g. A1)")
    parser.add_argument("--date", type=str, default=None,
                        help="Card date (default today)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(CST).strftime("%Y-%m-%d")

    # API Key 校验
    validate_config()

    # 选择批次
    if args.batch:
        batches = [b for b in BATCHES if b["name"] == args.batch.upper()]
        if not batches:
            print(f"[error] unknown batch: {args.batch}")
            return
    else:
        batches = BATCHES

    dry_run = (args.mode == "dry-run")
    is_test = (args.mode == "test")

    total = 0
    total_calls = 0
    for i, batch in enumerate(batches):
        repeats = batch.get("repeat", 1)
        for r in range(repeats):
            if is_test and (i > 0 or r > 0):
                print(f"\n[test] only first call of first batch")
                break
            count = run_batch(batch, r, date_str, dry_run)
            total += count
            total_calls += 1
            if is_test:
                break
        if is_test:
            break

    print(f"\n{'='*50}")
    print(f"[done]")
    print(f"  mode: {args.mode}")
    print(f"  api_calls: {total_calls}")
    print(f"  written: {total} cards")
    print(f"  path: {CARDS_BASE / date_str}")
    print(f"  expected total: {sum(b.get('repeat',1) * b['count'] for b in batches)} cards in {sum(b.get('repeat',1) for b in batches)} calls")

    if total > 0 and not dry_run:
        rebuild_index()


if __name__ == "__main__":
    main()
