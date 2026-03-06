"""
Aletheia Report Generator
=========================

借鉴 BettaFish ReportEngine 的章节生成机制，
为 Aletheia 提供自动报告生成功能。

核心能力：
1. 基于模板生成结构化报告
2. 章节级内容生成
3. 报告格式化与渲染
"""

import json
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class ReportSection:
    """报告章节"""

    section_id: str
    title: str
    content: str = ""
    level: int = 1
    order: int = 0
    template_hint: str = ""  # 模板提示词


@dataclass
class ReportTemplate:
    """报告模板"""

    name: str
    description: str
    sections: List[ReportSection] = field(default_factory=list)
    style_guide: Dict[str, Any] = field(default_factory=dict)


class ReportGenerator:
    """
    报告生成器

    基于 BettaFish ReportEngine 的设计理念，
    提供结构化的自动报告生成功能。
    """

    # 预定义模板
    TEMPLATES = {
        "verification": {
            "name": "信息核验报告",
            "description": "针对单一信息的深度核验报告",
            "sections": [
                {"id": "summary", "title": "执行摘要", "level": 1},
                {"id": "claim_analysis", "title": "命题分析", "level": 1},
                {"id": "source_verification", "title": "信源验证", "level": 1},
                {"id": "cross_validation", "title": "交叉验证", "level": 1},
                {"id": "conclusion", "title": "结论与建议", "level": 1},
            ],
        },
        "event_analysis": {
            "name": "舆情事件分析报告",
            "description": "针对热点事件的全面分析报告",
            "sections": [
                {"id": "overview", "title": "事件概述", "level": 1},
                {"id": "timeline", "title": "传播时间线", "level": 1},
                {"id": "platform_analysis", "title": "平台分析", "level": 1},
                {"id": "sentiment_analysis", "title": "情感分析", "level": 1},
                {"id": "key_accounts", "title": "关键账号", "level": 1},
                {"id": "risk_assessment", "title": "风险评估", "level": 1},
                {"id": "recommendations", "title": "应对建议", "level": 1},
            ],
        },
        "brief": {
            "name": "简要核验简报",
            "description": "快速核验结果的简要报告",
            "sections": [
                {"id": "result", "title": "核验结果", "level": 1},
                {"id": "evidence", "title": "关键证据", "level": 1},
                {"id": "recommendation", "title": "建议", "level": 1},
            ],
        },
    }

    def __init__(self, llm_client: Any = None):
        """
        初始化报告生成器

        Args:
            llm_client: LLM 客户端实例（可选）
        """
        self.llm_client = llm_client
        logger.info("ReportGenerator 已初始化")

    def generate(
        self,
        state: Any,  # AgentState
        template_name: str = "verification",
        custom_sections: List[Dict] = None,
        style: str = "formal",
    ) -> str:
        """
        生成报告

        Args:
            state: Agent 状态对象
            template_name: 模板名称
            custom_sections: 自定义章节列表
            style: 报告风格 (formal/short/media)

        Returns:
            Markdown 格式的报告
        """
        logger.info(f"开始生成报告，模板: {template_name}")

        # 获取模板
        template = self._get_template(template_name, custom_sections)

        # 生成各章节
        sections_content = []
        for section_template in template["sections"]:
            section = self._generate_section(section_template, state, style)
            sections_content.append(section)

        # 组装报告
        report = self._assemble_report(template, sections_content, state)

        logger.info(f"报告生成完成，总长度: {len(report)} 字符")
        return report

    def _get_template(
        self, template_name: str, custom_sections: List[Dict] = None
    ) -> Dict:
        """获取报告模板"""
        if custom_sections:
            return {"name": "自定义报告", "sections": custom_sections}

        return self.TEMPLATES.get(template_name, self.TEMPLATES["verification"])

    def _generate_section(
        self, section_template: Dict, state: Any, style: str
    ) -> Dict[str, str]:
        """生成单个章节内容"""
        section_id = section_template["id"]
        title = section_template["title"]

        # 根据章节类型生成内容
        generators = {
            "summary": self._generate_summary_section,
            "claim_analysis": self._generate_claim_section,
            "source_verification": self._generate_source_section,
            "cross_validation": self._generate_validation_section,
            "conclusion": self._generate_conclusion_section,
            "result": self._generate_result_section,
            "evidence": self._generate_evidence_section,
            "recommendation": self._generate_recommendation_section,
        }

        generator = generators.get(section_id, self._generate_generic_section)
        content = generator(state, style)

        return {
            "id": section_id,
            "title": title,
            "content": content,
            "level": section_template.get("level", 1),
        }

    def _generate_summary_section(self, state: Any, style: str) -> str:
        """生成执行摘要"""
        score = getattr(state, "credibility_score", 0)
        level = getattr(state, "credibility_level", "UNCERTAIN")
        query = getattr(state, "query", "")

        summary = getattr(state.verification, "current_summary", "")

        lines = [
            f"## 核验对象",
            f"",
            f"> {query}",
            f"",
            f"## 核验结论",
            f"",
            f"- **可信度评分**: {score:.1%}",
            f"- **可信度等级**: {level}",
            f"- **验证状态**: {'已完成' if getattr(state, 'is_completed', False) else '进行中'}",
            f"",
        ]

        if summary:
            lines.extend(
                [
                    f"## 核心发现",
                    f"",
                    summary,
                    f"",
                ]
            )

        return "\n".join(lines)

    def _generate_claim_section(self, state: Any, style: str) -> str:
        """生成命题分析章节"""
        reasoning_chain = getattr(state.verification, "reasoning_chain", [])

        lines = ["## 命题解析"]

        if reasoning_chain:
            first_step = reasoning_chain[0] if reasoning_chain else None
            if first_step:
                lines.extend(
                    [
                        f"",
                        f"**推理过程**: {getattr(first_step, 'reasoning', 'N/A')}",
                        f"",
                        f"**初步结论**: {getattr(first_step, 'conclusion', 'N/A')}",
                        f"",
                        f"**置信度**: {getattr(first_step, 'confidence', 0):.0%}",
                    ]
                )

        return "\n".join(lines)

    def _generate_source_section(self, state: Any, style: str) -> str:
        """生成信源验证章节"""
        search_history = getattr(state.verification, "search_history", [])

        if not search_history:
            return "## 信源验证\n\n暂无语源数据。"

        lines = [
            "## 信源验证",
            f"",
            f"共检索到 **{len(search_history)}** 条相关记录：",
            f"",
        ]

        # 按平台分组统计
        platform_stats = {}
        for result in search_history:
            platform = getattr(result, "platform", "unknown")
            platform_stats[platform] = platform_stats.get(platform, 0) + 1

        lines.append("### 平台分布")
        lines.append("")
        for platform, count in sorted(platform_stats.items(), key=lambda x: -x[1]):
            lines.append(f"- {platform}: {count} 条")
        lines.append("")

        # 高质量信源
        high_quality = [
            r for r in search_history if getattr(r, "evidence_quality", "") == "high"
        ]
        if high_quality:
            lines.append(f"### 高可信度信源 ({len(high_quality)} 条)")
            lines.append("")
            for result in high_quality[:5]:
                title = getattr(result, "title", "")[:50]
                url = getattr(result, "url", "")
                platform = getattr(result, "platform", "unknown")
                lines.append(f"- [{platform}] {title}...")
                if url:
                    lines.append(f"  - {url}")
            lines.append("")

        return "\n".join(lines)

    def _generate_validation_section(self, state: Any, style: str) -> str:
        """生成交叉验证章节"""
        reasoning_chain = getattr(state.verification, "reasoning_chain", [])

        lines = ["## 交叉验证"]

        if len(reasoning_chain) > 2:
            lines.append("")
            lines.append("### 推理链")
            lines.append("")

            for i, step in enumerate(reasoning_chain[1:-1], 1):
                stage = getattr(step, "stage", f"Step {i}")
                conclusion = getattr(step, "conclusion", "")
                confidence = getattr(step, "confidence", 0)

                lines.append(f"**{i}. {stage}**")
                lines.append(f"- 结论: {conclusion}")
                lines.append(f"- 置信度: {confidence:.0%}")
                lines.append("")

        return "\n".join(lines)

    def _generate_conclusion_section(self, state: Any, style: str) -> str:
        """生成结论章节"""
        score = getattr(state, "credibility_score", 0)
        level = getattr(state, "credibility_level", "UNCERTAIN")
        risk_flags = getattr(state, "risk_flags", [])

        # 根据可信度生成建议
        if score >= 0.8:
            verdict = "✅ **该信息可信度较高**"
            advice = "可放心引用，但建议标注信息来源。"
        elif score >= 0.6:
            verdict = "⚠️ **该信息部分可信**"
            advice = "需要结合其他来源进一步验证，谨慎引用。"
        elif score >= 0.4:
            verdict = "⚠️ **该信息可信度存疑**"
            advice = "建议查找更多权威来源进行核实。"
        else:
            verdict = "❌ **该信息可信度较低**"
            advice = "不建议引用，可能存在误导性。"

        lines = [
            "## 结论与建议",
            f"",
            verdict,
            f"",
            f"**可信度**: {score:.1%} ({level})",
            f"",
        ]

        if risk_flags:
            lines.extend(
                [
                    f"**风险提示**:",
                ]
            )
            for flag in risk_flags:
                lines.append(f"- {flag}")
            lines.append("")

        lines.extend(
            [
                f"**建议**: {advice}",
            ]
        )

        return "\n".join(lines)

    def _generate_result_section(self, state: Any, style: str) -> str:
        """生成结果章节（简报用）"""
        return self._generate_summary_section(state, style)

    def _generate_evidence_section(self, state: Any, style: str) -> str:
        """生成证据章节（简报用）"""
        return self._generate_source_section(state, style)

    def _generate_recommendation_section(self, state: Any, style: str) -> str:
        """生成建议章节（简报用）"""
        return self._generate_conclusion_section(state, style)

    def _generate_generic_section(self, state: Any, style: str) -> str:
        """生成通用章节"""
        return "## 章节内容\n\n（待补充）"

    def _assemble_report(self, template: Dict, sections: List[Dict], state: Any) -> str:
        """组装完整报告"""
        lines = [
            f"# {template['name']}",
            f"",
            f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"> 任务ID: {getattr(state, 'task_id', 'N/A')}",
            f"",
            "---",
            f"",
        ]

        for section in sections:
            lines.append(section["content"])
            lines.append("")
            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def export_to_html(self, markdown_report: str) -> str:
        """
        将 Markdown 报告转换为 HTML

        Args:
            markdown_report: Markdown 格式报告

        Returns:
            HTML 格式报告
        """
        try:
            import markdown

            html = markdown.markdown(
                markdown_report, extensions=["tables", "fenced_code", "toc"]
            )

            # 添加样式
            styled_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Aletheia 核验报告</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        h1 {{
            color: #2563eb;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #374151;
            margin-top: 30px;
        }}
        blockquote {{
            border-left: 4px solid #e5e7eb;
            margin: 0;
            padding-left: 16px;
            color: #6b7280;
        }}
        hr {{
            border: none;
            border-top: 1px solid #e5e7eb;
            margin: 20px 0;
        }}
        code {{
            background: #f3f4f6;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 0.9em;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
        }}
        th, td {{
            border: 1px solid #e5e7eb;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background: #f9fafb;
        }}
    </style>
</head>
<body>
    {html}
</body>
</html>
"""
            return styled_html

        except ImportError:
            logger.warning("markdown 库未安装，返回纯文本")
            return f"<pre>{markdown_report}</pre>"


# 便捷函数
def generate_report(
    state: Any, template: str = "verification", style: str = "formal"
) -> str:
    """
    便捷函数：生成报告

    Args:
        state: Agent 状态
        template: 模板名称
        style: 风格

    Returns:
        Markdown 报告
    """
    generator = ReportGenerator()
    return generator.generate(state, template, style=style)
