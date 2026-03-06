from services.report_template_service import ReportTemplateService
from core.config import settings


def test_parse_sections():
    svc = ReportTemplateService()
    content = "## 执行摘要\n摘要内容\n## 证据链\n证据内容\n"
    sections = svc._parse_sections(content)
    assert len(sections) == 2
    assert sections[0].title == "执行摘要"
    assert "摘要内容" in sections[0].markdown


def test_fallback_when_template_missing(monkeypatch):
    monkeypatch.setattr(settings, "INVESTIGATION_TEMPLATE_PATH", "missing-template.md")
    svc = ReportTemplateService()
    payload = svc.load_template("deep-research-report")
    assert payload.get("fallback") is True
    assert payload.get("section_count", 0) > 0

