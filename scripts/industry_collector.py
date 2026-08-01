#!/usr/bin/env python3
"""
行业分析数据采集器 v1 — AI 应用 / AI Agent 行业
读标准输入（JSON）获取配置，输出采集结果到标准输出。

设计为 OpenClaw cron 调用的纯 Python 脚本。
零外部依赖（urllib + json + sys 标准库）。
"""

import sys
import json
import io
import urllib.request
import urllib.parse
import urllib.error
import time
import ssl
import re
import concurrent.futures

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


# ── 数据源采集函数 ──────────────────────────

def _request(url, timeout=15, headers=None):
    """统一 HTTP GET"""
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/json,*/*",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or url.endswith(".json"):
                return json.loads(data)
            return data.decode("utf-8", errors="replace")
    except Exception as e:
        return {"_error": str(e), "_url": url}


def _hn_item(story_id, timeout=10):
    """获取 HN 单条详情"""
    data = _request(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=timeout)
    if isinstance(data, dict) and data.get("title"):
        return {
            "title": data.get("title", ""),
            "url": data.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
            "score": data.get("score", 0),
            "by": data.get("by", ""),
            "time": data.get("time", 0),
        }
    return None


def collect_hacker_news(limit=10):
    """采集 Hacker News 热门，过滤 AI 相关（多线程，单请求独立超时）"""
    data = _request("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15)
    if not isinstance(data, list):
        return {"source": "Hacker News", "items": [], "error": "API failed"}

    story_ids = data[:limit]
    ai_keywords = [
        "ai", "llm", "gpt", "chatgpt", "openai", "claude", "anthropic",
        "gemini", "deepseek", "mistral", "llama", "agent", "rag",
        "transformer", "diffusion", "neural", "machine learning",
        "language model", "coder", "copilot", "genai",
    ]

    items = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futmap = {executor.submit(_hn_item, sid, timeout=4): sid for sid in story_ids}
        for future in concurrent.futures.as_completed(futmap, timeout=12):
            try:
                item = future.result()
            except Exception:
                continue
            if item:
                title_lower = item["title"].lower()
                is_ai = any(kw in title_lower for kw in ai_keywords)
                items.append({**item, "is_ai_related": is_ai})

    return {
        "source": "Hacker News",
        "fetched_at": int(time.time()),
        "total": len(items),
        "ai_related": sum(1 for i in items if i["is_ai_related"]),
        "items": items,
    }


def collect_jiqizhixin(max_items=10):
    """机器之心 (jiqizhixin) — AI 垂直媒体 RSS，质量高"""
    result = _parse_rss_titles("https://www.jiqizhixin.com/rss", "机器之心", ai_filter=False, timeout=15)
    # 不过滤，机器之心文章几乎全是 AI 相关
    return result


def collect_github_trending(max_items=10):
    """GitHub trending — 搜索 AI/LLM 相关仓库"""
    items = []
    seen = set()

    queries = [
        "AI agent framework",
        "large language model",
        "multi-modal AI",
    ]

    for q in queries:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://api.github.com/search/repositories?q={encoded}&sort=updated&per_page=4"
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                data = json.loads(resp.read())
        except Exception:
            continue

        if not isinstance(data, dict) or "items" not in data:
            continue

        for repo in data["items"]:
            if not isinstance(repo, dict):
                continue
            name = repo.get("full_name", "")
            desc = repo.get("description", "") or ""
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language", "") or ""
            title = f"{name}: {desc} [{lang} ⭐{stars}]" if desc else f"{name} [{lang} ⭐{stars}]"
            url = repo.get("html_url", "")
            key = name[:40]
            if key not in seen and len(title) > 8:
                seen.add(key)
                items.append({"title": title, "url": url})
                if len(items) >= max_items:
                    break
        if len(items) >= max_items:
            break

    return {
        "source": "GitHub Trending",
        "fetched_at": int(time.time()),
        "total": len(items),
        "items": items,
    }


def collect_zhihu_hot():
    """知乎热榜 — 尝试 web_fetch 但大概率 403，用 Python 直接请求试试"""
    data = _request("https://www.zhihu.com/hot", timeout=15)
    if isinstance(data, dict) and data.get("_error"):
        return {"source": "知乎热榜", "items": [], "error": data["_error"]}
    return {"source": "知乎热榜", "items": [], "error": "unable to parse"}


def _parse_rss_titles(url, source_name, ai_filter=True, timeout=15):
    """通用 RSS 解析器 — 提取标题，可选 AI 过滤"""
    text = _request(url, timeout=timeout)
    if isinstance(text, dict) and text.get("_error"):
        return {"source": source_name, "items": [], "error": text["_error"]}
    if not isinstance(text, str):
        return {"source": source_name, "items": [], "error": "not text"}

    items = []
    seen = set()

    # 查找所有 CDATA 或纯 title 文本
    # 先找全部链接+标题
    entries = re.findall(r"<item>(.*?)</item>", text, re.DOTALL)
    if not entries:
        entries = re.findall(r"<entry>(.*?)</entry>", text, re.DOTALL)

    ai_kw = ["ai", "人工智能", "模型", "大模型", "智能", "agent", "机器人", "机器学习",
             "深度学习", "自动化", "算法", "数据", "LLM", "GPT", "ChatGPT", "OpenAI",
             "训练", "推理", "多模态", "具身智能", "数字人", "自动驾驶"]

    for entry in entries:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", entry, re.DOTALL)
        if not title_match:
            continue
        title = title_match.group(1).strip()
        title = title.replace("<![CDATA[", "").replace("]]>", "").strip()
        if not title or title in seen or len(title) < 10:
            continue
        seen.add(title)

        if ai_filter:
            title_lower = title.lower()
            is_ai = any(kw.lower() in title_lower for kw in ai_kw)
            if not is_ai:
                continue

        items.append({"title": title, "url": source_name})

    return {
        "source": source_name,
        "fetched_at": int(time.time()),
        "total": len(items),
        "items": items,
    }


def collect_kr36():
    """36氪 — RSS 订阅 + AI 过滤（减少无关财经条目，节省 token）"""
    result = _parse_rss_titles("https://www.36kr.com/feed", "36氪", ai_filter=True, timeout=15)
    # 使用 AI 关键词过滤，只保留 AI/科技/机器人相关
    return result


def collect_tmtpost():
    """钛媒体 — RSS 订阅"""
    result = _parse_rss_titles("https://www.tmtpost.com/rss", "钛媒体", ai_filter=False, timeout=15)
    return result


def collect_bing_ai_news():
    """通过 Bing 搜索 AI 相关新闻（改进版 v3：+AI关键词过滤+域名黑名单）"""
    queries = [
        "AI agent 2026 最新",
        "大模型 融资 2026",
        "人工智能 行业 最新",
        "LLM 开源 2026",
        "AI 应用 产品 发布",
    ]
    all_items = []
    seen_titles = set()

    # AI 关键词（用来过滤无关结果，如百度百科词语解释）
    ai_kw = ["ai", "llm", "gpt", "chatgpt", "openai", "claude", "deepseek", "agent", "大模型", "人工智能",
             "模型", "智能", "机器人", "机器学习", "深度学习", "融资", "芯片", "数据", "算法",
             "训练", "推理", "多模态", "数字人", "自动驾驶", "具身", "神经", "网络", "自动化",
             "mind", "token", "transformer", "diffusion", "genai", "copilot"]
    # 域名黑名单
    bad_domains = ["baike.baidu.com", "zdic.net", "hanyuguoxue.com", "ask.zhidao", "zhidao.baidu.com",
                   "map.baidu.com", "passport.baidu.com", "tieba.baidu.com"]

    for q in queries:
        encoded_q = urllib.parse.quote(q)
        url = f"https://cn.bing.com/search?q={encoded_q}&count=10&form=QBRE"
        text = _request(url, timeout=20)
        if not isinstance(text, str):
            time.sleep(1.5)
            continue

        items = []
        for m in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', text, re.DOTALL | re.IGNORECASE):
            link = m.group(1).strip()
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not title or len(title) < 8:
                continue
            if any(bad in link for bad in bad_domains):
                continue
            if 'bing.com' in link or 'microsoft.com' in link:
                continue

            # 标题里混入了域名的修正 — 搜索更激进
            # 先找 http:// 或 https:// 并切除之前的域名前缀
            proto_match = re.search(r'https?://', title)
            if proto_match:
                # 有协议前缀，可能是 "ai-bot.cnhttps://ai-bot.cn" 这种
                # 按协议分割取后半段
                after_proto = title[proto_match.start():]
                # 再提取域名后的实际路径/标题
                slash_pos = after_proto.find('/', 8)
                if slash_pos >= 0:
                    # 从路径取标题
                    pass
                # 直接尝试从标题末尾取有意义的部分
                second_part = re.sub(r'^https?://[^/]+/?', '', title)
                if len(second_part) > 8:
                    title = second_part
                elif len(title) > 20:
                    title = title[:40]
                    
            # 通用域名前缀清洗
            for domain in ['jishuzhan.net', 'segmentfault.com', 'aitoollab.cn', 'zhuanlan.zhihu.com', '36kr.com',
                           'tmtpost.com', 'infoq.cn', 'huxiu.com', 'geekpark.net', 'leiphone.com',
                           'mp.weixin.qq.com', 'thepaper.cn', 'sohu.com', '163.com', 'sina.com.cn',
                           'toutiao.com', 'baidu.com', 'zhihu.com', 'yiyan.baidu.com', 'doubao.com',
                           'csdn.net', 'runoob.com', 'aigc.cn', 'dongaigc.com', 'aipintai.com',
                           'ai-bot.cn']:
                if title.startswith(domain):
                    title = title[len(domain):].strip()
                    break

            # AI 关键词过滤
            tl = title.lower()
            if not any(kw.lower() in tl for kw in ai_kw):
                continue

            # 去重
            key = title[:30]
            if key in seen_titles:
                continue
            seen_titles.add(key)

            items.append({"title": title, "url": link.split('?')[0]})
            if len(items) >= 5:
                break

        if items:
            all_items.append({"query": q, "results": items})
        time.sleep(1.5)

    return {
        "source": "Bing 搜索",
        "fetched_at": int(time.time()),
        "data": all_items,
        "total": sum(len(g["results"]) for g in all_items),
    }


# ── 聚合调度 ──────────────────────────────────

def collect_failures():
    """采集失败/裁员/风险信号（由多维解析建议新增）
    从 36氪、HN（简单模式）中扫出负面信号。
    HN 国内直连速度慢，减小请求量。
    """
    items = []
    seen = set()
    now_ts = int(time.time())
    cutoff_ts = now_ts - 180 * 86400

    # 1. 36氪 RSS 扫负面（速度快，国内通）
    try:
        kr36_text = _request("https://www.36kr.com/feed", timeout=15)
        if isinstance(kr36_text, str):
            for entry in re.findall(r"<item>(.*?)</item>", kr36_text, re.DOTALL):
                title_m = re.search(r"<title[^>]*>(.*?)</title>", entry, re.DOTALL)
                if not title_m:
                    continue
                title = title_m.group(1).strip()
                title = title.replace("<![CDATA[", "").replace("]]>", "").strip()
                if any(kw in title for kw in ["裁员", "倒闭", "亏损", "暴跌", "离职", "破发", "爆雷"]):
                    key = title[:40]
                    if key not in seen:
                        seen.add(key)
                        items.append({"title": title, "url": "https://www.36kr.com", "source": "36氪", "score": 0})
                        if len(items) >= 6:
                            break
    except Exception:
        pass

    # 2. HN — 只从 top stories 中扫前 3 个（极小量，避免网络卡顿）
    try:
        data = _request("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8)
        if isinstance(data, list):
            risk_kw_en = ["layoff", "shutdown", "closing", "downsize", "fired", "kill", "archived", "fail", "lost"]
            for sid in data[:3]:
                if len(items) >= 4:
                    break
                try:
                    item = _hn_item(sid, timeout=3)
                except Exception:
                    continue
                if not item or not item.get("title"):
                    continue
                item_time = item.get("time", 0)
                if item_time < cutoff_ts:
                    continue
                tl = item["title"].lower()
                if any(kw in tl for kw in risk_kw_en):
                    key = item["title"][:40]
                    if key not in seen:
                        seen.add(key)
                        items.append({"title": item["title"], "url": item.get("url",""), "score": item.get("score", 0)})
    except Exception:
        pass

    return {
        "source": "失败/风险信号（负面采集）",
        "fetched_at": int(time.time()),
        "items": items,
        "total": len(items),
    }


def collect_one_safe(name, func, global_timeout=50):
    """单个源采集，带全局超时保护"""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(func)
        try:
            return fut.result(timeout=global_timeout)
        except concurrent.futures.TimeoutError:
            return {"source": name, "items": [], "error": "timeout"}


def collect_all(sources=None):
    """并发或串行采集所有源（每个源独立超时保护）"""
    available_sources = {
        "hacker_news": collect_hacker_news,
        "jiqizhixin": collect_jiqizhixin,
        "github_trending": collect_github_trending,
        "kr36": collect_kr36,
        "tmtpost": collect_tmtpost,
        "zhihu": collect_zhihu_hot,
        "bing": collect_bing_ai_news,
        "failures": collect_failures,
    }

    if sources:
        to_run = {k: v for k, v in available_sources.items() if k in sources}
    else:
        to_run = available_sources

    results = {}
    errors = []
    for name, func in to_run.items():
        try:
            result = collect_one_safe(name, func, global_timeout=50)
            if isinstance(result, dict) and result.get("error") == "timeout":
                errors.append({"source": name, "error": "timeout (>50s)"})
                continue
            items = result.get("items", [])
            if isinstance(items, list) and len(items) > 0:
                results[name] = result
            elif isinstance(items, list) and len(items) == 0:
                if "error" not in result:
                    results[name] = {**result, "_note": "no items parsed"}
                else:
                    errors.append({"source": name, "error": result.get("error")})
        except Exception as e:
            errors.append({"source": name, "error": str(e)})

    return {
        "collected_at": int(time.time()),
        "sources": list(results.keys()),
        "data": results,
        "errors": errors,
        "has_data": len(results) > 0,
    }


# ── CLI 入口 ──────────────────────────────────

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(f"Usage: python3 {__file__} [sources...]")
        print("Sources: hacker_news infoq kr36 tmtpost zhihu bing")
        print("Default: all")
        return

    sources = sys.argv[1:] if len(sys.argv) > 1 else None
    result = collect_all(sources)

    # 输出 JSON 到 stdout（仅此一行，不含其他内容）
    sys.stdout.write(json.dumps(result, ensure_ascii=False))
    sys.stdout.write("\n")

    # 统计信息到 stderr
    data = result["data"]
    total_items = sum(len(v.get("items", [])) for v in data.values() if isinstance(v.get("items"), list))

    sys.stderr.write(f"\n📡 采集完成 | 源数: {len(data)} | 条目: {total_items}")
    if result["errors"]:
        sys.stderr.write(f" | ❌ 失败源: {len(result['errors'])}")
        for e in result["errors"]:
            sys.stderr.write(f" | {e['source']}: {e['error'][:60]}")
    sys.stderr.write("\n")


if __name__ == "__main__":
    main()
