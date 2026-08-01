"""测试 content-checker 包"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from content_checker import check_text, check_file, scan_directory


def test_clean_text():
    """合规文本应该无任何违规"""
    content = "今天天气真好，适合写Python代码。"
    results = check_text(content)
    assert len(results["red_flags"]) == 0, f"预期0违规，实际 {len(results['red_flags'])}"
    assert len(results["yellow_flags"]) == 0
    print("✅ test_clean_text PASS")


def test_red_violation():
    """红线词应该被检测到"""
    content = "今天我们用翻墙工具来看看外面的世界。"
    results = check_text(content)
    assert len(results["red_flags"]) > 0, "应该检测到翻墙"
    print(f"✅ test_red_violation PASS — 检测到 {len(results['red_flags'])} 个红线词")


def test_yellow_violation():
    """黄线词应该被检测到"""
    content = "推荐使用V2Ray工具。"
    results = check_text(content)
    assert len(results["yellow_flags"]) > 0, "应该检测到V2Ray"
    print(f"✅ test_yellow_violation PASS — 检测到 {len(results['yellow_flags'])} 个黄线词")


def test_too_many_links():
    """过多外链应该触发警告"""
    links = " ".join([f"https://example{i}.com" for i in range(20)])
    results = check_text(links)
    assert results["checks"]["external_links"] > 10
    yellow_link_warnings = [f for f in results["yellow_flags"] if "外链过多" in f["word"]]
    assert len(yellow_link_warnings) > 0
    print("✅ test_too_many_links PASS")


def test_bad_file():
    """检查实际文件"""
    filepath = os.path.join(os.path.dirname(__file__), "..", "examples", "bad_article.md")
    results, verdict = check_file(filepath)
    assert "❌" in verdict, f"应该判定为禁止发布，实际: {verdict}"
    print(f"✅ test_bad_file PASS — {verdict}")


if __name__ == "__main__":
    test_clean_text()
    test_red_violation()
    test_yellow_violation()
    test_too_many_links()
    test_bad_file()
    print("\n🎉 全部测试通过!")
