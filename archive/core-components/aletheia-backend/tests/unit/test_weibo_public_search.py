from services.layer1_perception.crawlers.weibo import WeiboCrawler


def test_parse_public_search_results_extracts_weibo_links_and_metadata():
    crawler = WeiboCrawler()
    html = """
    <html>
      <body>
        <div class="result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.weibo.com%2F2018499075%2FQhzEofzSa">再见苏神!</a>
          <a class="result__snippet">36岁苏炳添宣布退役，结束21年职业生涯</a>
        </div>
        <div class="result">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ffoo">无关站点</a>
          <a class="result__snippet">this should be ignored</a>
        </div>
      </body>
    </html>
    """

    out = crawler._parse_public_search_results(
        html=html,
        keyword="苏炳添 退役",
        limit=10,
    )
    assert len(out) == 1
    row = out[0]
    assert row["original_url"].startswith("https://www.weibo.com/2018499075/")
    meta = row.get("metadata") or {}
    assert meta.get("retrieval_mode") == "weibo_public_search"
    assert meta.get("provider") == "native_public_search"
    assert meta.get("keyword_match") is True
    assert meta.get("post_id") == "QhzEofzSa"


def test_decode_public_search_url_unwraps_duckduckgo_redirect():
    crawler = WeiboCrawler()
    decoded = crawler._decode_public_search_url(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fweibo.com%2Fttarticle%2Fp%2Fshow%3Fid%3D2309405244854509895915"
    )
    assert decoded == "https://weibo.com/ttarticle/p/show?id=2309405244854509895915"

