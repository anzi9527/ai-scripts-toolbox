#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小说写作调度器 — 由 cron 触发
输出: auto-money/market_research/stories/{date}_{title}.md
"""

import json, sys, os, random, subprocess, time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
OUTPUT = BASE / "market_research" / "stories"
DRAFTS = BASE / "market_research" / "drafts"
LOGS = BASE / "market_research" / "logs"
for d in [OUTPUT, DRAFTS, LOGS]:
    d.mkdir(parents=True, exist_ok=True)

# ── 题材池（轮换使用） ──
THEMES = [
    ("悬疑推理", "以日常场景为背景，设计一个细思极恐的反转故事。"),
    ("民间奇谈", "以农村/小镇为背景，讲述一个代代相传的诡异传说。开头用「我爷爷跟我说过一件事…」"),
    ("都市传说", "以城市为背景（出租屋/地铁/便利店），现代都市恐怖。"),
    ("职场怪事", "以公司/单位/医院为背景，熟人社会的悬疑故事。"),
    ("情感悬疑", "表面是感情故事，中途反转成悬疑。"),
]

def get_next_theme():
    """按周轮换题材，尽量不重复"""
    log_file = LOGS / "writing_log.json"
    if log_file.exists():
        with open(log_file, encoding="utf-8") as f:
            log = json.load(f)
        last_theme = log[-1]["theme"] if log else None
        prev3 = [e["theme"] for e in log[-3:]]
    else:
        last_theme = None
        prev3 = []
    
    # 选一个最近没用过的
    candidates = [t for t in THEMES if t[0] not in prev3]
    if not candidates:
        candidates = THEMES
    
    theme, desc = random.choice(candidates)
    return theme, desc

def build_prompt(theme, desc):
    """构建写作 prompt"""
    month_day = datetime.now().strftime("%m月%d日")
    title_template = random.choice([
        f"我在{['殡仪馆','停尸房','老宅','出租屋','医院','公司'][random.randint(0,5)]}的那三年",
        f"那一夜，{['我接了一个电话','我看到了不该看的东西','有人敲了我的门','我永远忘不了那个声音'][random.randint(0,3)]}",
        f"一个{['真实的','恐怖的','细思极恐的','令人窒息的'][random.randint(0,3)]}故事",
    ])
    
    return f"""你是一个知乎盐选悬疑短篇写手，笔名林墨。

请写一篇短篇故事，严格按照以下要求：

题材：{theme}
题材说明：{desc}
标题参考：{title_template}

格式要求：
1. 字数：5000-8000字
2. 风格：知乎盐选「亲身经历」体（第一人称「我」，口语化）
3. 开头前200字必须有悬念钩子
4. 至少一层反转（中间让读者意外）
5. 结尾细思极恐（留白，不解释太清楚）
6. 分段短，每段不超过150字，适配手机阅读
7. 对话口语化，不要书面腔

直接写故事标题和正文，不要任何前言后语。"""

def save_story(text, theme):
    """保存故事文件"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 提取标题（第一行）
    lines = text.strip().split('\n')
    title_line = ""
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('>'):
            # 取前30字作为文件名
            title_line = line.replace('##', '').replace('#', '').strip()
            if len(title_line) > 30:
                title_line = title_line[:30]
            break
    
    safe_title = "".join(c for c in title_line if c.isalnum() or c in ' _-，。').strip()
    if not safe_title:
        safe_title = f"{theme}_{today}"
    
    # 初稿 → drafts
    draft_file = DRAFTS / f"{today}_{safe_title}.md"
    draft_file.write_text(text, encoding="utf-8")
    
    # 字数统计
    cn = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
    
    # 记录日志
    log_file = LOGS / "writing_log.json"
    entry = {
        "date": today,
        "theme": theme,
        "title": title_line,
        "file": draft_file.name,
        "cn_chars": cn,
        "created_at": datetime.now().isoformat(),
    }
    
    if log_file.exists():
        with open(log_file, encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = []
    log.append(entry)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    # ── 产出索引 ──
    try:
        from _cross_ref import index_new
        summary_text = f'小说《{title_line}》({theme})' if title_line else f'{theme}小说'
        index_new(str(draft_file), type='story', pipeline='novel-writer', producer='main', summary=summary_text, tags=['novel', theme])
    except ImportError:
        pass
    
    return draft_file, cn, title_line

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # 测试模式：快速生成短版
        theme, desc = get_next_theme()
        print(f"题材: {theme}")
        print(f"说明: {desc}")
        print(f"Prompt 已构建（{len(build_prompt(theme, desc))}字）")
        return
    
    print("林墨写作流水线启动")
    
    # 1. 选题材
    theme, desc = get_next_theme()
    prompt = build_prompt(theme, desc)
    print(f"[1/3] 题材: {theme}")
    
    # 2. 调用模型写故事（通过 stdout 输出，由 cron session 负责调用）
    # 实际调用由 cron 的 agentTurn 完成，这里只输出 prompt
    print(f"[2/3] Prompt 长度: {len(prompt)} 字")
    print()
    print("="*60)
    print(prompt)
    print("="*60)
    print()
    print(f"[3/3] 写作完成后将保存到: {OUTPUT}/ 或 {DRAFTS}/")

if __name__ == "__main__":
    main()
