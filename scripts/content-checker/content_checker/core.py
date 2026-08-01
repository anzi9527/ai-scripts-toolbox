"""
核心检测模块 — 内容合规检查逻辑
"""

import re
import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ============================================================
# 敏感词库 — 分级别
# ============================================================
SENSITIVE_WORDS = {
    "red": [
        "翻墙", "梯子", "VPN翻墙", "突破网络封锁", "突破防火墙",
        "赌博", "赌场", "六合彩", "外围",
        "代购毒品", "枪支", "炸药",
        "诈骗", "电信诈骗", "庞氏骗局",
        "传销", "非法集资",
        "黑客攻击", "DDoS", "网络攻击教程",
        "破解软件", "盗版", "破解版",
        "色情", "情色", "裸聊", "约炮", "一夜情",
        "卖淫", "嫖娼", "援交",
        "敏感词过滤", "绕过审查",
        "代办信用卡", "套现",
        "刷单", "刷量", "刷粉",
        "作弊", "代考", "代写论文",
    ],
    "yellow": [
        "翻墙软件", "科学上网",
        "VPN推荐", "SSR", "V2Ray",
        "闭源", "破解",
        "外挂", "脚本抢购",
        "爬虫抓取", "数据爬取",
        "侵删", "侵权删除",
        "期货", "杠杆",
        "炒股", "荐股",
        "医疗广告", "代孕",
    ],
    "platform_specific": {
        "juejin": ["未经授权的转载", "抄袭", "外链推广", "引流", "公众号"],
        "csdn": ["下载需积分", "付费资源"],
        "zhihu": ["咨询加微信", "付费咨询"],
    },
}


def _find_word_occurrences(content: str, word: str, context_chars: int = 30) -> List[Dict]:
    """在文本中查找某个词的所有出现位置及上下文"""
    results = []
    for m in re.finditer(re.escape(word), content, re.IGNORECASE):
        start = max(0, m.start() - context_chars)
        end = min(len(content), m.end() + context_chars)
        ctx = content[start:end].replace("\n", " ")
        results.append({
            "word": word,
            "context": ctx.strip(),
            "position": m.start(),
        })
    return results


# ============================================================
# 公开 API
# ============================================================

def check_text(content: str, filename: str = "") -> Dict:
    """
    检查文本内容是否合规

    Args:
        content: 要检查的文本
        filename: 可选的源文件名，仅用于报告

    Returns:
        包含检测结果的字典
    """
    results = {
        "file": filename,
        "words": len(content.split()),
        "chars": len(content.replace(" ", "").replace("\n", "")),
        "red_flags": [],
        "yellow_flags": [],
        "platform_warnings": {},
        "checks": {},
    }

    # 1. 红线检查
    for word in SENSITIVE_WORDS["red"]:
        occurrences = _find_word_occurrences(content, word)
        results["red_flags"].extend(occurrences)

    # 2. 黄线检查
    for word in SENSITIVE_WORDS["yellow"]:
        occurrences = _find_word_occurrences(content, word)
        results["yellow_flags"].extend(occurrences)

    # 3. 外链检查
    external_links = re.findall(r"https?://[^\s\)\]>\"]+", content)
    own_links = [
        l for l in external_links
        if not any(d in l for d in [
            "github.com", "picsum.photos", "via.placeholder.com", "img.shields.io"
        ])
    ]
    results["checks"]["external_links"] = len(own_links)
    if len(own_links) > 10:
        results["yellow_flags"].append({
            "word": f"外链过多({len(own_links)}个)",
            "context": f"文章包含 {len(own_links)} 个外部链接，可能被判定为营销内容",
            "position": -1,
        })

    # 4. 转载声明检查
    if re.search(r"(转载|转自|来源|原作者|侵删)", content):
        results["yellow_flags"].append({
            "word": "转载/来源声明",
            "context": "文章包含转载声明，请确认是否为原创",
            "position": -1,
        })

    # 5. 平台特有警告
    for platform, words in SENSITIVE_WORDS["platform_specific"].items():
        for word in words:
            if word.lower() in content.lower():
                results["platform_warnings"].setdefault(platform, [])
                results["platform_warnings"][platform].append(word)

    return results


def check_file(filepath: str) -> Tuple[Dict, str]:
    """
    检查一个文件的合规性

    Args:
        filepath: 文件路径

    Returns:
        (results_dict, verdict_str)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    filename = Path(filepath).name
    results = check_text(content, filename)

    # 总体判定
    if results["red_flags"]:
        verdict = "❌ 禁止发布 - 存在红线违规"
    elif results["yellow_flags"] and results["checks"].get("external_links", 0) > 15:
        verdict = "⚠️ 建议修改后发布"
    elif results["yellow_flags"]:
        verdict = "🟡 可发布，但建议检查警告项"
    else:
        verdict = "✅ 合规，可以发布"

    return results, verdict


def scan_directory(dirpath: str = ".", pattern: str = "*.md") -> List[Tuple[str, Dict, str]]:
    """
    扫描目录下的所有匹配文件

    Args:
        dirpath: 目录路径
        pattern: 文件通配模式，默认 *.md

    Returns:
        列表: [(filename, results_dict, verdict_str), ...]
    """
    path = Path(dirpath)
    if not path.exists():
        print(f"❌ 目录不存在: {dirpath}")
        return []

    files = sorted(path.glob(pattern))
    if not files:
        print(f"📭 未找到匹配 {pattern} 的文件")
        return []

    results_list = []
    for fpath in files:
        results, verdict = check_file(str(fpath))
        results_list.append((fpath.name, results, verdict))

    return results_list


def print_report(results: Dict, verdict: str, verbose: bool = True):
    """打印检测报告到控制台"""
    print(f"\n{'='*55}")
    print(f"  📄 {results['file'] or '(直接文本)'}")
    print(f"  {'='*55}")
    print(f"    字数: {results['words']} | 字符: {results['chars']}")
    print(f"    外链: {results['checks'].get('external_links', 0)} 个")

    if results["red_flags"]:
        print(f"\n  🔴 红线违规 ({len(results['red_flags'])} 处):")
        for f in results["red_flags"]:
            print(f"    - [{f['word']}] ...{f['context'][:80]}...")

    if results["yellow_flags"]:
        print(f"\n  🟡 警告 ({len(results['yellow_flags'])} 处):")
        for f in results["yellow_flags"]:
            print(f"    - [{f['word']}] ...{f['context'][:80]}...")

    if results["platform_warnings"]:
        for plat, words in results["platform_warnings"].items():
            print(f"\n  ⚠️ [{plat}] 平台注意: {', '.join(words)}")

    if not results["red_flags"] and not results["yellow_flags"] and not results["platform_warnings"]:
        print("\n  ✅ 未发现明显违规内容")

    print(f"\n  📋 判定: {verdict}")
