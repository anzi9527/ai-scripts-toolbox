#!/usr/bin/env python3
"""
B站/抖音视频发布器 — 自动上传和发布视频
使用 Cookie 登录态（需用户手动提供，定期更新）
"""

import sys
import json
import io
import os
import re
import time
import ssl
import urllib.request
import urllib.parse
import hashlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── B站发布 ──────────────────────────────

BILI_SESSDATA = None
BILI_BILI_JCT = None
BILI_DEDE_USER_ID = None
DOUYIN_SESSION_ID = None

def load_credentials():
    """从 openclaw.json env 或 local config 加载 Cookie"""
    global BILI_SESSDATA, BILI_BILI_JCT, BILI_DEDE_USER_ID, DOUYIN_SESSION_ID

    config_path = None
    possible = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        os.path.expanduser("~/.openclaw/openclaw.json5")
    ]
    for p in possible:
        if os.path.exists(p):
            config_path = p
            break

    if config_path:
        with open(config_path, "r", encoding="utf-8", errors="replace") as f:
            try:
                cfg = json.load(f)
                env = cfg.get("env", {}) or {}
            except json.JSONDecodeError:
                env = {}
        BILI_SESSDATA = env.get("BILI_SESSDATA") or BILI_SESSDATA
        BILI_BILI_JCT = env.get("BILI_BILI_JCT") or BILI_BILI_JCT
        BILI_DEDE_USER_ID = env.get("BILI_DEDE_USER_ID") or BILI_DEDE_USER_ID


def _bili_request(method, url, data=None, headers_extra=None):
    """带 cookie 的 B站 HTTP 请求"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/",
        "Cookie": f"SESSDATA={BILI_SESSDATA}; bili_jct={BILI_BILI_JCT}; DedeUserID={BILI_DEDE_USER_ID}",
    }
    if headers_extra:
        headers.update(headers_extra)

    if data is not None and isinstance(data, dict):
        data = urllib.parse.urlencode(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
        return {"code": -1, "message": str(e), "body": body}


def bili_test_login():
    """测试 B站 Cookie 是否有效"""
    result = _bili_request("GET", "https://api.bilibili.com/x/web-interface/nav")
    if result.get("code") == 0:
        data = result.get("data", {})
        uname = data.get("uname", "unknown")
        uid = data.get("mid", 0)
        level = data.get("level_info", {}).get("current_level", 0)
        return {"ok": True, "name": uname, "uid": uid, "level": level, "raw": result}
    return {"ok": False, "error": result.get("message", "Login failed"), "raw": result}


def bili_get_categories():
    """获取 B站 视频分区"""
    result = _bili_request("GET", "https://api.bilibili.com/x/web-interface/nav")
    if result.get("code") == 0:
        data = result.get("data", {})
        return {"ok": True, "name": data.get("uname"), "revenue": data.get("wallet", {}).get("bcoin_balance", 0)}


def bili_upload_video(filepath, title, desc, tid=174, tags="AI,科技"):
    """
    上传视频到 B站
    tid: 分区ID (174=AI/科技, 181=编程, 124=科普)
    """
    if not os.path.exists(filepath):
        return {"ok": False, "error": f"file not found: {filepath}"}

    filesize = os.path.getsize(filepath)
    fname = os.path.basename(filepath)

    # Step 1: 预上传 — 获取上传地址
    pre = _bili_request(
        "POST",
        "https://member.bilibili.com/x/vup/re/pre",
        data={
            "name": fname,
            "size": filesize,
            "r": "upos",
            "profile": "ugcfv:pc3",
            "mimetype": "video/mp4",
        }
    )
    if pre.get("code") != 0:
        return {"ok": False, "error": f"pre-upload failed: {pre}", "raw": pre}
    up_meta = pre.get("data", {})
    upload_url = up_meta.get("upos_uri", "")
    upload_id = up_meta.get("upload_id", "")
    biz_id = up_meta.get("biz_id", "")

    # Step 2: 分片上传（简化版 — 小文件不分片）
    # 对于 < 100MB 的文件可以直接 PUT 上传
    if filesize < 100 * 1024 * 1024:
        # 直接用 PUT 流式上传
        with open(filepath, "rb") as f:
            file_data = f.read()

        # 上传到 upos 地址
        upload_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "video/mp4",
        }
        up_url = upload_url.replace("upos://", "https://upos-cos.uposcdn.com/")
        req = urllib.request.Request(up_url, data=file_data, headers=upload_headers, method="PUT")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(req, timeout=600, context=ctx) as resp:
                upload_result = resp.read().decode()
        except Exception as e:
            return {"ok": False, "error": f"upload failed: {e}"}

        # Step 3: 提交稿件
        submit = _bili_request(
            "POST",
            "https://member.bilibili.com/x/vup/re/cover",
            data={
                "title": title,
                "desc": desc,
                "tid": tid,
                "tag": tags,
                "filename": fname,
                "source": "",
                "cover": "",
                "biz_id": biz_id,
                "upload_id": upload_id,
                "copyright": 2,  # 2 = 自制
            }
        )
        if submit.get("code") == 0:
            aid = submit.get("data", {}).get("aid", "unknown")
            return {"ok": True, "aid": aid, "title": title, "platform": "bilibili"}
        else:
            return {"ok": False, "error": f"submit failed: {submit}", "raw": submit}
    else:
        return {"ok": False, "error": "file too large, chunk upload not implemented"}


def douyin_upload_video(filepath, title, desc=""):
    """
    抖音视频上传（Cookie 版）
    使用 sessionid Cookie 维护登录态
    """
    # TODO: 抖音上传接口相对复杂（需要抓上传地址 → 分片上传 → 发布）
    # 需要先验证 Cookie 有效
    return {"ok": False, "note": "抖音上传暂时需要额外调试，先聚焦B站"}


def test_all():
    """验证两个平台的 Cookie 是否有效"""
    load_credentials()
    results = {}

    # B站
    print("=== B站 登录测试 ===")
    b = bili_test_login()
    print(f"  OK: {b.get('ok')}")
    if b.get("ok"):
        print(f"  用户: {b.get('name')} (UID: {b.get('uid')}, Lv.{b.get('level')})")
    else:
        print(f"  失败: {b.get('error')}")
    results["bilibili"] = b

    # 抖音（占位）
    print("=== 抖音 登录测试（待实现）===")
    results["douyin"] = {"ok": False, "note": "not implemented"}

    return results


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        results = test_all()
        print(f"\n最终结果: B站={'✅' if results['bilibili']['ok'] else '❌'}")
    elif len(sys.argv) > 1 and sys.argv[1] == "upload":
        fp = sys.argv[2] if len(sys.argv) > 2 else None
        title = sys.argv[3] if len(sys.argv) > 3 else "AI视频"
        desc = "在特定领域寻找中国答案" if len(sys.argv) <= 4 else sys.argv[4]
        if fp and os.path.exists(fp):
            load_credentials()
            r = bili_upload_video(fp, title, desc)
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(f"Usage: {sys.argv[0]} upload <filepath> [title] [desc]")
    else:
        print("Usage: python3 video_publisher.py test|upload <filepath> [title] [desc]")
