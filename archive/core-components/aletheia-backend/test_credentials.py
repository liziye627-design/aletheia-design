#!/usr/bin/env python3
"""
凭证验证脚本 - 检查 .env 文件中的所有凭证是否已配置

使用方法:
    python test_credentials.py
"""

import os
from pathlib import Path


def load_env_file(env_path: str) -> dict:
    """手动加载 .env 文件"""
    credentials = {}

    if not os.path.exists(env_path):
        print(f"⚠️ 警告: .env文件不存在: {env_path}")
        return credentials

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            # 跳过注释和空行
            if not line or line.startswith("#"):
                continue

            # 解析 KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if value:
                    credentials[key] = value

    return credentials


def check_credentials():
    """检查所有凭证"""

    # .env 文件路径
    env_path = "docker/.env"

    print("=" * 70)
    print("🔍 Aletheia 凭证检查工具")
    print("=" * 70)
    print(f"\n正在检查: {env_path}\n")

    # 加载凭证
    credentials = load_env_file(env_path)

    # 所有需要的凭证
    required_credentials = {
        "社交媒体平台": [
            ("WEIBO_COOKIES", "微博", "high"),
            ("TWITTER_BEARER_TOKEN", "Twitter/X", "high"),
            ("XHS_COOKIES", "小红书", "high"),
            ("DOUYIN_COOKIES", "抖音", "medium"),
            ("ZHIHU_COOKIES", "知乎", "high"),
            ("BILIBILI_COOKIES", "B站", "high"),
            ("KUAISHOU_COOKIES", "快手", "medium"),
            ("DOUBAN_COOKIES", "豆瓣", "medium"),
        ],
        "API凭证": [
            ("REDDIT_CLIENT_ID", "Reddit Client ID", "medium"),
            ("REDDIT_CLIENT_SECRET", "Reddit Client Secret", "medium"),
            ("GITHUB_TOKEN", "GitHub Token", "high"),
            ("STACKOVERFLOW_API_KEY", "Stack Overflow API Key", "low"),
        ],
        "学术数据集": [
            ("OPENALEX_EMAIL", "OpenAlex 邮箱", "medium"),
        ],
    }

    # 统计
    total_count = 0
    set_count = 0
    high_priority_count = 0
    high_priority_set = 0

    # 按类别检查
    for category, creds in required_credentials.items():
        print(f"\n{'=' * 70}")
        print(f"📂 {category}")
        print(f"{'=' * 70}\n")

        for key, name, priority in creds:
            total_count += 1
            if priority == "high":
                high_priority_count += 1

            value = credentials.get(key)

            if value:
                set_count += 1
                if priority == "high":
                    high_priority_set += 1

                # 显示预览
                preview = f"{value[:50]}..." if len(value) > 50 else value

                # 优先级标记
                priority_emoji = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢",
                }

                print(f"✅ {priority_emoji.get(priority, '⚪')} {name:30} {preview}")
            else:
                # 未设置
                priority_emoji = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢",
                }

                print(f"❌ {priority_emoji.get(priority, '⚪')} {name:30} 未设置")

    # 打印摘要
    print(f"\n{'=' * 70}")
    print("📊 摘要")
    print(f"{'=' * 70}\n")

    print(f"总凭证数: {total_count}")
    print(f"已配置: {set_count} / {total_count} ({set_count / total_count * 100:.1f}%)")
    print(
        f"\n高优先级凭证: {high_priority_set} / {high_priority_count} ({high_priority_set / high_priority_count * 100:.1f}%)"
    )

    # 完成度判断
    if set_count == total_count:
        print("\n🎉 恭喜！所有凭证已配置完成！")
        status = "完美"
    elif high_priority_set == high_priority_count:
        print("\n✅ 高优先级凭证已全部配置！")
        status = "良好"
    elif high_priority_set > 0:
        print("\n⚠️ 部分高优先级凭证未配置，建议补充")
        status = "一般"
    else:
        print("\n❌ 未配置任何高优先级凭证，请尽快配置")
        status = "较差"

    print(f"\n配置状态: {status}")

    # 缺失的高优先级凭证
    missing_high = []
    for category, creds in required_credentials.items():
        for key, name, priority in creds:
            if priority == "high" and key not in credentials:
                missing_high.append((name, key))

    if missing_high:
        print(f"\n{'=' * 70}")
        print("🔴 缺失的高优先级凭证:")
        print(f"{'=' * 70}\n")
        for name, key in missing_high:
            print(f"  • {name} ({key})")
        print("\n请参考以下文档获取凭证:")
        print("  1. QUICK_CREDENTIALS_GUIDE.md (快速指南)")
        print("  2. MCP_COOKIES_GUIDE.md (MCP工具详细指南)")
        print("  3. 运行: python get_all_credentials.py (自动化脚本)")

    print(f"\n{'=' * 70}\n")

    return set_count == total_count


def main():
    """主函数"""
    try:
        success = check_credentials()
        exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ 检查过程中发生错误: {e}")
        import traceback

        traceback.print_exc()
        exit(1)


if __name__ == "__main__":
    main()
