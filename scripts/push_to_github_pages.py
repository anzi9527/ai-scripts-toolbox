#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小玲自动推送 — 多行业日报摘要到 GitHub Pages
使用 GitHub REST API （git 命令因网络限制无法直连 GitHub）

行业前缀: industry_daily_, industry_deep_, industry_multiview_,
           industry_self_media_, industry_ecommerce_
"""

import sys, os, json, io, glob, re, base64
import time, socket
from datetime import datetime
from urllib.request import Request, urlopen, HTTPError

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT = os.path.join(BASE, "output")
CROSS_DIR = os.path.join(os.path.dirname(BASE), "cross-validate")
DOCS_DIR = os.path.join(CROSS_DIR, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)

# ─── 分发回执日志（P0-4：发送成功回执） ─────────────────────────
DIST_LOG_DIR = os.path.join(BASE, "logs", "distribution")
os.makedirs(DIST_LOG_DIR, exist_ok=True)
DIST_FAIL_MARK = "DISTRIBUTION_FAIL"

# ─── 互斥锁（防并发推送导致 GitHub 409 SHA 冲突） ──────────────
LOCK_FILE = os.path.join(BASE, "logs", "distribution", ".push.lock")
LOCK_TIMEOUT = 300  # 最多等 5 分钟，避免死锁

def acquire_lock():
    """尝试获取互斥锁。成功返回 True；超时返回 False（调用方应退出）。"""
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    deadline = time.time() + LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"pid={os.getpid()} host={socket.gethostname()} ts={datetime.now().isoformat()}\n".encode())
            os.close(fd)
            print(f"    [Lock] 已获取互斥锁 {LOCK_FILE}", file=sys.stderr)
            return True
        except FileExistsError:
            # 检查是否 stale（进程已死）
            stale = False
            try:
                with open(LOCK_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                m = re.search(r"pid=(\d+)", content)
                if m:
                    pid = int(m.group(1))
                    if not _pid_alive(pid):
                        stale = True
            except Exception:
                pass
            if stale:
                print(f"    [Lock] 检测到 stale 锁 (pid {pid} 已死)，强制接管", file=sys.stderr)
                try:
                    os.remove(LOCK_FILE)
                except OSError:
                    pass
                continue
            if time.time() > deadline:
                print(f"    [Lock] ⚠️ 等待锁超时 ({LOCK_TIMEOUT}s)，放弃本次推送", file=sys.stderr)
                return False
            time.sleep(2)

def _pid_alive(pid):
    """Windows 兼容的进程存活检测"""
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return True  # 无法检测时保守视为存活
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def release_lock():
    """释放互斥锁（幂等）"""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
            print(f"    [Lock] 已释放 {LOCK_FILE}", file=sys.stderr)
    except OSError:
        pass

def _push_with_lock():
    """带锁的主流程包装：main() 的核心步骤。返回 True 表示可继续，False 表示获取锁失败。"""
    if not acquire_lock():
        return False
    try:
        _run_main()
        return True
    finally:
        release_lock()
FAIL_LIST_GLOBAL = []


def write_receipt(status, summary, detail):
    """写分发回执日志：auto-money/logs/distribution/YYYY-MM-DD.json

    status: ok / fail / partial
    summary: {files_total, files_ok, files_fail, reports_count, copied}
    detail: 失败明细列表（每个 {file, error}）
    失败时同时输出 DISTRIBUTION_FAIL 标记，便于晨检/巡检 grep。
    """
    now = datetime.now()
    ts = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    receipt = {
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": ts,
        "status": status,
        "summary": summary,
        "detail": detail,
    }
    path = os.path.join(DIST_LOG_DIR, f"{now.strftime('%Y-%m-%d')}.json")
    # 追加到当日文件（若存在），保留多次分发历史
    entries = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = [entries]
        except Exception:
            entries = []
    entries.append(receipt)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    if status != "ok":
        print(f"⚠️  {DIST_FAIL_MARK} status={status} files_fail={summary.get('files_fail', 0)}", file=sys.stderr)
    else:
        print(f"✅ 分发回执已写入: {path} (files {summary.get('files_ok', 0)}/{summary.get('files_total', 0)})", file=sys.stderr)
    return path


# GitHub 配置（PAT 走环境变量 GITHUB_PAT）
GITHUB_REPO = "anzi9527/cross-validate"
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")  # 环境变量注入，不硬编码
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents"
GITHUB_BRANCH = "main"

# Buttondown API（Newsletter 推送）
# API Key 从环境变量读取，不硬编码（安全红线，参考 API key 迁移教训）
# 未配置时优雅跳过，不影响 GitHub 推送主流程
BUTTONDOWN_API = "https://api.buttondown.com/v1/emails"
BUTTONDOWN_API_KEY = os.environ.get("BUTTONDOWN_API_KEY", "").strip()

# 所有支持的行业前缀
INDUSTRY_PREFIXES = [
    'industry_daily_',
    'industry_deep_',
    'industry_multiview_',
    'industry_self_media_',
    'industry_ecommerce_',
    'industry_daily_dianshang_',
    'industry_daily_meiti_',
    'report_',
]

INDUSTRY_NAMES = {
    'industry_daily_': 'AI应用',
    'industry_deep_': '深度报告',
    'industry_multiview_': '多维解析',
    'industry_self_media_': '自媒体',
    'industry_ecommerce_': '电商',
    'industry_daily_dianshang_': '电商日报',
    'industry_daily_meiti_': '自媒体日报',
    'report_': '深度报告',
}

def extract_summary(text, max_len=200):
    lines = text.split('\n')
    content_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.startswith('>') and len(stripped) > 20:
            content_lines.append(stripped)
    full = ' '.join(content_lines)
    return full[:max_len] + ('...' if len(full) > max_len else '')

def extract_heat_rating(text):
    heat_kw = ['增长','上升','爆发','突破','新高','激增','热门','焦点','热点']
    count = sum(1 for kw in heat_kw if kw in text)
    if count >= 6: return 'high'
    if count >= 3: return 'medium'
    return 'low'

def extract_recommend_rating(text):
    rec_kw = ['推荐','关注','机会','建议','布局','投入','看好']
    count = sum(1 for kw in rec_kw if kw in text)
    if count >= 4: return 'strong'
    if count >= 2: return 'normal'
    return 'weak'

def count_opportunities(text):
    kw = ['机会','机遇','增长点','红利','蓝海','爆发']
    return sum(text.count(k) for k in kw)

def count_risks(text):
    kw = ['风险','警告','谨慎','注意','监管','下跌','下降']
    return sum(text.count(k) for k in kw)

def find_longest_prefix(fname):
    # 兼容：industry_xxx_YYYY-MM-DD_final.md / industry_xxx_YYYY-MM-DD.md / multiview_YYYY-MM-DD.md
    sorted_prefixes = sorted(INDUSTRY_PREFIXES, key=len, reverse=True)
    for prefix in sorted_prefixes:
        if fname.startswith(prefix):
            rest = fname[len(prefix):]
            m = re.match(r'(\d{4}-\d{2}-\d{2})', rest)
            if m:
                return prefix, m.group(1)
    # multiview_YYYY-MM-DD.md（industry_multiview.py 实际输出命名，无 _final）
    m = re.match(r'multiview_(\d{4}-\d{2}-\d{2})\.md$', fname)
    if m:
        return 'industry_multiview_', m.group(1)
    return None, None


def build_reports_json():
    all_reports = []
    seen_keys = set()
    all_files = sorted(glob.glob(os.path.join(OUTPUT, '*_final.md')) +
                       glob.glob(os.path.join(OUTPUT, 'multiview_*.md')), reverse=True)
    for fpath in all_files:
        fname = os.path.basename(fpath)
        prefix, date_str = find_longest_prefix(fname)
        if not prefix or not date_str:
            continue
        key = (date_str, prefix)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        with open(fpath, 'r', encoding='utf-8') as f:
            text = f.read()
        sector = INDUSTRY_NAMES.get(prefix, '其他')
        all_reports.append({
            "date": date_str,
            "sector": sector,
            "prefix": prefix,
            "title": f"{sector}行业日报",
            "summary": extract_summary(text),
            "heat": extract_heat_rating(text),
            "recommend": extract_recommend_rating(text),
            "opportunities": count_opportunities(text),
            "risks": count_risks(text),
            "url": f"/cross-validate/daily/{prefix}{date_str}.md",
        })
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M+08:00")
    return {"updated": now_str, "reports": all_reports}

def copy_daily_mds(reports):
    daily_dir = os.path.join(DOCS_DIR, "daily")
    os.makedirs(daily_dir, exist_ok=True)
    copied = 0
    for r in reports:
        # 优先精确匹配 _final.md；multiview 无 _final，用通配回退
        src = os.path.join(OUTPUT, f"{r['prefix']}{r['date']}_final.md")
        if os.path.exists(src):
            dst = os.path.join(daily_dir, f"{r['prefix']}{r['date']}.md")
            with open(src, 'r', encoding='utf-8') as f:
                with open(dst, 'w', encoding='utf-8') as f2:
                    f2.write(f.read())
            copied += 1
        else:
            candidates = sorted(glob.glob(os.path.join(OUTPUT, f"{r['prefix']}{r['date']}*.md")) +
                                glob.glob(os.path.join(OUTPUT, f"multiview_{r['date']}.md")), reverse=True)
            if candidates:
                with open(candidates[0], 'r', encoding='utf-8') as f:
                    with open(os.path.join(daily_dir, f"{r['prefix']}{r['date']}.md"), 'w', encoding='utf-8') as f2:
                        f2.write(f.read())
                copied += 1
    return copied

# ─── GitHub API 推送 ─────────────────────────────────────────────

def github_headers():
    return {
        'Authorization': f'token {GITHUB_PAT}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'xiaoling-bot',
        'Content-Type': 'application/json',
    }

def github_get_sha(api_path):
    """获取远程文件的 SHA，不存在返回 None"""
    url = f"{GITHUB_API}/{api_path}?ref={GITHUB_BRANCH}"
    req = Request(url, headers=github_headers())
    try:
        r = urlopen(req, timeout=15)
        return json.loads(r.read().decode()).get('sha')
    except HTTPError as e:
        if e.code == 404:
            return None
        raise

def github_upload(local_path, api_path):
    """用 GitHub API 创建/更新文件（409 冲突自动重试一次）"""
    if not os.path.exists(local_path):
        return False, "文件不存在"
    with open(local_path, 'r', encoding='utf-8') as f:
        content = f.read()
    b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {
        'message': f'小玲自动更新 {api_path}',
        'content': b64,
        'branch': GITHUB_BRANCH,
    }
    sha = github_get_sha(api_path)
    if sha:
        data['sha'] = sha
    url = f"{GITHUB_API}/{api_path}"
    req = Request(url, data=json.dumps(data).encode(), headers=github_headers(), method='PUT')
    try:
        r = urlopen(req, timeout=15)
        return True, ""
    except HTTPError as e:
        if e.code == 409:
            # SHA 冲突：重读远程 SHA 后重试一次（处理并发/竞态）
            import time
            time.sleep(1)
            sha2 = github_get_sha(api_path)
            if sha2 and sha2 != sha:
                data['sha'] = sha2
                req2 = Request(url, data=json.dumps(data).encode(), headers=github_headers(), method='PUT')
                try:
                    r2 = urlopen(req2, timeout=15)
                    return True, ""
                except HTTPError as e2:
                    body = e2.read().decode()[:300]
                    return False, f"HTTP {e2.code} (retry): {body}"
        body = e.read().decode()[:300]
        return False, f"HTTP {e.code}: {body}"

def push_via_api():
    """通过 GitHub REST API 推送所有文件"""
    global FAIL_LIST_GLOBAL
    ok_list = []
    fail_list = []
    FAIL_LIST_GLOBAL = fail_list

    def up(local, remote):
        ok, err = github_upload(local, remote)
        if ok:
            ok_list.append(remote)
        else:
            fail_list.append((remote, err))

    # index.html
    index_local = os.path.join(DOCS_DIR, "index.html")
    if os.path.exists(index_local):
        up(index_local, "docs/index.html")
    else:
        fail_list.append(("docs/index.html", "本地文件不存在"))

    # reports.json
    up(os.path.join(DOCS_DIR, "reports.json"), "docs/reports.json")

    # daily/*.md
    daily_dir = os.path.join(DOCS_DIR, "daily")
    if os.path.isdir(daily_dir):
        for fname in sorted(os.listdir(daily_dir)):
            if fname.endswith('.md'):
                local = os.path.join(daily_dir, fname)
                up(local, f"docs/daily/{fname}")

    total = len(ok_list) + len(fail_list)
    result = f"GitHub API: {len(ok_list)} OK / {len(fail_list)} FAIL (共 {total})"
    for remote, err in fail_list:
        print(f"     FAIL {remote}: {err}", file=sys.stderr)
    return result

# ─── Buttondown API（Newsletter 推送）──────────────────────────────────

def find_latest_daily_final():
    """查找当日行业日报 _final.md（industry_daily_YYYY-MM-DD_final.md，取日期最新）"""
    pattern = os.path.join(OUTPUT, 'industry_daily_*_final.md')
    candidates = glob.glob(pattern)
    if not candidates:
        return None
    # 按文件名中的日期排序，取最新
    def date_key(fpath):
        m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(fpath))
        return m.group(1) if m else ''
    candidates.sort(key=date_key, reverse=True)
    return candidates[0]


def push_buttondown_newsletter():
    """推送当日行业日报到 Buttondown Newsletter。

    - 无 API Key 时优雅跳过（返回 None，不报错）
    - 失败仅记日志，不影响 GitHub 推送主流程
    """
    if not BUTTONDOWN_API_KEY:
        print("    [Buttondown] 跳过：未配置 BUTTONDOWN_API_KEY 环境变量", file=sys.stderr)
        return None

    daily_path = find_latest_daily_final()
    if not daily_path:
        print("    [Buttondown] 跳过：未找到 industry_daily_*_final.md", file=sys.stderr)
        return None

    with open(daily_path, 'r', encoding='utf-8') as f:
        body_md = f.read()

    # subject 格式「AI行业日报 YYYY-MM-DD」
    m = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(daily_path))
    date_str = m.group(1) if m else datetime.now().strftime('%Y-%m-%d')
    subject = f"AI行业日报 {date_str}"

    payload = {
        "subject": subject,
        "body": body_md,  # Buttondown 支持 markdown
        "status": "draft",  # Buttondown API 无 published；创建 draft 后 PATCH about_to_send 触发发送
    }

    try:
        req = Request(
            BUTTONDOWN_API,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Token {BUTTONDOWN_API_KEY}',
                'Content-Type': 'application/json',
                'User-Agent': 'xiaoling-bot',
            },
            method='POST',
        )
        with urlopen(req, timeout=90) as resp:
            resp_body = resp.read().decode('utf-8', errors='replace')
            try:
                resp_json = json.loads(resp_body)
                email_id = resp_json.get('id', 'unknown')
            except Exception:
                email_id = 'unknown'
            print(f"    [Buttondown] ✅ 已创建 Newsletter (id={email_id}, subject={subject})", file=sys.stderr)

        # 触发发送：PATCH status=about_to_send
        patch_url = f"{BUTTONDOWN_API}/{email_id}"
        patch_req = Request(
            patch_url,
            data=json.dumps({"status": "about_to_send"}).encode('utf-8'),
            headers={
                'Authorization': f'Token {BUTTONDOWN_API_KEY}',
                'Content-Type': 'application/json',
                'User-Agent': 'xiaoling-bot',
            },
            method='PATCH',
        )
        with urlopen(patch_req, timeout=90) as presp:
            presp_body = presp.read().decode('utf-8', errors='replace')
            try:
                presp_json = json.loads(presp_body)
                pstatus = presp_json.get('status', 'unknown')
            except Exception:
                pstatus = 'unknown'
            print(f"    [Buttondown] ✅ 已触发发送 (status={pstatus})", file=sys.stderr)
            return email_id
    except Exception as e:
        print(f"    [Buttondown] ⚠️ 推送失败（不影响 GitHub 流程）: {e}", file=sys.stderr)
        return None


# ─── 主流程 ───────────────────────────────────────────────────────

def main():
    """入口：先取互斥锁，避免并发推送导致 GitHub 409 SHA 冲突。"""
    if not acquire_lock():
        sys.exit(2)
    try:
        _run_main()
    finally:
        release_lock()

def _run_main():
    print("小玲 Pages 自动推送 v3.1 (GitHub API + 分发回执 + 互斥锁)", file=sys.stderr)

    print("[1/3] 构建 reports.json...", file=sys.stderr)
    data = build_reports_json()
    reports = data["reports"]
    sectors = sorted(set(r['sector'] for r in reports))
    print(f"   {len(reports)} 篇日报 ({', '.join(sectors)})", file=sys.stderr)

    with open(os.path.join(DOCS_DIR, "reports.json"), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("[2/3] 复制日报到 docs/daily/...", file=sys.stderr)
    copied = copy_daily_mds(reports)
    print(f"   已复制 {copied} 篇", file=sys.stderr)

    print("[3/3] 通过 GitHub API 推送...", file=sys.stderr)
    gh_result = push_via_api()
    print(f"   {gh_result}", file=sys.stderr)

    print("[4/4] 推送 Buttondown Newsletter...", file=sys.stderr)
    bd_result = push_buttondown_newsletter()

    # ── 解析 GitHub 推送结果，生成回执 ──
    gh_ok = gh_fail = 0
    fail_detail = []
    if gh_result.startswith("GitHub API:"):
        m = re.search(r'(\d+) OK / (\d+) FAIL', gh_result)
        if m:
            gh_ok, gh_fail = int(m.group(1)), int(m.group(2))
            # 从 fail_list 取明细
            if gh_fail > 0:
                # push_via_api 打印在 stderr；此处从全局收集失败明细
                fail_detail = [{"file": f[0], "error": f[1]} for f in FAIL_LIST_GLOBAL]

    status = "ok"
    if gh_fail > 0:
        status = "partial" if gh_ok > 0 else "fail"

    summary = {
        "files_total": gh_ok + gh_fail,
        "files_ok": gh_ok,
        "files_fail": gh_fail,
        "reports_count": len(reports),
        "copied": copied,
        "sectors": sectors,
        "github": gh_result,
        "buttondown": "skipped" if bd_result is None else "sent",
        "buttondown_email_id": bd_result,
    }
    receipt_path = write_receipt(status, summary, fail_detail)
    summary["receipt_path"] = receipt_path

    result = {
        "status": status,
        "reports_count": len(reports),
        "sectors": sectors,
        "copied": copied,
        "github": gh_result,
        "github_url": "https://anzi9527.github.io/cross-validate/",
        "buttondown": "skipped" if bd_result is None else "sent",
        "buttondown_email_id": bd_result,
        "receipt_path": receipt_path,
    }
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
