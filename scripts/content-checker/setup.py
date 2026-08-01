"""Content Checker - 发文前内容合规检查工具"""
from setuptools import setup, find_packages

setup(
    name="content-checker",
    version="1.0.0",
    description="AI发文前内容合规检查器 — 检查敏感词、违规内容、平台规范",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="小玲 AI Tools",
    author_email="tools@xiaoling.ai",
    url="https://github.com/xiaoling/content-checker",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[],
    entry_points={
        "console_scripts": [
            "content-checker=content_checker.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Software Development :: Quality Assurance",
    ],
    python_requires=">=3.7",
)
