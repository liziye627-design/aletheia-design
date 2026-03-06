"""
Content Extraction Module.
正文抽取模块 - 实现优先级抽取链

Extraction priority chain:
1. Site template rules (CSS/XPath) - highest confidence
2. JSON-LD structured data (Schema.org)
3. Open Graph protocol metadata
4. Trafilatura/Readability fallback

Author: Aletheia Team
"""

import re
import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from bs4 import BeautifulSoup
import structlog

logger = structlog.get_logger()


class ExtractionMethod(str, Enum):
    """Content extraction methods"""
    TEMPLATE_RULES = "template_rules"
    JSONLD = "jsonld"
    OPENGRAPH = "opengraph"
    TRAFILATURA = "trafilatura"
    READABILITY = "readability"
    FALLBACK = "fallback"


@dataclass
class ExtractionResult:
    """Result of content extraction"""
    title: Optional[str] = None
    content_text: Optional[str] = None
    content_html: Optional[str] = None
    publish_time: Optional[datetime] = None
    author: Optional[str] = None
    canonical_url: Optional[str] = None
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    extraction_method: ExtractionMethod = ExtractionMethod.FALLBACK
    extraction_confidence: float = 0.0

    # Raw extracted data
    jsonld_data: Optional[Dict[str, Any]] = None
    og_data: Optional[Dict[str, str]] = None
    meta_data: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "title": self.title,
            "content_text": self.content_text,
            "content_html": self.content_html,
            "publish_time": self.publish_time.isoformat() if self.publish_time else None,
            "author": self.author,
            "canonical_url": self.canonical_url,
            "images": self.images,
            "videos": self.videos,
            "tags": self.tags,
            "extraction_method": self.extraction_method.value,
            "extraction_confidence": self.extraction_confidence,
        }


class SiteTemplate:
    """
    Site-specific extraction template.
    站点级抽取模板
    """

    def __init__(
        self,
        site_id: str,
        domain_pattern: str,
        title_selector: Optional[str] = None,
        content_selector: Optional[str] = None,
        author_selector: Optional[str] = None,
        time_selector: Optional[str] = None,
        time_format: Optional[str] = None,
        image_selector: Optional[str] = None,
        video_selector: Optional[str] = None,
        tag_selector: Optional[str] = None,
        remove_selectors: Optional[List[str]] = None,
    ):
        self.site_id = site_id
        self.domain_pattern = domain_pattern
        self.title_selector = title_selector
        self.content_selector = content_selector
        self.author_selector = author_selector
        self.time_selector = time_selector
        self.time_format = time_format
        self.image_selector = image_selector
        self.video_selector = video_selector
        self.tag_selector = tag_selector
        self.remove_selectors = remove_selectors or []

    def matches(self, url: str) -> bool:
        """Check if URL matches this template"""
        return bool(re.search(self.domain_pattern, url, re.IGNORECASE))

    def extract(self, html: str, url: str) -> ExtractionResult:
        """Extract content using template rules"""
        soup = BeautifulSoup(html, "html.parser")
        result = ExtractionResult()
        result.extraction_method = ExtractionMethod.TEMPLATE_RULES
        result.extraction_confidence = 0.95

        # Remove unwanted elements
        for selector in self.remove_selectors:
            for elem in soup.select(selector):
                elem.decompose()

        # Extract title
        if self.title_selector:
            elem = soup.select_one(self.title_selector)
            if elem:
                result.title = elem.get_text(strip=True)

        # Extract content
        if self.content_selector:
            elem = soup.select_one(self.content_selector)
            if elem:
                result.content_html = str(elem)
                result.content_text = elem.get_text(strip=True, separator=" ")

        # Extract author
        if self.author_selector:
            elem = soup.select_one(self.author_selector)
            if elem:
                result.author = elem.get_text(strip=True)

        # Extract time
        if self.time_selector:
            elem = soup.select_one(self.time_selector)
            if elem:
                time_text = elem.get_text(strip=True)
                result.publish_time = self._parse_time(time_text)

        # Extract images
        if self.image_selector:
            for elem in soup.select(self.image_selector):
                src = elem.get("src") or elem.get("data-src")
                if src:
                    result.images.append(src)

        # Extract videos
        if self.video_selector:
            for elem in soup.select(self.video_selector):
                src = elem.get("src") or elem.get("data-src")
                if src:
                    result.videos.append(src)

        # Extract tags
        if self.tag_selector:
            for elem in soup.select(self.tag_selector):
                tag = elem.get_text(strip=True)
                if tag:
                    result.tags.append(tag)

        return result

    def _parse_time(self, time_text: str) -> Optional[datetime]:
        """Parse time string to datetime"""
        if not time_text:
            return None

        # Common Chinese time formats
        formats = [
            "%Y年%m月%d日 %H:%M",
            "%Y年%m月%d日",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_text, fmt)
            except ValueError:
                continue

        return None


# Predefined site templates
SITE_TEMPLATES = [
    # 人民网
    SiteTemplate(
        site_id="people",
        domain_pattern=r"people\.com\.cn",
        title_selector="h1, .title",
        content_selector=".rm_txt_con, #rwb_zw",
        author_selector=".editor, .author",
        time_selector=".box01_date, .date",
        image_selector=".rm_txt_con img",
        remove_selectors=[".ad", ".advertisement", ".related"],
    ),
    # 新华网
    SiteTemplate(
        site_id="xinhua",
        domain_pattern=r"(news\.cn|xinhuanet\.com)",
        title_selector="h1, .title",
        content_selector="#p-detail, .article-content",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector="#p-detail img, .article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 央视网
    SiteTemplate(
        site_id="cctv",
        domain_pattern=r"cctv\.com",
        title_selector="h1, .title",
        content_selector=".content_area, .article-content",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".content_area img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 微博
    SiteTemplate(
        site_id="weibo",
        domain_pattern=r"weibo\.com",
        title_selector=".text",
        content_selector=".text",
        author_selector=".name",
        time_selector=".from a",
        image_selector=".media-piclist img",
        remove_selectors=[".ad"],
    ),
    # 知乎
    SiteTemplate(
        site_id="zhihu",
        domain_pattern=r"zhihu\.com",
        title_selector="h1.Title, .QuestionHeader-title",
        content_selector=".RichContent-inner, .RichText",
        author_selector=".AuthorInfo-name",
        time_selector=".ContentItem-time",
        image_selector=".RichContent-inner img",
        remove_selectors=[".ad", ".Pc-Business-Card"],
    ),
    # B站
    SiteTemplate(
        site_id="bilibili",
        domain_pattern=r"bilibili\.com",
        title_selector="h1.video-title, .title",
        content_selector=".basic-desc-info, .desc-info-text",
        author_selector=".up-name, .username",
        time_selector=".pubdate-text, .pudate-text",
        image_selector=".bili-cover img",
        remove_selectors=[".ad", ".banner"],
    ),
    # 澎湃新闻
    SiteTemplate(
        site_id="thepaper",
        domain_pattern=r"thepaper\.cn",
        title_selector="h1, .news_title",
        content_selector=".news_txt, .content",
        author_selector=".author, .news_author",
        time_selector=".time, .date",
        image_selector=".news_txt img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 财新网
    SiteTemplate(
        site_id="caixin",
        domain_pattern=r"caixin\.com",
        title_selector="h1, .title",
        content_selector=".article-content, #the_content",
        author_selector=".author, .info",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 界面新闻
    SiteTemplate(
        site_id="jiemian",
        domain_pattern=r"jiemian\.com",
        title_selector="h1, .article-title",
        content_selector=".article-content, .content",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 今日头条
    SiteTemplate(
        site_id="toutiao",
        domain_pattern=r"(toutiao\.com|www\.toutiao\.com)",
        title_selector="h1, .article-title",
        content_selector=".article-content, .main",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 抖音
    SiteTemplate(
        site_id="douyin",
        domain_pattern=r"douyin\.com",
        title_selector="h1, .title",
        content_selector=".desc, .description",
        author_selector=".author, .nickname",
        time_selector=".time, .date",
        image_selector=".poster img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 小红书
    SiteTemplate(
        site_id="xiaohongshu",
        domain_pattern=r"xiaohongshu\.com",
        title_selector="h1, .title",
        content_selector=".content, .desc",
        author_selector=".author, .nickname",
        time_selector=".time, .date",
        image_selector=".swiper-slide img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 中国政府网
    SiteTemplate(
        site_id="gov",
        domain_pattern=r"gov\.cn",
        title_selector="h1, .title",
        content_selector=".pages_content, #content",
        author_selector=".source, .author",
        time_selector=".time, .date",
        image_selector=".pages_content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 新浪新闻
    SiteTemplate(
        site_id="sina",
        domain_pattern=r"(sina\.com\.cn|news\.sina\.com\.cn)",
        title_selector="h1, .main-title",
        content_selector=".article-content, #artibody",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 网易新闻
    SiteTemplate(
        site_id="netease",
        domain_pattern=r"(163\.com|news\.163\.com)",
        title_selector="h1, .title",
        content_selector=".post-content, #content",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".post-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 搜狐新闻
    SiteTemplate(
        site_id="sohu",
        domain_pattern=r"sohu\.com",
        title_selector="h1, .text-title",
        content_selector=".article-content, #mp-editor",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
    # 凤凰网
    SiteTemplate(
        site_id="ifeng",
        domain_pattern=r"ifeng\.com",
        title_selector="h1, .title",
        content_selector=".article-content, #main_content",
        author_selector=".author, .source",
        time_selector=".time, .date",
        image_selector=".article-content img",
        remove_selectors=[".ad", ".advertisement"],
    ),
]


class JSONLDExtractor:
    """
    JSON-LD structured data extractor.
    JSON-LD 结构化数据提取器
    """

    SUPPORTED_TYPES = [
        "NewsArticle",
        "Article",
        "BlogPosting",
        "WebPage",
        "ScholarlyArticle",
    ]

    def extract(self, html: str) -> Tuple[Optional[Dict[str, Any]], float]:
        """
        Extract JSON-LD data from HTML.
        从 HTML 提取 JSON-LD 数据

        Returns:
            Tuple of (extracted_data, confidence)
        """
        soup = BeautifulSoup(html, "html.parser")

        # Find all JSON-LD script tags
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            try:
                data = json.loads(script.string)

                # Handle @graph format
                if "@graph" in data:
                    for item in data["@graph"]:
                        if self._is_article_type(item):
                            return self._extract_fields(item), 0.80

                # Handle single item
                if self._is_article_type(data):
                    return self._extract_fields(data), 0.80

            except (json.JSONDecodeError, TypeError):
                continue

        return None, 0.0

    def _is_article_type(self, data: Dict) -> bool:
        """Check if data is an article type"""
        type_ = data.get("@type", "")
        if isinstance(type_, list):
            return any(t in self.SUPPORTED_TYPES for t in type_)
        return type_ in self.SUPPORTED_TYPES

    def _extract_fields(self, data: Dict) -> Dict[str, Any]:
        """Extract relevant fields from JSON-LD"""
        result = {}

        # Title
        if "headline" in data:
            result["title"] = data["headline"]

        # Content
        if "articleBody" in data:
            result["content_text"] = data["articleBody"]

        # Author
        author = data.get("author", {})
        if isinstance(author, dict):
            result["author"] = author.get("name", "")
        elif isinstance(author, str):
            result["author"] = author

        # Publish time
        if "datePublished" in data:
            try:
                result["publish_time"] = datetime.fromisoformat(
                    data["datePublished"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Modified time
        if "dateModified" in data:
            try:
                result["modified_time"] = datetime.fromisoformat(
                    data["dateModified"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Images
        images = data.get("image", [])
        if isinstance(images, str):
            images = [images]
        if isinstance(images, dict):
            images = [images.get("url", "")]
        result["images"] = [img for img in images if img]

        return result


class OpenGraphExtractor:
    """
    Open Graph protocol metadata extractor.
    Open Graph 协议元数据提取器
    """

    OG_PROPERTIES = [
        "og:title",
        "og:url",
        "og:image",
        "og:description",
        "og:site_name",
        "og:type",
        "article:published_time",
        "article:modified_time",
        "article:author",
        "article:tag",
    ]

    def extract(self, html: str) -> Tuple[Dict[str, str], float]:
        """
        Extract Open Graph data from HTML.
        从 HTML 提取 Open Graph 数据

        Returns:
            Tuple of (og_data, confidence)
        """
        soup = BeautifulSoup(html, "html.parser")
        og_data = {}

        for prop in self.OG_PROPERTIES:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                og_data[prop] = meta.get("content")

        # Calculate confidence based on how many key properties were found
        key_props = ["og:title", "og:url", "og:description"]
        found_keys = sum(1 for p in key_props if p in og_data)
        confidence = found_keys / len(key_props) * 0.75

        return og_data, confidence


class MetaExtractor:
    """
    HTML meta tag extractor.
    HTML meta 标签提取器
    """

    def extract(self, html: str) -> Dict[str, str]:
        """Extract metadata from HTML meta tags"""
        soup = BeautifulSoup(html, "html.parser")
        meta_data = {}

        # Standard meta tags
        meta_mappings = {
            "title": ["title", "twitter:title"],
            "description": ["description", "twitter:description"],
            "author": ["author", "article:author"],
            "keywords": ["keywords"],
            "publish_time": ["article:published_time", "datePublished", "publishdate"],
            "canonical_url": ["canonical"],
        }

        for field, names in meta_mappings.items():
            for name in names:
                # Try meta tag
                meta = soup.find("meta", attrs={"name": name})
                if not meta:
                    meta = soup.find("meta", attrs={"property": name})
                if meta and meta.get("content"):
                    meta_data[field] = meta.get("content")
                    break

        # Canonical link
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            meta_data["canonical_url"] = canonical.get("href")

        # Title from <title> tag
        if "title" not in meta_data:
            title_tag = soup.find("title")
            if title_tag:
                meta_data["title"] = title_tag.get_text(strip=True)

        return meta_data


class GenericExtractor:
    """
    Generic content extractor using readability algorithms.
    通用正文抽取器 - 使用 readability 算法兜底
    """

    def extract(self, html: str, url: str) -> ExtractionResult:
        """
        Extract content using generic methods.
        使用通用方法提取内容
        """
        result = ExtractionResult()

        # Try trafilatura first
        try:
            import trafilatura
            content = trafilatura.extract(html, include_comments=False)
            if content:
                result.content_text = content
                result.extraction_method = ExtractionMethod.TRAFILATURA
                result.extraction_confidence = 0.65
        except ImportError:
            pass

        # Fallback to BeautifulSoup extraction
        if not result.content_text:
            result = self._bs4_fallback(html, url)

        return result

    def _bs4_fallback(self, html: str, url: str) -> ExtractionResult:
        """BeautifulSoup fallback extraction"""
        result = ExtractionResult()
        result.extraction_method = ExtractionMethod.FALLBACK
        result.extraction_confidence = 0.50

        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, footer, header
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content area
        main_selectors = [
            "main", "article", ".content", ".article", ".post",
            "#content", "#article", "#main", ".main-content",
        ]

        for selector in main_selectors:
            main = soup.select_one(selector)
            if main:
                result.content_html = str(main)
                result.content_text = main.get_text(strip=True, separator=" ")
                break

        # If no main content found, use body
        if not result.content_text:
            body = soup.find("body")
            if body:
                result.content_text = body.get_text(strip=True, separator=" ")

        # Extract title
        title = soup.find("title")
        if title:
            result.title = title.get_text(strip=True)

        # Extract meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result.content_text = result.content_text or meta_desc.get("content", "")

        return result


class ContentExtractor:
    """
    Main content extractor with priority chain.
    主内容提取器 - 实现优先级抽取链
    """

    def __init__(self, templates: Optional[List[SiteTemplate]] = None):
        self.templates = templates or SITE_TEMPLATES
        self.jsonld_extractor = JSONLDExtractor()
        self.og_extractor = OpenGraphExtractor()
        self.meta_extractor = MetaExtractor()
        self.generic_extractor = GenericExtractor()

    def extract(self, html: str, url: str) -> ExtractionResult:
        """
        Extract content using priority chain.
        使用优先级链提取内容

        Priority:
        1. Site template rules (confidence ~0.95)
        2. JSON-LD structured data (confidence ~0.80)
        3. Open Graph metadata (confidence ~0.70)
        4. Generic extraction fallback (confidence ~0.50-0.65)
        """
        result = ExtractionResult()

        # 1. Try site template rules
        template = self._find_template(url)
        if template:
            result = template.extract(html, url)
            if result.content_text:
                # Template extraction successful
                self._merge_meta(result, html)
                return result

        # 2. Try JSON-LD
        jsonld_data, jsonld_conf = self.jsonld_extractor.extract(html)
        if jsonld_data and jsonld_conf > 0:
            result = self._build_from_jsonld(jsonld_data)
            result.jsonld_data = jsonld_data
            result.extraction_method = ExtractionMethod.JSONLD
            result.extraction_confidence = jsonld_conf

        # 3. Extract Open Graph
        og_data, og_conf = self.og_extractor.extract(html)
        if og_data:
            result.og_data = og_data
            if not result.title and "og:title" in og_data:
                result.title = og_data["og:title"]
            if not result.canonical_url and "og:url" in og_data:
                result.canonical_url = og_data["og:url"]
            if not result.images and "og:image" in og_data:
                result.images = [og_data["og:image"]]
            if "og:description" in og_data and not result.content_text:
                result.content_text = og_data["og:description"]

        # 4. Extract meta tags
        meta_data = self.meta_extractor.extract(html)
        if meta_data:
            result.meta_data = meta_data
            if not result.title and "title" in meta_data:
                result.title = meta_data["title"]
            if not result.author and "author" in meta_data:
                result.author = meta_data["author"]
            if not result.canonical_url and "canonical_url" in meta_data:
                result.canonical_url = meta_data["canonical_url"]

        # 5. Generic fallback if no content
        if not result.content_text:
            generic_result = self.generic_extractor.extract(html, url)
            if generic_result.content_text:
                if not result.title:
                    result.title = generic_result.title
                result.content_text = generic_result.content_text
                result.content_html = generic_result.content_html
                result.extraction_method = generic_result.extraction_method
                result.extraction_confidence = generic_result.extraction_confidence

        return result

    def _find_template(self, url: str) -> Optional[SiteTemplate]:
        """Find matching template for URL"""
        for template in self.templates:
            if template.matches(url):
                return template
        return None

    def _merge_meta(self, result: ExtractionResult, html: str):
        """Merge metadata into extraction result"""
        meta_data = self.meta_extractor.extract(html)
        if meta_data:
            result.meta_data = meta_data
            if not result.canonical_url and "canonical_url" in meta_data:
                result.canonical_url = meta_data["canonical_url"]

    def _build_from_jsonld(self, data: Dict) -> ExtractionResult:
        """Build extraction result from JSON-LD data"""
        result = ExtractionResult()
        result.title = data.get("title")
        result.content_text = data.get("content_text")
        result.author = data.get("author")
        result.publish_time = data.get("publish_time")
        result.images = data.get("images", [])
        return result


# Convenience function
def extract_content(html: str, url: str) -> ExtractionResult:
    """Extract content from HTML using priority chain"""
    extractor = ContentExtractor()
    return extractor.extract(html, url)