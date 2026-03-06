from services.layer1_perception.crawlers.douyin import DouyinCrawler
from services.layer1_perception.crawlers.xiaohongshu import XiaohongshuCrawler
from services.layer1_perception.crawlers.zhihu import ZhihuCrawler


def test_xiaohongshu_public_search_parser():
    crawler = XiaohongshuCrawler()
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.xiaohongshu.com%2Fexplore%2F6798879b000000001f0175a2">测试笔记</a>
      <a class="result__snippet">苏炳添退役相关讨论</a>
    </div>
    """
    out = crawler._parse_public_site_results(html, keyword="苏炳添 退役", limit=5)
    assert len(out) == 1
    meta = out[0].get("metadata") or {}
    assert meta.get("retrieval_mode") == "xiaohongshu_public_search"
    assert meta.get("note_id") == "6798879b000000001f0175a2"


def test_douyin_public_search_parser():
    crawler = DouyinCrawler()
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.douyin.com%2Fvideo%2F7483611600293074202">测试视频</a>
      <a class="result__snippet">抖音公开视频索引内容</a>
    </div>
    """
    out = crawler._parse_public_site_results(html, keyword="苏炳添 退役", limit=5)
    assert len(out) == 1
    meta = out[0].get("metadata") or {}
    assert meta.get("retrieval_mode") == "douyin_public_search"
    assert meta.get("aweme_id") == "7483611600293074202"


def test_zhihu_public_search_parser():
    crawler = ZhihuCrawler()
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.zhihu.com%2Fquestion%2F655513560%2Fanswer%2F3500185801">知乎问答</a>
      <a class="result__snippet">知乎公开问答检索结果</a>
    </div>
    """
    out = crawler._parse_public_site_results(html, keyword="苏炳添 退役", limit=5)
    assert len(out) == 1
    meta = out[0].get("metadata") or {}
    assert meta.get("retrieval_mode") == "zhihu_public_search"
    assert meta.get("zhihu_id") == "655513560"


def test_chinese_keyword_match_score_not_zero():
    keyword = "苏炳添退役了"
    text = "苏炳添宣布退役，如何评价他的职业生涯？"
    assert XiaohongshuCrawler()._keyword_match_score(keyword, text) >= 0.5
    assert DouyinCrawler()._keyword_match_score(keyword, text) >= 0.5
    assert ZhihuCrawler()._keyword_match_score(keyword, text) >= 0.5


def test_xiaohongshu_public_search_filters_non_content_url():
    crawler = XiaohongshuCrawler()
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fjob.xiaohongshu.com%2Fsocial%2Fposition%2F14527">招聘页</a>
      <a class="result__snippet">苏炳添退役相关讨论</a>
    </div>
    """
    out = crawler._parse_public_site_results(html, keyword="苏炳添退役", limit=5)
    assert out == []
