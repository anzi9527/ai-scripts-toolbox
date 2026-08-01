"""
命令行入口 — content-checker
"""

import sys
import os
import json
try:
    from .core import check_file, check_text, scan_directory, print_report
except ImportError:
    # 允许直接运行 python cli.py
    from core import check_file, check_text, scan_directory, print_report

def main():
    """主入口"""
    if len(sys.argv) < 2:
        print(__doc__)
        print()
        print("用法:")
        print("  content-checker check <文件路径>    检查单个文件")
        print("  content-checker scan [目录路径]      扫描目录下所有 .md 文件")
        print("  content-checker json <文件路径>      输出 JSON 格式结果")
        print("  content-checker --help               显示帮助")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd in ("--help", "-h"):
        print("content-checker v1.0.0 — 发文前内容合规检查工具")
        print()
        print("用法:")
        print("  content-checker check <文件路径>    检查单个文件")
        print("  content-checker scan [目录路径]      扫描目录下所有 .md 文件")
        print("  content-checker json <文件路径>      输出 JSON 格式结果")
        return

    if cmd == "check":
        if len(sys.argv) < 3:
            print("❌ 请指定文件路径")
            sys.exit(1)
        path = sys.argv[2]
        if not os.path.isfile(path):
            print(f"❌ 文件不存在: {path}")
            sys.exit(1)
        results, verdict = check_file(path)
        print_report(results, verdict)

    elif cmd == "scan":
        dirpath = sys.argv[2] if len(sys.argv) > 2 else "."
        results = scan_directory(dirpath)
        if not results:
            return
        all_pass = True
        for fname, _, _ in results:
            if not any(r["red_flags"] for r in [results[0][1]] if r["file"] == fname):
                pass  # we need a cleaner check
        print(f"\n📋 共 {len(results)} 个文件检查完成")
        for fname, r, v in results:
            symbol = "✅" if "合规" in v else ("⚠️" if "警告" in v or "修改" in v else "❌")
            print(f"  {symbol} {fname} → {v}")
            if "❌" in v:
                all_pass = False
        if all_pass:
            print("  ✅ 所有文件合规，可以发布")
        else:
            print("  ⚠️ 存在违规文件，请修改后重试")

    elif cmd == "json":
        if len(sys.argv) < 3:
            print("❌ 请指定文件路径")
            sys.exit(1)
        path = sys.argv[2]
        if not os.path.isfile(path):
            print(f"❌ 文件不存在: {path}")
            sys.exit(1)
        results, verdict = check_file(path)
        output = {"results": results, "verdict": verdict}
        print(json.dumps(output, ensure_ascii=False, indent=2))

    else:
        print(f"❌ 未知命令: {cmd}")
        print("可用命令: check, scan, json")
        sys.exit(1)


if __name__ == "__main__":
    main()
