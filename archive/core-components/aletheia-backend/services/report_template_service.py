"""
报告模板解析服务
将 deep-research-report.md 解析为可渲染章节模板
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List

from core.config import settings
from utils.logging import logger


@dataclass
class TemplateSection:
    id: str
    title: str
    markdown: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "markdown": self.markdown,
        }


class ReportTemplateService:
    """deep-research-report 章节模板解析器"""

    def __init__(self) -> None:
        self._cache: Dict[str, Any] | None = None
        self._cache_path: str | None = None

    def load_template(
        self, template_id: str = "deep-research-report"
    ) -> Dict[str, Any]:
        """加载模板；失败时回退到内置模板。"""
        target_path = self._resolve_template_path(template_id)
        self._cache_path = str(target_path)

        try:
            raw = target_path.read_text(encoding="utf-8")
            sections = self._parse_sections(raw)
            if not sections:
                raise ValueError("template has no sections")
            payload = {
                "template_id": template_id,
                "version": datetime.utcnow().strftime("%Y%m%d"),
                "checksum": sha256(raw.encode("utf-8")).hexdigest(),
                "path": str(target_path),
                "section_count": len(sections),
                "sections": [s.to_dict() for s in sections],
            }
            self._cache = payload
            return payload
        except Exception as exc:
            logger.warning(f"Template load failed, fallback enabled: {exc}")
            fallback = self._fallback_template(template_id)
            self._cache = fallback
            return fallback

    def get_cached_or_load(self, template_id: str = "deep-research-report") -> Dict[str, Any]:
        if self._cache and template_id == self._cache.get("template_id"):
            return self._cache
        return self.load_template(template_id=template_id)

    def _resolve_template_path(self, template_id: str) -> Path:
        if template_id != "deep-research-report":
            raise ValueError(f"unsupported template_id: {template_id}")

        configured = Path(settings.INVESTIGATION_TEMPLATE_PATH)
        if configured.is_absolute():
            return configured

        # 以 aletheia-backend 根目录为基准拼接
        backend_root = Path(__file__).resolve().parents[1]
        return (backend_root / configured).resolve()

    def _parse_sections(self, markdown_text: str) -> List[TemplateSection]:
        sections: List[TemplateSection] = []
        current_title: str | None = None
        current_lines: List[str] = []

        for line in markdown_text.splitlines():
            if line.startswith("## "):
                if current_title is not None:
                    sections.append(
                        self._make_section(current_title, "\n".join(current_lines).strip())
                    )
                current_title = line[3:].strip()
                current_lines = []
                continue
            current_lines.append(line)

        if current_title is not None:
            sections.append(
                self._make_section(current_title, "\n".join(current_lines).strip())
            )

        return sections

    def _make_section(self, title: str, markdown: str) -> TemplateSection:
        section_id = (
            title.lower()
            .replace(" ", "-")
            .replace("/", "-")
            .replace("、", "-")
            .replace("：", "-")
            .replace(":", "-")
        )
        if not section_id:
            section_id = f"section-{abs(hash(title))}"
        return TemplateSection(id=section_id, title=title, markdown=markdown)

    def _fallback_template(self, template_id: str) -> Dict[str, Any]:
        sections = [
            TemplateSection(
                id="summary",
                title="执行摘要",
                markdown="自动回退模板：展示关键结论、风险和证据覆盖。",
            ),
            TemplateSection(
                id="evidence",
                title="证据链",
                markdown="展示证据卡片、来源等级、支持/反驳立场。",
            ),
            TemplateSection(
                id="recommendation",
                title="处置建议",
                markdown="给出下一步补证查询与人工复核建议。",
            ),
        ]
        raw = "\n".join([s.title + s.markdown for s in sections])
        return {
            "template_id": template_id,
            "version": "fallback",
            "checksum": sha256(raw.encode("utf-8")).hexdigest(),
            "path": self._cache_path or "fallback",
            "section_count": len(sections),
            "sections": [s.to_dict() for s in sections],
            "fallback": True,
        }


_report_template_service: ReportTemplateService | None = None


def get_report_template_service() -> ReportTemplateService:
    global _report_template_service
    if _report_template_service is None:
        _report_template_service = ReportTemplateService()
    return _report_template_service

