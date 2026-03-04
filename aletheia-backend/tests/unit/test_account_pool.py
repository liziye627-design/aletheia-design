from services.account_pool import AccountPool, parse_cookie_pool


def test_parse_cookie_pool_supports_json_and_delimiters() -> None:
    assert parse_cookie_pool('["a","b","a"]') == ["a", "b"]
    assert parse_cookie_pool("a\nb\nb") == ["a", "b"]
    assert parse_cookie_pool("a||b||a") == ["a", "b"]
    assert parse_cookie_pool("") == []


def test_account_pool_rotation_and_cooldown() -> None:
    pool = AccountPool(
        platform="weibo",
        cookies=["cookie_a", "cookie_b"],
        max_failures=1,
        cooldown_sec=120,
    )

    first = pool.acquire_cookie()
    second = pool.acquire_cookie()
    assert {first, second} == {"cookie_a", "cookie_b"}

    pool.mark_failure(first, reason="status_403")
    snap = pool.snapshot()
    assert snap["total_accounts"] == 2
    assert snap["cooldown_accounts"] == 1
    assert snap["available_accounts"] == 1

    # 冷却中的账号不会被立即再次分配
    picks = {pool.acquire_cookie() for _ in range(3)}
    assert picks == {second}

    pool.mark_success(second)
    snap2 = pool.snapshot()
    assert snap2["available_accounts"] == 1
