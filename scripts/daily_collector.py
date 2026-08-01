#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日综合数据采集器
合并 知乎热榜 + 36氪快讯 + 微博热搜 + 其他可用源
输出到 output/aggregation_{date}.json
"""
import sys, os, json, io, re, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from datetime import datetime, timezone, timedelta

BJT = timezone(timedelta(hours=8))
NOW = datetime.now(tz=BJT)
DATE = NOW.strftime('%Y-%m-%d')
BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, 'output', '_internal')
os.makedirs(OUTPUT, exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

results = {}

# 1. 36氪快讯
print('[1/4] 36氪快讯...', file=sys.stderr)
kr_articles = []
try:
    req = urllib.request.Request('https://36kr.com/newsflashes', headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
    # 提取新闻（markdown 格式：标题+链接+正文）
    for m in re.finditer(r'\[(.*?)\]\((.*?)\)\n\n(.*?)(?=\n\n\[|\n\n$)', html, re.DOTALL):
        title = m.group(1).strip()
        if title and len(title) > 5 and '36氪获悉' not in title[:10]:
            kr_articles.append({'title': title, 'url': m.group(2), 'summary': m.group(3).strip()[:100]})
except Exception as e:
    print(f'  36kr: {e}', file=sys.stderr)
results['36kr'] = kr_articles
print(f'  {len(kr_articles)} 篇', file=sys.stderr)

# 1b. Bing 搜索（替代 DuckDuckGo 的搜索方案）
print('[1b/4] Bing 行业搜索...', file=sys.stderr)
bing_results = []
bing_queries = ['自媒体 行业 最新动态', '电商 行业 2026 趋势', 'AI应用 行业 新闻 2026']
for q in bing_queries:
    try:
        from urllib.parse import quote
        url = f'https://cn.bing.com/search?q={quote(q)}&count=5'
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
        for m in re.finditer(r'<h2>.*?<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL):
            t = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if t and len(t) > 5:
                bing_results.append({'title': t, 'url': m.group(1).split('?')[0], 'source': 'bing'})
    except Exception as e:
        print(f'  bing {q}: {e}', file=sys.stderr)
# 去重
seen = set()
unique = []
for b in bing_results:
    if b['title'] not in seen:
        seen.add(b['title'])
        unique.append(b)
results['bing'] = unique
print(f'  {len(unique)} 篇', file=sys.stderr)

# 2. 知乎热榜
print('[2/4] 知乎热榜...', file=sys.stderr)
zhihu_file = os.path.join(OUTPUT, f'zhihu_hot_{DATE}.json')
if os.path.exists(zhihu_file):
    with open(zhihu_file, 'r', encoding='utf-8') as f:
        hot = json.load(f)
    results['zhihu_hot'] = hot
    print(f'  {len(hot)} 条', file=sys.stderr)
else:
    results['zhihu_hot'] = []
    print('  无今日热榜', file=sys.stderr)

# 3. 百度热点（可用 RSS 替代）
print('[3/4] 百度热搜...', file=sys.stderr)
baidu = []
try:
    req = urllib.request.Request('https://top.baidu.com/board?tab=realtime', headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
    for m in re.finditer(r'"word":"([^"]+)"', html):
        baidu.append({'title': m.group(1)})
    baidu = list(dict.fromkeys([b['title'] for b in baidu]))[:20]
    baidu = [{'title': t} for t in baidu]
except Exception as e:
    print(f'  baidu: {e}', file=sys.stderr)
results['baidu_hot'] = baidu
print(f'  {len(baidu)} 条', file=sys.stderr)

# 4. 行业过滤
print('[4/4] 行业分类...', file=sys.stderr)
all_items = []
for source, items in results.items():
    for item in items:
        title = item.get('title', '')
        all_items.append({'source': source, 'title': title})

# 关键词分类
categories = {
    'AI应用': ['AI', '人工智能', '大模型', 'GPT', 'ChatGPT', 'Kimi', 'DeepSeek', '机器学习', '算法', '算力', '芯片', '英伟达', '苹果AI', '谷歌AI', 'OpenAI'],
    '自媒体': ['抖音', '快手', '小红书', 'B站', '视频号', '网红', 'KOL', 'MCN', '直播', '短视频', '自媒体', '创作者', '流量', '博主', '涨粉'],
    '电商': ['电商', '淘宝', '京东', '拼多多', 'Temu', 'Shein', '直播带货', '跨境电商', '消费', '品牌', '物流', '外卖', '到店'],
    '金融': ['股市', 'A股', '基金', '投资', '理财', '加息', '降息', 'IPO', '融资', '债券', '期货'],
}

classified = {k: [] for k in categories}
classified['其他'] = []

for item in all_items:
    title = item['title']
    matched = False
    for sector, keywords in categories.items():
        for kw in keywords:
            if kw in title:
                classified[sector].append(item)
                matched = True
                break
        if matched:
            break
    if not matched:
        classified['其他'].append(item)

for sector, items in classified.items():
    print(f'  {sector}: {len(items)} 条', file=sys.stderr)

# 保存
out = os.path.join(OUTPUT, f'aggregation_{NOW.strftime("%Y%m%d_%H%M")}.json')
data = {
    'date': DATE,
    'time': NOW.strftime('%H:%M'),
    'sources': {k: len(v) for k, v in results.items()},
    'classified': {k: [i['title'] for i in v] for k, v in classified.items()},
    'total': len(all_items),
}
with open(out, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\n已保存: {out}', file=sys.stderr)
print(json.dumps(data, ensure_ascii=False))
