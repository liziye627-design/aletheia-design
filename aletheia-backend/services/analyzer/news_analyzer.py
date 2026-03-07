# -*- coding: utf-8 -*-
"""
News Analyzer
新闻分析器

- 提取最近20条新闻
- 爬取新闻原文
- 使用小模型生成逻辑分析链条
"""

import asyncio
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from services.crawler.multi_source_news_searcher import NewsItem


@dataclass
class NewsAnalysis:
    """新闻分析结果"""
    news_item: NewsItem
    full_content: str
    analysis: str
    relevance_score: float = 0.0  # 相关度分数
    credibility_score: float = 0.0  # 可信度分数
    analysis_time: datetime = None
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.analysis_time is None:
            self.analysis_time = datetime.now()
    
    def _parse_analysis(self, analysis_text):
        """解析分析文本为结构化数据"""
        import re
        
        # 初始化结果
        parsed = {
            "core_claim": "",
            "premises": [],
            "evidence": [],
            "reasoning_steps": [],
            "conclusion": "",
            "relevance": self.relevance_score
        }
        
        if not analysis_text:
            return parsed
        
        # 提取核心主张
        core_match = re.search(r'1\. 核心主张 / 结论：\s*(-.*?)(?=2\. 前提 / 假设：|$)', 
                            analysis_text, re.DOTALL)
        if core_match:
            core_text = core_match.group(1).strip()
            if core_text.startswith('-'):
                core_text = core_text[1:].strip()
            parsed["core_claim"] = core_text
        
        # 提取前提/假设
        premises_match = re.search(r'2\. 前提 / 假设：\s*(.*?)(?=3\. 支撑证据：|$)', 
                                analysis_text, re.DOTALL)
        if premises_match:
            premises_text = premises_match.group(1).strip()
            # 分割多个前提
            premises = re.split(r'\s*-\s*', premises_text)
            premises = [p.strip() for p in premises if p.strip()]
            parsed["premises"] = premises
        
        # 提取支撑证据
        evidence_match = re.search(r'3\. 支撑证据：\s*(.*?)(?=4\. 推理步骤：|$)', 
                                analysis_text, re.DOTALL)
        if evidence_match:
            evidence_text = evidence_match.group(1).strip()
            # 分割多个证据
            evidence = re.split(r'\s*-\s*', evidence_text)
            evidence = [e.strip() for e in evidence if e.strip()]
            parsed["evidence"] = evidence
        
        # 提取推理步骤
        reasoning_match = re.search(r'4\. 推理步骤：\s*(.*?)(?=5\. 结论 / 后续行动：|$)', 
                                analysis_text, re.DOTALL)
        if reasoning_match:
            reasoning_text = reasoning_match.group(1).strip()
            # 提取步骤（数字开头）
            steps = re.findall(r'\d+\.\s*(.*?)(?=\d+\.\s*|$)', reasoning_text, re.DOTALL)
            steps = [s.strip() for s in steps if s.strip()]
            parsed["reasoning_steps"] = steps
        
        # 提取结论/后续行动
        conclusion_match = re.search(r'5\. 结论 / 后续行动：\s*(.*?)(?=6\. 相关度评估：|$)', 
                                  analysis_text, re.DOTALL)
        if conclusion_match:
            conclusion_text = conclusion_match.group(1).strip()
            if conclusion_text.startswith('-'):
                conclusion_text = conclusion_text[1:].strip()
            parsed["conclusion"] = conclusion_text
        
        # 提取相关度（如果需要覆盖默认值）
        relevance_match = re.search(r'6\. 相关度评估：\s*(-\s*|)([0-9.]+)', analysis_text)
        if relevance_match:
            try:
                parsed["relevance"] = float(relevance_match.group(2))
            except:
                pass
        
        return parsed
    
    def to_dict(self):
        """转换为字典"""
        parsed_analysis = self._parse_analysis(self.analysis)
        
        return {
            "url": self.news_item.url,
            "source": self.news_item.source,  # 使用提取到的具体信源（如中国新闻网）
            "source_domain": self.news_item.source_domain,  # 保留域名信息
            "credibility": self.credibility_score,
            "time": self.news_item.publish_time.isoformat() if self.news_item.publish_time else None,
            "relevance": self.relevance_score,
            "analysis": {
                "core_claim": parsed_analysis["core_claim"],
                "premises": parsed_analysis["premises"],
                "evidence": parsed_analysis["evidence"],
                "reasoning_steps": parsed_analysis["reasoning_steps"],
                "conclusion": parsed_analysis["conclusion"]
            }
        }


class NewsAnalyzer:
    """新闻分析器"""
    
    def __init__(self, silicon_flow_api_key: str = None, timeout: float = 60.0):
        import os
        self.silicon_flow_api_key = silicon_flow_api_key or os.getenv('SILICONFLOW_API_KEY')
        self.timeout = timeout
        # 使用 .env 中配置的 API 基础 URL
        self.silicon_flow_url = os.getenv('SILICONFLOW_API_BASE', 'https://api.siliconflow.cn/v1') + "/chat/completions"
    
    async def extract_recent_news(self, news_items: List[NewsItem], top_n: int = 20) -> List[NewsItem]:
        """提取最近的新闻"""
        # 按发布时间排序，优先选择有明确发布时间的新闻
        sorted_news = sorted(
            news_items,
            key=lambda x: x.publish_time or datetime.min,
            reverse=True
        )
        
        # 取前20条
        recent_news = sorted_news[:top_n]
        logger.info(f"提取了 {len(recent_news)} 条最近新闻")
        return recent_news
    
    async def scrape_news_content(self, url: str) -> tuple:
        """爬取新闻原文和信源信息
        
        Returns:
            tuple: (content, publisher) - 内容和信息发布方
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 提取信息发布方
                publisher = self._extract_publisher(soup, url)
                
                # 尝试提取主要内容
                content = []
                
                # 常见内容标签
                content_tags = ['article', 'main', '.content', '.article-content', '.news-content']
                
                for tag in content_tags:
                    elements = soup.select(tag)
                    if elements:
                        for element in elements:
                            # 提取文本，去除空白
                            text = element.get_text(separator='\n', strip=True)
                            if text and len(text) > 100:
                                content.append(text)
                                break
                    if content:
                        break
                
                # 如果没有找到内容，使用整个页面文本
                if not content:
                    text = soup.get_text(separator='\n', strip=True)
                    # 过滤掉过长的文本，保留合理长度
                    if len(text) > 5000:
                        text = text[:5000]
                    content.append(text)
                
                full_content = '\n'.join(content)
                logger.info(f"从 {url} 爬取到 {len(full_content)} 字符, 信源: {publisher}")
                return full_content, publisher
                
        except Exception as e:
            logger.error(f"爬取 {url} 失败: {str(e)}")
            return f"爬取失败: {str(e)}", "未知来源"
    
    def _extract_publisher(self, soup: BeautifulSoup, url: str) -> str:
        """从网页中提取信息发布方"""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()
        publisher = None
        
        # 特殊处理：百度百家号 - 需要从页面内容提取原始来源
        if 'baijiahao.baidu.com' in domain:
            # 获取页面文本
            page_text = soup.get_text(separator=' ', strip=True)[:2000]
            import re
            
            # 1. 匹配 "来源：XXX" 或 "来源: XXX"
            source_match = re.search(r'来源[：:]\s*([^\s，。,；;]{2,20})', page_text)
            if source_match:
                return source_match.group(1).strip()
            
            # 2. 匹配 "XXX报讯"、"XXX网讯"、"XXX客户端讯"
            xun_match = re.search(r'([^\s，。,；;]{2,15})(报|网|客户端)讯', page_text)
            if xun_match:
                return xun_match.group(1) + xun_match.group(2)
            
            # 3. 百度百家号特殊格式：标题后跟着媒体名称+时间
            # 例如："...举行 新华社新媒体 2026-03-07 15:17"
            # 或："...牵挂 中国新闻网 2026-03-07 15:53"
            bjh_patterns = [
                r'\s+([\u4e00-\u9fa5]{2,10}(?:新媒体|官方账号))\s+\d{4}-\d{2}-\d{2}',
                r'\s+([\u4e00-\u9fa5]{2,8}网)\s+\d{4}-\d{2}-\d{2}',
                r'\s+([\u4e00-\u9fa5]{2,8}社)\s+\d{4}-\d{2}-\d{2}',
                r'\s+([\u4e00-\u9fa5]{2,10}报)\s+\d{4}-\d{2}-\d{2}',
            ]
            for pattern in bjh_patterns:
                match = re.search(pattern, page_text)
                if match:
                    return match.group(1).strip()
            
            # 4. 尝试从meta标签提取
            meta_selectors = [
                'meta[name="author"]',
                'meta[name="article:author"]',
            ]
            for selector in meta_selectors:
                tag = soup.select_one(selector)
                if tag and tag.get('content'):
                    content = tag.get('content').strip()
                    if 2 < len(content) < 50:
                        return content
        
        # 1. 尝试从 meta 标签提取
        if not publisher:
            meta_selectors = [
                'meta[name="author"]',
                'meta[name="publisher"]',
                'meta[property="article:publisher"]',
                'meta[name="og:site_name"]',
                'meta[property="og:site_name"]',
                'meta[name="twitter:site"]',
            ]
            for selector in meta_selectors:
                tag = soup.select_one(selector)
                if tag and tag.get('content'):
                    content = tag.get('content').strip()
                    # 过滤掉太长或太短的
                    if 2 < len(content) < 50:
                        publisher = content
                        break
        
        # 2. 尝试从常见的来源标签提取
        if not publisher:
            source_selectors = [
                '.source',
                '.article-source',
                '.news-source',
                '.post-source',
                '[class*="source"]',
                '.author',
                '.byline',
                '.publisher',
                '.media-name',
                '.media-source',
            ]
            for selector in source_selectors:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(strip=True)
                    if text and 2 < len(text) < 50:
                        publisher = text
                        break
        
        # 3. 从 URL 域名推断
        if not publisher:
            # 域名到媒体名称的映射
            domain_to_name = {
                'xinhuanet.com': '新华网',
                'news.cn': '新华网',
                'people.com.cn': '人民网',
                'cctv.com': '央视网',
                'chinadaily.com.cn': '中国日报',
                'china.com.cn': '中国网',
                'china.com': '中华网',
                'chinanews.com': '中国新闻网',
                'news.sina.com.cn': '新浪新闻',
                'news.qq.com': '腾讯新闻',
                '163.com': '网易新闻',
                'sohu.com': '搜狐新闻',
                'ifeng.com': '凤凰网',
                'thepaper.cn': '澎湃新闻',
                'caixin.com': '财新网',
                'jiemian.com': '界面新闻',
                '21jingji.com': '21世纪经济报道',
                'stcn.com': '证券时报',
                'cs.com.cn': '中证网',
                'eastmoney.com': '东方财富网',
                'hexun.com': '和讯网',
                'wallstreetcn.com': '华尔街见闻',
                'cls.cn': '财联社',
                'yicai.com': '第一财经',
                'cbnweek.com': '第一财经',
                'eeo.com.cn': '经济观察网',
                'nbd.com.cn': '每日经济新闻',
                'reuters.com': '路透社',
                'bbc.com': 'BBC',
                'apnews.com': '美联社',
                'theguardian.com': '卫报',
                'nytimes.com': '纽约时报',
            }
            
            for key, name in domain_to_name.items():
                if key in domain:
                    publisher = name
                    break
            
            # 如果没找到映射，使用域名
            if not publisher:
                publisher = domain.replace('www.', '')
        
        return publisher or "未知来源"
    
    async def generate_analysis(self, full_content: str, user_opinion: str = "") -> tuple:
        """使用小模型生成分析和相关度"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                prompt = f'你是一名逻辑分析师。请对以下文章进行分析，生成**文字版逻辑推理链条**，并评估该文章与用户观点的相关度（0-1之间的数值）。逻辑链条需包含核心结论、前提、支撑证据、推理步骤和结论/后续行动，并尽量清晰、条理化。 要求： 1. **核心主张 / 结论**：文章的主要观点或最终结论。 2. **前提 / 假设**：支持结论所依赖的隐含或显性前提。 3. **支撑证据**：文章中明确的事实、数据或引用。 4. **推理步骤**：按照逻辑顺序，将前提和证据推导至结论。 5. **结论 / 后续行动**：根据文章推理得出的结果或建议。 6. **相关度评估**：评估文章与用户观点的相关程度，给出0-1之间的数值，1表示完全相关，0表示完全不相关。 7. 可选：标注每个推理步骤的置信度或风险提示（高/中/低）。 用户观点："""{user_opinion}""" 文章内容： """{full_content}""" 请输出结构化的逻辑链条，格式如下： 1. 核心主张 / 结论： - 2. 前提 / 假设： - 3. 支撑证据： - 4. 推理步骤： 1. 2. 3. ... 5. 结论 / 后续行动： - 6. 相关度评估： - 结构性的分析结果。'
                
                # 使用 .env 中配置的 Qwen 模型
                import os
                model = os.getenv('SILICONFLOW_QWEN_MODEL', os.getenv('SILICONFLOW_SMALL_MODEL', 'Qwen/Qwen3.5-9B'))
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.1
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.silicon_flow_api_key}"
                }
                
                response = await client.post(self.silicon_flow_url, json=payload, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                analysis_text = data['choices'][0]['message']['content']
                logger.info("成功生成新闻分析")
                
                # 从分析文本中提取相关度分数
                relevance_score = 0.5  # 默认值
                import re
                relevance_match = re.search(r'相关度评估：\s*-\s*([0-9.]+)', analysis_text)
                if relevance_match:
                    try:
                        relevance_score = float(relevance_match.group(1))
                        relevance_score = max(0.0, min(1.0, relevance_score))  # 确保在0-1之间
                    except:
                        pass
                
                return analysis_text, relevance_score
                
        except Exception as e:
            logger.error(f"生成分析失败: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            return f"分析失败: {type(e).__name__}: {str(e)}", 0.3  # 返回元组
    
    async def analyze_news(self, news_items: List[NewsItem], user_opinion: str = "", top_n: int = 20, relevance_threshold: float = 0.3) -> List[NewsAnalysis]:
        """分析新闻"""
        # 提取最近的新闻
        recent_news = await self.extract_recent_news(news_items, top_n)
        
        # 分析每条新闻
        analyses = []
        tasks = []
        
        for news_item in recent_news:
            task = self._analyze_single_news(news_item, user_opinion)
            tasks.append(task)
        
        # 并行处理
        results = await asyncio.gather(*tasks)
        
        # 过滤相关度低于阈值的结果
        filtered_analyses = []
        for analysis in results:
            if analysis.relevance_score >= relevance_threshold:
                filtered_analyses.append(analysis)
            else:
                logger.info(f"跳过相关度低的新闻: {analysis.news_item.title} (相关度: {analysis.relevance_score})")
        
        logger.info(f"完成 {len(filtered_analyses)} 条新闻的分析 (过滤掉 {len(results) - len(filtered_analyses)} 条相关度低的新闻)")
        return filtered_analyses
    
    def save_to_json(self, analyses: List[NewsAnalysis], output_file: str = "news_analysis.json"):
        """保存分析结果到JSON文件"""
        import json
        
        # 转换为字典列表
        data = [analysis.to_dict() for analysis in analyses]
        
        # 保存到文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"分析结果已保存到 {output_file}")
        return output_file
    
    def calculate_relevance(self, content: str, user_opinion: str) -> float:
        """计算相关度"""
        if not user_opinion:
            return 0.5  # 默认相关度
        
        # 简单的关键词匹配算法
        content_lower = content.lower()
        opinion_lower = user_opinion.lower()
        
        # 提取关键词（使用更简单的方法，避免正则表达式的问题）
        content_words = set(content_lower.split())
        opinion_words = set(opinion_lower.split())
        
        # 计算交集
        common_words = content_words.intersection(opinion_words)
        
        # 计算相关度分数
        if not opinion_words:
            return 0.0
        
        relevance = len(common_words) / len(opinion_words)
        
        # 额外检查：如果内容包含用户观点中的任何关键词，提高相关度
        for word in opinion_words:
            if word in content_lower:
                relevance += 0.1
        
        return min(relevance, 1.0)
    
    def calculate_source_credibility(self, publisher: str, domain: str) -> float:
        """计算信源可信度权重
        
        Returns:
            float: 0-1之间的信源可信度分数
        """
        # 权威媒体映射（权重0.8-1.0）
        authoritative_media = {
            '新华网': 0.95, '人民网': 0.95, '央视网': 0.95, '中国新闻网': 0.95,
            '中国日报': 0.90, '中国网': 0.90, '中华网': 0.85,
            '新华社': 0.95, '人民日报': 0.95, '中央电视台': 0.95,
            '路透社': 0.90, 'BBC': 0.88, '美联社': 0.90, '卫报': 0.85,
            '纽约时报': 0.88, '华尔街日报': 0.88, '金融时报': 0.88,
        }
        
        # 主流商业媒体（权重0.6-0.8）
        mainstream_media = {
            '澎湃新闻': 0.80, '财新网': 0.82, '界面新闻': 0.78,
            '第一财经': 0.80, '21世纪经济报道': 0.78, '经济观察网': 0.76,
            '每日经济新闻': 0.76, '证券时报': 0.78, '财联社': 0.78,
            '华尔街见闻': 0.75, '新浪财经': 0.70, '腾讯新闻': 0.70,
            '网易新闻': 0.70, '搜狐新闻': 0.70, '凤凰新闻': 0.70,
            '新浪新闻': 0.70, '和讯网': 0.72, '东方财富网': 0.72,
            '中证网': 0.75,
        }
        
        # 检查publisher
        if publisher:
            for media, score in {**authoritative_media, **mainstream_media}.items():
                if media in publisher:
                    return score
        
        # 基于域名判断
        domain_mapping = {
            'xinhuanet.com': 0.95, 'news.cn': 0.95, 'people.com.cn': 0.95,
            'cctv.com': 0.95, 'chinanews.com': 0.95, 'chinadaily.com.cn': 0.90,
            'china.com.cn': 0.90, 'thepaper.cn': 0.80, 'caixin.com': 0.82,
            'jiemian.com': 0.78, 'yicai.com': 0.80, '21jingji.com': 0.78,
            'eeo.com.cn': 0.76, 'nbd.com.cn': 0.76, 'stcn.com': 0.78,
            'cls.cn': 0.78, 'wallstreetcn.com': 0.75, 'reuters.com': 0.90,
            'bbc.com': 0.88, 'apnews.com': 0.90, 'theguardian.com': 0.85,
            'nytimes.com': 0.88,
        }
        
        for key, score in domain_mapping.items():
            if key in domain:
                return score
        
        # 政府网站
        if 'gov.cn' in domain:
            return 0.90
        
        # 默认中等可信度
        return 0.50
    
    async def calculate_model_credibility(self, full_content: str) -> float:
        """使用小模型评估内容可信度
        
        Returns:
            float: 0-1之间的模型可信度评分
        """
        try:
            # 限制内容长度，避免超时
            content_for_analysis = full_content[:2000] if len(full_content) > 2000 else full_content
            
            prompt = f'''你是一名新闻可信度评估专家。请对以下新闻内容进行可信度评估，给出0-1之间的数值评分。

评估维度：
1. 内容完整性：是否有明确的时间、地点、人物、事件
2. 信息来源：是否标注信息来源，来源是否可靠
3. 客观性：是否存在明显的偏见或主观臆断
4. 专业性：用词是否专业，逻辑是否清晰
5. 时效性：信息是否及时

新闻内容：
"""{content_for_analysis}"""

请只输出一个0-1之间的数字，表示可信度评分。例如：0.85
不要输出任何解释文字。'''
            
            import os
            model = os.getenv('SILICONFLOW_QWEN_MODEL', os.getenv('SILICONFLOW_SMALL_MODEL', 'Qwen/Qwen3.5-9B'))
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50,
                "temperature": 0.1
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.silicon_flow_api_key}"
            }
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.silicon_flow_url, json=payload, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                result_text = data['choices'][0]['message']['content'].strip()
                
                # 提取数字
                import re
                number_match = re.search(r'0?\.\d+|1\.0|1|0', result_text)
                if number_match:
                    score = float(number_match.group())
                    return max(0.0, min(1.0, score))
                
                return 0.5  # 默认中等可信度
                
        except Exception as e:
            logger.warning(f"模型可信度评估失败: {str(e)}")
            return 0.5  # 失败时返回默认值
    
    def calculate_credibility(self, publisher: str, domain: str, content: str, 
                            publish_time: datetime, model_score: float = None) -> float:
        """计算综合可信度
        
        综合信源权重(40%) + 小模型评分(40%) + 内容质量(20%)
        
        Args:
            publisher: 信息发布方名称
            domain: 域名
            content: 新闻内容
            publish_time: 发布时间
            model_score: 小模型评分(可选)
        
        Returns:
            float: 0-1之间的综合可信度分数
        """
        # 1. 信源可信度 (权重40%)
        source_score = self.calculate_source_credibility(publisher, domain)
        
        # 2. 小模型评分 (权重40%)
        if model_score is None:
            model_score = 0.5  # 默认中等
        
        # 3. 内容质量评分 (权重20%)
        content_score = 0.0
        
        # 基于内容长度
        content_len = len(content)
        if content_len > 1000:
            content_score += 0.10
        elif content_len > 500:
            content_score += 0.07
        elif content_len > 200:
            content_score += 0.04
        
        # 基于发布时间
        if publish_time:
            days_since = (datetime.now() - publish_time).days
            if days_since <= 3:
                content_score += 0.10
            elif days_since <= 7:
                content_score += 0.07
            elif days_since <= 30:
                content_score += 0.04
        else:
            content_score += 0.05  # 无发布时间扣一点分
        
        # 综合计算
        final_score = (source_score * 0.40) + (model_score * 0.40) + (content_score * 0.20)
        
        return round(min(final_score, 1.0), 2)
    
    async def _analyze_single_news(self, news_item: NewsItem, user_opinion: str) -> NewsAnalysis:
        """分析单条新闻"""
        # 爬取原文和信源
        full_content, publisher = await self.scrape_news_content(news_item.url)
        
        # 更新news_item的信源为提取到的具体发布方
        if publisher and publisher != "未知来源":
            news_item.source = publisher
        
        # 生成分析和相关度（带重试机制）
        analysis, relevance_score = await self._generate_analysis_with_retry(full_content, user_opinion)
        
        # 使用小模型评估可信度
        model_credibility = await self.calculate_model_credibility(full_content)
        
        # 计算综合可信度
        credibility_score = self.calculate_credibility(
            publisher=publisher,
            domain=news_item.source_domain,
            content=full_content,
            publish_time=news_item.publish_time,
            model_score=model_credibility
        )
        
        return NewsAnalysis(
            news_item=news_item,
            full_content=full_content,
            analysis=analysis,
            relevance_score=relevance_score,
            credibility_score=credibility_score
        )
    
    async def _generate_analysis_with_retry(self, full_content: str, user_opinion: str, 
                                           max_retries: int = 3) -> tuple:
        """带重试机制的分析生成
        
        Args:
            full_content: 新闻全文
            user_opinion: 用户观点
            max_retries: 最大重试次数
            
        Returns:
            tuple: (analysis_text, relevance_score)
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # 增加超时时间
                timeout = 60.0 + (attempt * 30)  # 第一次60s，第二次90s，第三次120s
                
                result = await self._call_analysis_api(full_content, user_opinion, timeout)
                
                if result and result[0] and not result[0].startswith("分析失败"):
                    return result
                
                # 如果返回的是失败信息，继续重试
                last_error = result[0] if result else "未知错误"
                logger.warning(f"第 {attempt + 1} 次尝试失败: {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.warning(f"第 {attempt + 1} 次尝试异常: {last_error}")
            
            # 等待后重试
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
        
        # 所有重试都失败，返回默认结果
        logger.error(f"分析生成失败，已重试 {max_retries} 次")
        return f"分析失败: 多次尝试后仍超时或出错 ({last_error})", 0.3
    
    async def _call_analysis_api(self, full_content: str, user_opinion: str, 
                                  timeout: float) -> tuple:
        """调用API生成分析
        
        Args:
            full_content: 新闻全文（会被截断以控制长度）
            user_opinion: 用户观点
            timeout: 超时时间
            
        Returns:
            tuple: (analysis_text, relevance_score)
        """
        # 限制内容长度，避免超时
        max_content_len = 3000
        if len(full_content) > max_content_len:
            content_for_analysis = full_content[:max_content_len] + "..."
        else:
            content_for_analysis = full_content
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            prompt = f'''你是一名逻辑分析师。请对以下文章进行分析，生成**文字版逻辑推理链条**，并评估该文章与用户观点的相关度（0-1之间的数值）。

逻辑链条需包含核心结论、前提、支撑证据、推理步骤和结论/后续行动，并尽量清晰、条理化。

要求：
1. **核心主张 / 结论**：文章的主要观点或最终结论。
2. **前提 / 假设**：支持结论所依赖的隐含或显性前提。
3. **支撑证据**：文章中明确的事实、数据或引用。
4. **推理步骤**：按照逻辑顺序，将前提和证据推导至结论。
5. **结论 / 后续行动**：根据文章推理得出的结果或建议。
6. **相关度评估**：评估文章与用户观点的相关程度，给出0-1之间的数值，1表示完全相关，0表示完全不相关。
7. 可选：标注每个推理步骤的置信度或风险提示（高/中/低）。

用户观点："""{user_opinion}"""

文章内容：
"""{content_for_analysis}"""

请输出结构化的逻辑链条，格式如下：
1. 核心主张 / 结论：
   -
2. 前提 / 假设：
   -
3. 支撑证据：
   -
4. 推理步骤：
   1.
   2.
   3.
   ...
5. 结论 / 后续行动：
   -
6. 相关度评估：
   - 0.x'''
            
            import os
            model = os.getenv('SILICONFLOW_QWEN_MODEL', os.getenv('SILICONFLOW_SMALL_MODEL', 'Qwen/Qwen3.5-9B'))
            
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1500,
                "temperature": 0.1,
                "stream": False
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.silicon_flow_api_key}"
            }
            
            response = await client.post(self.silicon_flow_url, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            analysis_text = data['choices'][0]['message']['content']
            logger.info("成功生成新闻分析")
            
            # 从分析文本中提取相关度分数
            relevance_score = 0.5  # 默认值
            relevance_match = re.search(r'相关度评估[：:]\s*[-–—]?\s*([0-9.]+)', analysis_text)
            if relevance_match:
                try:
                    relevance_score = float(relevance_match.group(1))
                    relevance_score = max(0.0, min(1.0, relevance_score))
                except:
                    pass
            
            return analysis_text, relevance_score
