from types import SimpleNamespace

import pytest

from services.llm.siliconflow_client import SiliconFlowClient


class _FakeCompletions:
    def __init__(self, fail_on: set[str] | None = None):
        self.fail_on = fail_on or set()
        self.calls: list[str] = []

    async def create(self, **kwargs):
        model = str(kwargs.get("model") or "")
        self.calls.append(model)
        if model in self.fail_on:
            raise RuntimeError(f"forced-failure:{model}")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )


def _fake_client(completions: _FakeCompletions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


@pytest.mark.asyncio
async def test_chat_with_fallback_uses_preferred_model_first():
    client = SiliconFlowClient()
    completions = _FakeCompletions()
    client.client = _fake_client(completions)

    await client._chat_with_fallback(
        preferred_model="preferred",
        fallback_models=["fallback"],
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=8,
        route="processing",
    )

    assert completions.calls == ["preferred"]


@pytest.mark.asyncio
async def test_chat_with_fallback_tries_next_model_on_failure():
    client = SiliconFlowClient()
    completions = _FakeCompletions(fail_on={"bad-model"})
    client.client = _fake_client(completions)

    resp = await client._chat_with_fallback(
        preferred_model="bad-model",
        fallback_models=["good-model"],
        messages=[{"role": "user", "content": "hi"}],
        temperature=0,
        max_tokens=8,
        route="summary",
    )

    assert resp.choices[0].message.content == "ok"
    assert completions.calls == ["bad-model", "good-model"]
