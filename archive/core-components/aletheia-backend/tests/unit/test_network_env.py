from utils import network_env


def test_evaluate_trust_env_disabled_by_default():
    trust_env, broken = network_env.evaluate_trust_env(default=False)
    assert trust_env is False
    assert broken == []


def test_evaluate_trust_env_keeps_enabled_when_auto_disable_off():
    trust_env, broken = network_env.evaluate_trust_env(
        default=True,
        auto_disable_local_proxy=False,
        env={"HTTP_PROXY": "http://127.0.0.1:7897"},
    )
    assert trust_env is True
    assert broken == []


def test_evaluate_trust_env_disables_when_local_proxy_unreachable(monkeypatch):
    monkeypatch.setattr(network_env, "_probe_local_proxy", lambda *_args, **_kwargs: False)
    trust_env, broken = network_env.evaluate_trust_env(
        default=True,
        auto_disable_local_proxy=True,
        env={"HTTP_PROXY": "http://127.0.0.1:7897"},
    )
    assert trust_env is False
    assert broken == ["127.0.0.1:7897"]


def test_evaluate_trust_env_ignores_non_local_proxy(monkeypatch):
    monkeypatch.setattr(network_env, "_probe_local_proxy", lambda *_args, **_kwargs: False)
    trust_env, broken = network_env.evaluate_trust_env(
        default=True,
        auto_disable_local_proxy=True,
        env={"HTTP_PROXY": "http://proxy.example.com:3128"},
    )
    assert trust_env is True
    assert broken == []


def test_ensure_local_no_proxy_appends_local_hosts():
    env = {"HTTP_PROXY": "http://10.0.0.1:8080", "NO_PROXY": "example.com"}
    appended = network_env.ensure_local_no_proxy(env=env)
    assert "localhost" in appended
    assert "127.0.0.1" in appended
    merged = env.get("NO_PROXY", "")
    assert "localhost" in merged
    assert "127.0.0.1" in merged
