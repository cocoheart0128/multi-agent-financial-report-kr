"""
Compliance Agent（합규 검토 Agent）
职責：검토 보고서 합규성, 면책 고시, 데이터 인용, 규제 합규
Pipeline최후 단계, 보고서가 외부 발행 가능하도록 보장
"""

import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import retry, stop_after_attempt, wait_exponential

from models.report_schema import (
    ComplianceIssue,
    ComplianceReport,
    InvestmentReport,
    CollectedData,
)

logger = logging.getLogger(__name__)

COMPLIANCE_PROMPT = """당신은 금융 규제 합규 전문가입니다.
다음 투자 연구 보고서를 합규 문제에 대해 검토하세요.

보고서 제목: {title}
종목: {ticker}

보고서 내용:
---
요약: {executive_summary}

회사 개요: {company_overview}

재무 분석: {financial_analysis}

기술 분석: {technical_analysis}

감정 개요: {sentiment_overview}

위험 평가: {risk_assessment}

투자 권장 사항: {recommendation}
---

사용된 데이터 소스: {data_sources}

다음 합규 요구사항을 확인하세요:
1. **면책 고시**: 투자 위험 면책 고시를 포함해야 함
2. **데이터 인용**: 모든 데이터 주장은 출처를 참조해야 함
3. **규제 합규**: 내부자 거래 암시 없음, 수익 보장 없음
4. **편견 검사**: 균형잡힌 분석, 과도하게 홍보적이지 않음
5. **전망 진술**: 의견/추정으로 명확하게 표시되어야 함

이 정확한 JSON 형식으로 응답하세요:
{{
    "disclaimer_present": false,
    "data_citations_valid": true,
    "regulatory_compliant": true,
    "bias_check_passed": true,
    "issues": [
        {{
            "severity": "critical|warning|info",
            "category": "disclaimer|data_citation|regulatory|bias",
            "description": "구체적인 문제 설명",
            "location": "보고서에서 문제가 있는 부분",
            "suggestion": "수정 제안"
        }}
    ],
    "compliance_score": 75
}}
"""

DISCLAIMER_TEMPLATE = """
---
**면책 고시 (Disclaimer)**

본 보고서는 참고 목적으로만 제공되며 어떤 투자 조언도 구성하지 않습니다.
투자는 위험을 수반하므로 신중하게 결정하시기 바랍니다.
본 보고서의 정보는 공개 시장 데이터를 출처로 하며, 그 정확성과 완전성을 보장하지 않습니다.
과거 실적은 미래 성과를 보장하지 않습니다.
모든 투자 결정은 자신의 조사와 위험 수용 능력을 기반으로 해야 합니다.

This report is for informational purposes only and does not constitute
investment advice. Past performance is not indicative of future results.
All investments involve risk, including possible loss of principal.

数据来源 / Data Sources: {sources}
报告生成时间: {timestamp}
---
"""


class ComplianceAgent:
    """
    合规审查Agent - 检查报告合规性，自动添加免责声明

    输入: InvestmentReport + CollectedData
    输出: ComplianceReport（含修复建议）

    工作流程:
    1. LLM审查报告内容的合规性
    2. 检查是否包含免责声明
    3. 验证数据引用完整性
    4. 检查是否有误导性表述
    5. 自动生成合规评分

    面试考点:
    - 为什么需要单独的合规Agent？
      → 金融行业有严格的监管要求（SEC/证监会），分离关注点
    - 如果合规不通过怎么办？
      → 返回issues给Report Writer重新修改，可设置最大循环次数
    """

    def __init__(self):
        self.name = "ComplianceAgent"
        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"),
            temperature=0.1,
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute(
        self,
        report: InvestmentReport,
        collected_data: CollectedData,
    ) -> ComplianceReport:
        """执行合规审查"""
        logger.info("[%s] Reviewing compliance for %s", self.name, report.ticker)

        llm_result = await self._review_with_llm(report, collected_data)

        issues = [
            ComplianceIssue(
                severity=issue["severity"],
                category=issue["category"],
                description=issue["description"],
                location=issue.get("location", ""),
                suggestion=issue.get("suggestion", ""),
            )
            for issue in llm_result.get("issues", [])
        ]

        disclaimer_present = llm_result.get("disclaimer_present", False)
        if not disclaimer_present:
            issues.append(
                ComplianceIssue(
                    severity="critical",
                    category="disclaimer",
                    description="报告缺少免责声明",
                    location="报告末尾",
                    suggestion="添加标准免责声明模板",
                )
            )

        data_citations_valid = llm_result.get("data_citations_valid", True)
        regulatory_compliant = llm_result.get("regulatory_compliant", True)
        bias_passed = llm_result.get("bias_check_passed", True)

        compliance_score = llm_result.get("compliance_score", 50.0)
        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        compliance_score = max(0, compliance_score - critical_count * 20 - warning_count * 5)

        is_compliant = critical_count == 0 and compliance_score >= 60

        result = ComplianceReport(
            is_compliant=is_compliant,
            issues=issues,
            disclaimer_present=disclaimer_present,
            data_citations_valid=data_citations_valid,
            regulatory_compliant=regulatory_compliant,
            bias_check_passed=bias_passed,
            compliance_score=min(100, max(0, compliance_score)),
        )

        logger.info(
            "[%s] Compliance: %s (score: %.0f, issues: %d critical, %d warning)",
            self.name,
            "PASS" if is_compliant else "FAIL",
            result.compliance_score,
            critical_count,
            warning_count,
        )
        return result

    def get_disclaimer(self, data_sources: list[str], timestamp: str) -> str:
        """生成标准免责声明"""
        return DISCLAIMER_TEMPLATE.format(
            sources=", ".join(data_sources),
            timestamp=timestamp,
        )

    async def _review_with_llm(
        self, report: InvestmentReport, collected_data: CollectedData
    ) -> dict:
        """使用LLM审查合规性"""
        try:
            prompt = COMPLIANCE_PROMPT.format(
                title=report.title,
                ticker=report.ticker,
                executive_summary=report.executive_summary,
                company_overview=report.company_overview[:300],
                financial_analysis=report.financial_analysis[:300],
                technical_analysis=report.technical_analysis[:300],
                sentiment_overview=report.sentiment_overview[:300],
                risk_assessment=report.risk_assessment[:300],
                recommendation=report.investment_recommendation[:300],
                data_sources=", ".join(collected_data.data_sources),
            )

            response = await self.llm.ainvoke(prompt)
            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            return json.loads(content.strip())
        except Exception as e:
            logger.warning("LLM compliance review failed: %s, using defaults", e)
            return {
                "disclaimer_present": False,
                "data_citations_valid": True,
                "regulatory_compliant": True,
                "bias_check_passed": True,
                "issues": [],
                "compliance_score": 70,
            }
