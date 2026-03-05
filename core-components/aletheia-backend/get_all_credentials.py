#!/usr/bin/env python3
"""
凭证批量获取助手
使用Selenium自动化获取所有平台的cookies和tokens

依赖:
    pip install selenium webdriver-manager

使用方法:
    python get_all_credentials.py
"""

import json
import time
from typing import Dict, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


class CredentialCollector:
    """凭证收集器 - 使用Selenium自动化获取cookies"""

    def __init__(self):
        """初始化Chrome浏览器"""
        chrome_options = Options()
        # chrome_options.add_argument('--headless')  # 如果需要无头模式，取消注释
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        # 设置User-Agent
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=chrome_options
        )

        self.credentials = {}

    def get_cookies_string(self) -> str:
        """获取当前页面的cookies并转换为字符串"""
        cookies = self.driver.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        return cookie_str

    def wait_for_login(self, platform: str, check_url_contains: str = None):
        """等待用户手动登录"""
        print(f"\n{'=' * 60}")
        print(f"正在等待 {platform} 登录...")
        print(f"当前页面: {self.driver.current_url}")
        print(f"{'=' * 60}")
        print("请在浏览器中完成登录（扫码或密码登录）")
        print("登录成功后，按回车键继续...\n")

        input("按回车键继续 >>> ")

        # 验证登录成功
        if check_url_contains:
            current_url = self.driver.current_url
            if check_url_contains in current_url:
                print(f"✅ {platform} 登录成功！")
                return True
            else:
                print(f"⚠️ 警告: URL不包含 '{check_url_contains}'，可能登录未成功")
                retry = input("是否重试？(y/n) >>> ")
                if retry.lower() == "y":
                    return self.wait_for_login(platform, check_url_contains)

        return True

    # ==================== 社交媒体平台 ====================

    def get_weibo_cookies(self):
        """获取微博cookies"""
        print("\n📱 1/12 - 微博 (Weibo)")
        self.driver.get("https://weibo.com")

        if self.wait_for_login("微博", "weibo.com"):
            cookies = self.get_cookies_string()
            self.credentials["WEIBO_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_xiaohongshu_cookies(self):
        """获取小红书cookies"""
        print("\n📱 2/12 - 小红书 (Xiaohongshu)")
        self.driver.get("https://www.xiaohongshu.com")

        if self.wait_for_login("小红书", "xiaohongshu.com"):
            cookies = self.get_cookies_string()
            self.credentials["XHS_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_douyin_cookies(self):
        """获取抖音cookies"""
        print("\n📱 3/12 - 抖音 (Douyin)")
        self.driver.get("https://www.douyin.com")

        if self.wait_for_login("抖音", "douyin.com"):
            cookies = self.get_cookies_string()
            self.credentials["DOUYIN_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_zhihu_cookies(self):
        """获取知乎cookies"""
        print("\n📱 4/12 - 知乎 (Zhihu)")
        self.driver.get("https://www.zhihu.com")

        if self.wait_for_login("知乎", "zhihu.com"):
            cookies = self.get_cookies_string()
            self.credentials["ZHIHU_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_bilibili_cookies(self):
        """获取B站cookies"""
        print("\n📱 5/12 - B站 (Bilibili)")
        self.driver.get("https://www.bilibili.com")

        if self.wait_for_login("B站", "bilibili.com"):
            cookies = self.get_cookies_string()
            self.credentials["BILIBILI_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_kuaishou_cookies(self):
        """获取快手cookies"""
        print("\n📱 6/12 - 快手 (Kuaishou)")
        self.driver.get("https://www.kuaishou.com")

        if self.wait_for_login("快手", "kuaishou.com"):
            cookies = self.get_cookies_string()
            self.credentials["KUAISHOU_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    def get_douban_cookies(self):
        """获取豆瓣cookies"""
        print("\n📱 7/12 - 豆瓣 (Douban)")
        self.driver.get("https://www.douban.com")

        if self.wait_for_login("豆瓣", "douban.com"):
            cookies = self.get_cookies_string()
            self.credentials["DOUBAN_COOKIES"] = cookies
            print(f"✅ 获取到cookies: {cookies[:100]}...")

    # ==================== API凭证 ====================

    def get_twitter_bearer_token(self):
        """获取Twitter Bearer Token"""
        print("\n🐦 8/12 - Twitter/X Bearer Token")
        print("正在打开Twitter Developer Portal...")
        self.driver.get("https://developer.twitter.com/en/portal/dashboard")

        print("\n请按照以下步骤操作:")
        print("1. 登录Twitter开发者账号")
        print("2. 创建或选择一个App")
        print("3. 进入 'Keys and Tokens' 标签")
        print("4. 生成或查看 Bearer Token")
        print("5. 复制Bearer Token\n")

        token = input("请粘贴Bearer Token >>> ").strip()
        if token:
            self.credentials["TWITTER_BEARER_TOKEN"] = token
            print("✅ Twitter Bearer Token已保存")

    def get_reddit_credentials(self):
        """获取Reddit API credentials"""
        print("\n🔴 9/12 - Reddit API Credentials")
        print("正在打开Reddit Apps页面...")
        self.driver.get("https://www.reddit.com/prefs/apps")

        print("\n请按照以下步骤操作:")
        print("1. 登录Reddit账号")
        print("2. 点击 'Create App' 或 'Create Another App'")
        print("3. 填写:")
        print("   - Name: Aletheia Crawler")
        print("   - App type: script")
        print("   - Redirect URI: http://localhost:8080")
        print("4. 点击 'Create app'")
        print("5. 记录 Client ID (在app名称下方) 和 Client Secret\n")

        client_id = input("请输入Reddit Client ID >>> ").strip()
        client_secret = input("请输入Reddit Client Secret >>> ").strip()

        if client_id and client_secret:
            self.credentials["REDDIT_CLIENT_ID"] = client_id
            self.credentials["REDDIT_CLIENT_SECRET"] = client_secret
            print("✅ Reddit凭证已保存")

    def get_github_token(self):
        """获取GitHub Personal Access Token"""
        print("\n🐱 10/12 - GitHub Personal Access Token")
        print("正在打开GitHub Token页面...")
        self.driver.get("https://github.com/settings/tokens")

        print("\n请按照以下步骤操作:")
        print("1. 登录GitHub账号")
        print("2. 点击 'Generate new token' → 'Generate new token (classic)'")
        print("3. 填写:")
        print("   - Note: Aletheia Crawler")
        print("   - Expiration: 选择有效期")
        print("   - Scopes: 勾选 public_repo")
        print("4. 点击 'Generate token'")
        print("5. 复制token (只显示一次!)\n")

        token = input("请粘贴GitHub Token >>> ").strip()
        if token:
            self.credentials["GITHUB_TOKEN"] = token
            print("✅ GitHub Token已保存")

    def get_stackoverflow_api_key(self):
        """获取Stack Overflow API Key (可选)"""
        print("\n📚 11/12 - Stack Overflow API Key (可选)")
        print("正在打开Stack Apps注册页面...")
        self.driver.get("https://stackapps.com/apps/oauth/register")

        print("\n请按照以下步骤操作 (可跳过):")
        print("1. 登录Stack Overflow账号")
        print("2. 填写:")
        print("   - Application Name: Aletheia Crawler")
        print("   - OAuth Domain: localhost")
        print("3. 提交后获得 API Key\n")

        api_key = input("请输入API Key (直接回车跳过) >>> ").strip()
        if api_key:
            self.credentials["STACKOVERFLOW_API_KEY"] = api_key
            print("✅ Stack Overflow API Key已保存")
        else:
            print("⏭️ 已跳过Stack Overflow API Key")

    def get_openalex_email(self):
        """配置OpenAlex邮箱"""
        print("\n📖 12/12 - OpenAlex联系邮箱")
        print("OpenAlex是完全免费的API，不需要注册")
        print("但建议提供邮箱以获得更高速率限制 (10 req/s → 100 req/s)\n")

        email = input("请输入您的邮箱 >>> ").strip()
        if email:
            self.credentials["OPENALEX_EMAIL"] = email
            print("✅ OpenAlex邮箱已保存")

    def run_all(self, platforms=None):
        """运行所有凭证获取"""
        if platforms is None:
            platforms = [
                "weibo",
                "xiaohongshu",
                "douyin",
                "zhihu",
                "bilibili",
                "kuaishou",
                "douban",
                "twitter",
                "reddit",
                "github",
                "stackoverflow",
                "openalex",
            ]

        print("\n" + "=" * 60)
        print("🚀 Aletheia 凭证批量获取助手")
        print("=" * 60)
        print(f"将获取 {len(platforms)} 个平台的凭证")
        print("请准备好各平台的账号密码/扫码工具\n")

        input("按回车键开始 >>> ")

        # 映射平台到方法
        platform_methods = {
            "weibo": self.get_weibo_cookies,
            "xiaohongshu": self.get_xiaohongshu_cookies,
            "douyin": self.get_douyin_cookies,
            "zhihu": self.get_zhihu_cookies,
            "bilibili": self.get_bilibili_cookies,
            "kuaishou": self.get_kuaishou_cookies,
            "douban": self.get_douban_cookies,
            "twitter": self.get_twitter_bearer_token,
            "reddit": self.get_reddit_credentials,
            "github": self.get_github_token,
            "stackoverflow": self.get_stackoverflow_api_key,
            "openalex": self.get_openalex_email,
        }

        # 执行获取
        for platform in platforms:
            if platform in platform_methods:
                try:
                    platform_methods[platform]()
                except Exception as e:
                    print(f"❌ {platform} 获取失败: {e}")
                    continue

        # 保存结果
        self.save_credentials()

    def save_credentials(self):
        """保存凭证到文件"""
        print("\n" + "=" * 60)
        print("💾 保存凭证")
        print("=" * 60)

        # 保存为.env格式
        env_file = "aletheia-backend/docker/.env"

        print(f"\n正在保存到: {env_file}")

        env_content = "# Aletheia 爬虫凭证配置\n"
        env_content += f"# 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        # 分类保存
        env_content += "# ==================== 社交媒体平台 ====================\n"
        for key in [
            "WEIBO_COOKIES",
            "TWITTER_BEARER_TOKEN",
            "XHS_COOKIES",
            "DOUYIN_COOKIES",
            "ZHIHU_COOKIES",
            "BILIBILI_COOKIES",
            "KUAISHOU_COOKIES",
            "DOUBAN_COOKIES",
        ]:
            if key in self.credentials:
                env_content += f'{key}="{self.credentials[key]}"\n'

        env_content += "\n# ==================== Reddit ====================\n"
        for key in ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]:
            if key in self.credentials:
                env_content += f'{key}="{self.credentials[key]}"\n'

        env_content += "\n# ==================== 社区论坛 ====================\n"
        for key in ["GITHUB_TOKEN", "STACKOVERFLOW_API_KEY"]:
            if key in self.credentials:
                env_content += f'{key}="{self.credentials[key]}"\n'

        env_content += "\n# ==================== 学术数据集 ====================\n"
        if "OPENALEX_EMAIL" in self.credentials:
            env_content += f'OPENALEX_EMAIL="{self.credentials["OPENALEX_EMAIL"]}"\n'

        # 写入文件
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(env_content)

        print(f"✅ 凭证已保存到: {env_file}")

        # 也保存为JSON格式（用于调试）
        json_file = "credentials_backup.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(self.credentials, f, indent=2, ensure_ascii=False)

        print(f"✅ 备份已保存到: {json_file}")

        # 打印摘要
        print("\n" + "=" * 60)
        print("📊 凭证获取摘要")
        print("=" * 60)
        print(f"成功获取: {len(self.credentials)} 个凭证")
        for key in self.credentials:
            print(f"  ✅ {key}")

        print("\n" + "=" * 60)
        print("🎉 所有凭证获取完成！")
        print("=" * 60)
        print(f"\n请查看: {env_file}")
        print("\n⚠️ 注意: 请勿将凭证文件提交到版本控制系统！")

    def close(self):
        """关闭浏览器"""
        self.driver.quit()


def main():
    """主函数"""
    collector = CredentialCollector()

    try:
        # 运行所有平台的凭证获取
        collector.run_all()

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断操作")
        collector.save_credentials()

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback

        traceback.print_exc()

    finally:
        collector.close()


if __name__ == "__main__":
    main()
