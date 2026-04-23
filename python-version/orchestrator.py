"""
Orchestrator（编排器）- 核心Pipeline + Fan-out并行编排逻辑

架构设计：
    用户输入(股票代码) → Orchestrator
        → [Data Collector + Sentiment Agent] (并行 Fan-out)
        → Market Analyst (串行，等待上游完成)
        → Report Writer (串行)
        → Compliance Agent (串行)
        → 输出 FinalReport

面试关键：
    这是整个系统的核心，面试官最可能问的就是编排逻辑。
    要能清楚解释为什么用 asyncio.gather() 实现并行，
    以及如何处理其中一个Agent失败的降级策略。
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents.data_collector import DataCollectorAgent
from agents.sentiment_agent import SentimentAgent
from agents.market_analyst import MarketAnalystAgent
from agents.report_writer import ReportWriterAgent
from agents.compliance_agent import ComplianceAgent
from models.report_schema import FinalReport, StockQuery

logger = logging.getLogger(__name__)
console = Console()


class ReportOrchestrator:
    """
    报告生成编排器 - Pipeline + Fan-out 并行模式

    执行流程:
    ┌─────────────────────────────────────────────────┐
    │  Stage 1: Fan-out (并行)                         │
    │  ┌──────────────────┐  ┌─────────────────────┐  │
    │  │ Data Collector    │  │ Sentiment Agent      │  │
    │  │ (Yahoo+SEC)       │  │ (Tavily+LLM)        │  │
    │  └────────┬─────────┘  └──────────┬──────────┘  │
    │           └──────────┬────────────┘              │
    │  Stage 2: Pipeline (串行)                        │
    │  ┌──────────────────┐                            │
    │  │ Market Analyst    │ ← 依赖Stage1的两个输出     │
    │  └────────┬─────────┘                            │
    │  ┌──────────────────┐                            │
    │  │ Report Writer     │                           │
    │  └────────┬─────────┘                            │
    │  ┌──────────────────┐                            │
    │  │ Compliance Agent  │                           │
    │  └────────┬─────────┘                            │
    │           ▼                                      │
    │     FinalReport (PDF + Markdown + JSON)          │
    └─────────────────────────────────────────────────┘
    """

    def __init__(self):
        self.data_collector = DataCollectorAgent()
        self.sentiment_agent = SentimentAgent()
        self.market_analyst = MarketAnalystAgent()
        self.report_writer = ReportWriterAgent()
        self.compliance_agent = ComplianceAgent()

    async def generate_report(self, query: StockQuery) -> FinalReport:
        """
        执行完整的报告生成Pipeline

        关键实现：asyncio.gather() 实现Fan-out并行
        Data Collector 和 Sentiment Agent 同时启动，等最慢的完成后继续
        """
        start_time = time.time()
        console.print(Panel(
            f"[bold green]한국 기업 {query.ticker} 투자 연구보고서 생성 시작[/bold green]\n"
            f"분석 주기: {query.period} | 언어: {query.language}",
            title="한국 특화 Multi-Agent 금융 보고서 시스템",
        ))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # ====== Stage 1: Fan-out 병렬 실행 ======
            task1 = progress.add_task(
                "[cyan]Stage 1: 데이터 수집 + 감정 분석 (병렬 실행 중)...", total=None
            )

            # 핵심 병렬 로직: asyncio.gather() 동시 실행
            collected_data, sentiment = await asyncio.gather(
                self.data_collector.execute(query),
                self.sentiment_agent.execute(query),
            )
            progress.update(task1, description="[green]Stage 1: 데이터 수집 + 감정 분석 ✓")

            stage1_time = time.time() - start_time
            console.print(f"  ├── 데이터 수집 완료: {len(collected_data.recent_prices)} 개 주가 기록")
            console.print(f"  ├── 감정 분석 완료: {sentiment.overall_sentiment.value} ({sentiment.sentiment_score:.2f})")
            console.print(f"  └── Stage 1 소요 시간: {stage1_time:.1f}초 (병렬)")

            # ====== Stage 2: 시장 분석 (Stage 1 의존) ======
            task2 = progress.add_task(
                "[cyan]Stage 2: 시장 분석...", total=None
            )
            market_analysis = await self.market_analyst.execute(
                collected_data, sentiment
            )
            progress.update(task2, description="[green]Stage 2: 시장 분석 ✓")
            console.print(f"  ├── 투자 조언: {market_analysis.recommendation.value}")
            console.print(f"  └── 위험 등급: {market_analysis.overall_risk_level.value}")

            # ====== Stage 3: 보고서 작성 ======
            task3 = progress.add_task(
                "[cyan]Stage 3: 보고서 작성...", total=None
            )
            report = await self.report_writer.execute(
                collected_data, sentiment, market_analysis, query.language
            )
            progress.update(task3, description="[green]Stage 3: 보고서 작성 ✓")

            # ====== Stage 4: 합규 검토 ======
            task4 = progress.add_task(
                "[cyan]Stage 4: 합규 검토...", total=None
            )
            compliance = await self.compliance_agent.execute(report, collected_data)
            progress.update(task4, description="[green]Stage 4: 합규 검토 ✓")

            compliance_status = "✅ 통과" if compliance.is_compliant else "⚠️ 수정 필요"
            console.print(f"  ├── 합규 상태: {compliance_status}")
            console.print(f"  └── 합규 점수: {compliance.compliance_score:.0f}/100")

        total_time = time.time() - start_time

        final_report = FinalReport(
            report=report,
            compliance=compliance,
            collected_data=collected_data,
            sentiment=sentiment,
            market_analysis=market_analysis,
            metadata={
                "ticker": query.ticker,
                "period": query.period,
                "total_time_seconds": round(total_time, 2),
                "stage1_parallel_time": round(stage1_time, 2),
                "generated_at": datetime.now().isoformat(),
                "agents_used": [
                    "DataCollectorAgent",
                    "SentimentAgent",
                    "MarketAnalystAgent",
                    "ReportWriterAgent",
                    "ComplianceAgent",
                ],
            },
        )

        console.print(Panel(
            f"[bold green]보고서 생성 완료![/bold green]\n"
            f"총 소요 시간: {total_time:.1f}초 | 병렬 처리: {stage1_time:.1f}초\n"
            f"투자 조언: {market_analysis.recommendation.value} | "
            f"합규 상태: {compliance_status}",
            title="보고서 생성 완료",
        ))

        return final_report

    async def save_outputs(
        self, final_report: FinalReport, output_dir: str = "./output", language: str = "ko"
    ) -> dict[str, str]:
        """여러 형식으로 보고서 저장"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        ticker = final_report.report.ticker
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{ticker}_{timestamp}"

        paths = {}

        # 언어 변환 처리
        if language != "ko":
            final_report = await self._translate_report(final_report, language)

        # JSON
        json_path = os.path.join(output_dir, f"{prefix}_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(final_report.model_dump(), f, ensure_ascii=False, indent=2)
        paths["json"] = json_path

        # Markdown
        md_path = os.path.join(output_dir, f"{prefix}_report.md")
        md_content = self._to_markdown(final_report, language)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        paths["markdown"] = md_path

        # PDF
        try:
            pdf_path = os.path.join(output_dir, f"{prefix}_report.pdf")
            self._to_pdf(final_report, pdf_path, language)
            paths["pdf"] = pdf_path
        except Exception as e:
            logger.warning("PDF generation failed: %s", e)

        console.print(f"\n[bold]输出文件:[/bold]")
        for fmt, path in paths.items():
            console.print(f"  📄 {fmt.upper()}: {path}")

        return paths

    def _to_markdown(self, final: FinalReport, language: str = "zh") -> str:
        """转换为Markdown格式"""
        section_titles = {
            "zh": {
                "title": "# {title}",
                "ticker": "**股票代码**: {ticker}",
                "generated_at": "**生成时间**: {generated_at}",
                "recommendation": "**投资建议**: {recommendation}",
                "compliance_score": "**合规评分**: {compliance_score}/100",
                "executive_summary": "## 执行摘要",
                "company_overview": "## 公司概况",
                "financial_analysis": "## 财务分析",
                "technical_analysis": "## 技术分析",
                "sentiment_overview": "## 舆情概览",
                "risk_assessment": "## 风险评估",
                "investment_recommendation": "## 投资建议",
                "disclaimer": "## 免责声明",
            },
            "en": {
                "title": "# {title}",
                "ticker": "**Ticker**: {ticker}",
                "generated_at": "**Generated**: {generated_at}",
                "recommendation": "**Recommendation**: {recommendation}",
                "compliance_score": "**Compliance Score**: {compliance_score}/100",
                "executive_summary": "## Executive Summary",
                "company_overview": "## Company Overview",
                "financial_analysis": "## Financial Analysis",
                "technical_analysis": "## Technical Analysis",
                "sentiment_overview": "## Sentiment Overview",
                "risk_assessment": "## Risk Assessment",
                "investment_recommendation": "## Investment Recommendation",
                "disclaimer": "## Disclaimer",
            },
            "ko": {
                "title": "# {title}",
                "ticker": "**종목코드**: {ticker}",
                "generated_at": "**생성시간**: {generated_at}",
                "recommendation": "**투자 권고**: {recommendation}",
                "compliance_score": "**컴플라이언스 점수**: {compliance_score}/100",
                "executive_summary": "## 요약",
                "company_overview": "## 기업 개요",
                "financial_analysis": "## 재무 분석",
                "technical_analysis": "## 기술 분석",
                "sentiment_overview": "## 시장 심리",
                "risk_assessment": "## 위험 평가",
                "investment_recommendation": "## 투자 제안",
                "disclaimer": "## 면책 조항",
            },
            "ja": {
                "title": "# {title}",
                "ticker": "**銘柄コード**: {ticker}",
                "generated_at": "**生成日時**: {generated_at}",
                "recommendation": "**推奨**: {recommendation}",
                "compliance_score": "**コンプライアンススコア**: {compliance_score}/100",
                "executive_summary": "## エグゼクティブサマリー",
                "company_overview": "## 企業概要",
                "financial_analysis": "## 財務分析",
                "technical_analysis": "## 技術分析",
                "sentiment_overview": "## 市場心理",
                "risk_assessment": "## リスク評価",
                "investment_recommendation": "## 投資提案",
                "disclaimer": "## 免責事項",
            },
        }
        
        titles = section_titles.get(language, section_titles["zh"])
        r = final.report
        c = final.compliance
        disclaimer = self.compliance_agent.get_disclaimer(
            final.collected_data.data_sources,
            r.generated_at,
        )

        content = titles["title"].format(title=r.title) + "\n\n"
        content += titles["ticker"].format(ticker=r.ticker) + "\n"
        content += titles["generated_at"].format(generated_at=r.generated_at) + "\n"
        content += titles["recommendation"].format(recommendation=r.recommendation.value) + "\n"
        content += titles["compliance_score"].format(compliance_score=int(c.compliance_score)) + "\n\n"
        content += "---\n\n"
        content += titles["executive_summary"] + "\n\n"
        content += r.executive_summary + "\n\n"
        content += titles["company_overview"] + "\n\n"
        content += r.company_overview + "\n\n"
        content += titles["financial_analysis"] + "\n\n"
        content += r.financial_analysis + "\n\n"
        content += titles["technical_analysis"] + "\n\n"
        content += r.technical_analysis + "\n\n"
        content += titles["sentiment_overview"] + "\n\n"
        content += r.sentiment_overview + "\n\n"
        content += titles["risk_assessment"] + "\n\n"
        content += r.risk_assessment + "\n\n"
        content += titles["investment_recommendation"] + "\n\n"
        content += r.investment_recommendation + "\n\n"
        content += titles["disclaimer"] + "\n\n"
        content += disclaimer

        return content

    def _to_pdf(self, final: FinalReport, path: str, language: str = "zh") -> None:
        """转换为PDF格式（使用ReportLab）"""
        section_titles = {
            "zh": ["Executive Summary", "Company Overview", "Financial Analysis", "Technical Analysis", 
                   "Sentiment Overview", "Risk Assessment", "Investment Recommendation"],
            "en": ["Executive Summary", "Company Overview", "Financial Analysis", "Technical Analysis", 
                   "Sentiment Overview", "Risk Assessment", "Investment Recommendation"],
            "ko": ["요약", "기업 개요", "재무 분석", "기술 분석", 
                   "시장 심리", "위험 평가", "투자 제안"],
            "ja": ["エグゼクティブサマリー", "企業概要", "財務分析", "技術分析", 
                   "市場心理", "リスク評価", "投資提案"],
        }
        
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.units import inch

        # 注册 CJK 字体支持中文/日文/韩文
        try:
            # macOS
            font_path = "/System/Library/Fonts/STHeiti Medium.ttc"
            pdfmetrics.registerFont(TTFont("HeiTi", font_path))
            font_name = "HeiTi"
        except:
            try:
                # Linux/其他系统
                font_path = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
                pdfmetrics.registerFont(TTFont("NotoSans", font_path))
                font_name = "NotoSans"
            except:
                # 回退到 Helvetica
                font_name = "Helvetica"

        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "CustomTitle", parent=styles["Title"], fontSize=18, spaceAfter=20, fontName=font_name
        )
        heading_style = ParagraphStyle(
            "CustomHeading", parent=styles["Heading2"], fontSize=14, spaceAfter=10, fontName=font_name
        )
        body_style = ParagraphStyle(
            "CustomBody", parent=styles["Normal"], fontSize=10, spaceAfter=8, leading=14, fontName=font_name
        )

        story = []
        r = final.report
        titles = section_titles.get(language, section_titles["zh"])

        story.append(Paragraph(r.title, title_style))
        story.append(Paragraph(
            f"Ticker: {r.ticker} | Generated: {r.generated_at} | "
            f"Recommendation: {r.recommendation.value}",
            body_style,
        ))
        story.append(Spacer(1, 0.3 * inch))

        sections = [
            (titles[0], r.executive_summary),
            (titles[1], r.company_overview),
            (titles[2], r.financial_analysis),
            (titles[3], r.technical_analysis),
            (titles[4], r.sentiment_overview),
            (titles[5], r.risk_assessment),
            (titles[6], r.investment_recommendation),
        ]

        for title, content in sections:
            story.append(Paragraph(title, heading_style))
            for para in content.split("\n"):
                if para.strip():
                    safe = para.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(safe, body_style))
            story.append(Spacer(1, 0.2 * inch))

        story.append(Paragraph("Disclaimer", heading_style))
        story.append(Paragraph(
            "This report is for informational purposes only and does not constitute "
            "investment advice. Past performance is not indicative of future results.",
            body_style,
        ))

        doc.build(story)

    async def _translate_report(self, final_report: FinalReport, target_language: str) -> FinalReport:
        """使用LLM将报告翻译为目标语言"""
        language_map = {
            "en": "English",
            "ko": "Korean",
            "ja": "Japanese",
        }
        target_lang_name = language_map.get(target_language, "English")
        
        translate_prompt = f"""Translate the following investment report into {target_lang_name}.
Keep the format and structure exactly the same. Only translate the text content.

Original Report:
{{report_content}}

Provide the translated report in the same JSON structure.
"""
        
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=os.getenv("GOOGLE_MODEL", "gemini-1.5-pro"),
                temperature=0.1,
            )
            
            report_json = json.dumps(final_report.report.model_dump(), ensure_ascii=False, indent=2)
            prompt = translate_prompt.format(report_content=report_json)
            response = await llm.ainvoke(prompt)
            
            import re
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            translated_data = json.loads(content.strip())
            final_report.report = final_report.report.__class__(**translated_data)
            
        except Exception as e:
            logger.warning("Translation failed: %s, using original report", e)
        
        return final_report
