#!/usr/bin/env python3
"""
掘金自动发文脚本 v4
从 accounts.json 读取 cookies，不再硬编码 sessionid
"""

import requests
import json
import os
import re
import time
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(BASE_DIR, 'output', 'accounts.json')
ARTICLES_DIR = os.path.join(BASE_DIR, 'output', 'articles')
LOG_FILE = os.path.join(BASE_DIR, 'output', 'publish_log.json')

HEADERS_BASE = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36',
    'Referer': 'https://juejin.cn/',
    'Origin': 'https://juejin.cn',
    'Content-Type': 'application/json',
}

TAG_MAP = {
    'AI': '6809637769959186439',
    '人工智能': '6809637769959186439',
    '机器学习': '6809637773937893384',
    'Python': '6809637773937893389',
    '前端': '6809637773937893384',
    '后端': '6809637776263217160',
    'Java': '6809637776263217160',
    '程序员': '6809637776263217160',
    '工具': '6809637773937893384',
    '效率': '6809637773937893384',
    '开源': '6809637773937893384',
    '教程': '6809637776263217160',
    '默认': '6809637776263217160',
}

CATEGORY_MAP = {
    'frontend': '1', 'backend': '2', 'android': '3', 'ios': '4',
    'ai': '5', 'devops': '6', 'read': '7', 'other': '8',
    '默认': '2',
}

def get_juejin_cookies():
    """从 accounts.json 读取掘金 cookies"""
    if not os.path.exists(ACCOUNTS_FILE):
        print('❌ accounts.json 未找到，请先运行 save_login.py')
        return None
    with open(ACCOUNTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    accounts = data.get('juejin', [])
    if not accounts:
        print('❌ 未找到掘金账号，请先运行 save_login.py juejin')
        return None
    # 取最新的
    acc = accounts[-1]
    cookies = {}
    for c in acc.get('cookies', []):
        cookies[c['name']] = c['value']
    print('  📱 %s | %d cookies' % (acc.get('phone', ''), len(cookies)))
    return cookies

def get_session():
    cookies = get_juejin_cookies()
    if not cookies:
        return None
    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update(HEADERS_BASE)
    s.get('https://juejin.cn/')
    return s

def validate_session(session):
    """验证 session 是否有效"""
    try:
        r = session.get('https://api.juejin.cn/user_api/v1/user/get')
        user = r.json().get('data', {})
        if user.get('user_name'):
            print('  ✅ 登录: %s | 文章: %s' % (user['user_name'], user.get('post_article_count', 0)))
            return True
        else:
            print('  ❌ 登录验证失败: 接口返回空用户')
            return False
    except Exception as e:
        print('  ❌ 登录验证异常: %s' % e)
        return False

def load_publish_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'published': [], 'failed': []}

def save_publish_log(log):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def get_articles_to_publish():
    if not os.path.exists(ARTICLES_DIR):
        return []
    published = load_publish_log().get('published', [])
    articles = []
    for fname in sorted(os.listdir(ARTICLES_DIR)):
        if not fname.endswith('.md') or fname == 'writing_log.json':
            continue
        fpath = os.path.join(ARTICLES_DIR, fname)
        if fpath in published:
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        title = extract_title(content, fname)
        tags = extract_tags(content)
        category = extract_category(content, tags)
        articles.append({
            'filepath': fpath,
            'filename': fname,
            'title': title,
            'content': content,
            'tags': tags,
            'category': category,
        })
    return articles

def extract_title(content, filename):
    m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    parts = filename.replace('.md', '').split('-', 3)
    return parts[3] if len(parts) >= 4 else filename.replace('.md', '')

def extract_tags(content):
    tags = ['默认']
    tag_keywords = {
        'Python': ['python', 'flask', 'django', 'fastapi', '爬虫', 'scraping', 'requests'],
        '工具': ['工具', 'cli', 'command line', '开源', '效率'],
        '教程': ['教程', '入门', '指南', 'guide', 'tutorial', '从零'],
        'AI': ['ai', '人工智能', 'machine learning', 'deep learning', 'chatgpt', 'llm', '大模型', 'gpt'],
        '效率': ['效率', '生产力', 'workflow', '自动化', '知识管理'],
    }
    title_lower = (content.split('\n')[0] or '').lower()
    content_lower = content[:500].lower()
    for tag, kws in tag_keywords.items():
        if any(kw in title_lower or kw in content_lower for kw in kws):
            if tag not in tags:
                tags.append(tag)
    return tags

def extract_category(content, tags):
    if any(t in ('AI', '人工智能', '机器学习') for t in tags):
        return '5'
    if '前端' in tags:
        return '1'
    return '2'

def publish_article(session, article):
    title = article['title']
    content = article['content']
    tags = article['tags']
    category_id = article.get('category', '2')

    tag_ids = []
    for tag in tags:
        tid = TAG_MAP.get(tag)
        if tid and tid not in tag_ids:
            tag_ids.append(tid)
    if not tag_ids:
        tag_ids = [TAG_MAP['默认']]

    brief = content[:200].replace('\n', ' ').replace('#', '').strip()

    print('\n  ---')
    print('  标题: %s' % title)
    print('  标签: %s -> %s' % (tags, tag_ids))
    print('  分类: %s' % category_id)
    print('  字数: %d' % len(content))

    # Step 1: 创建草稿
    draft_payload = {
        'title': title,
        'content': content,
        'tag_ids': tag_ids,
        'category_id': category_id,
        'brief_content': brief,
        'cover_images': [],
        'is_original': 1,
        'editor_type': 'markdown',
    }

    r = session.post('https://api.juejin.cn/content_api/v1/article_draft/create', json=draft_payload)
    resp = r.json()

    if resp.get('err_no') != 0:
        err = resp.get('err_msg', '创建草稿失败')
        print('  ❌ 草稿失败: %s' % err)
        return False, err

    draft_id = resp['data']['id']
    print('  ✅ 草稿: %s' % draft_id)

    # Step 2: 发布
    time.sleep(1)
    pub_payload = {'draft_id': draft_id}
    r2 = session.post('https://api.juejin.cn/content_api/v1/article/publish', json=pub_payload)
    pub_resp = r2.json()

    if pub_resp.get('err_no') == 0:
        art_id = pub_resp['data']['article_id']
        print('  ✅ 发布成功! ID: %s' % art_id)
        print('  🔗 https://juejin.cn/post/%s' % art_id)
        return True, art_id
    else:
        err = pub_resp.get('err_msg', '发布失败')
        print('  ❌ 发布失败: %s' % err)
        return False, err

def main():
    print('=== 掘金自动发文 v4 ===')
    print('时间: %s\n' % datetime.now().strftime('%Y-%m-%d %H:%M'))

    session = get_session()
    if not session:
        return

    if not validate_session(session):
        return

    articles = get_articles_to_publish()
    if not articles:
        print('📭 无待发布文章')
        return

    print('\n待发布: %d 篇\n' % len(articles))
    
    log = load_publish_log()
    ok, fail = 0, 0

    for i, a in enumerate(articles):
        if i > 0:
            time.sleep(3)
        success, result = publish_article(session, a)
        if success:
            log['published'].append(a['filepath'])
            log.setdefault('article_ids', []).append({
                'filepath': a['filepath'],
                'title': a['title'],
                'article_id': result,
                'time': datetime.now().isoformat(),
            })
            ok += 1
        else:
            log['failed'].append({
                'filepath': a['filepath'],
                'title': a['title'],
                'error': result,
                'time': datetime.now().isoformat(),
            })
            fail += 1

    save_publish_log(log)
    print('\n✅ 成功: %d | ❌ 失败: %d' % (ok, fail))

if __name__ == '__main__':
    main()
