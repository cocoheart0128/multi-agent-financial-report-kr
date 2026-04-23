"""
Multi-Agent金融研究报告自动生成系统 - Python版本入口

使用方法:
    # 基本用法
    python main.py AAPL

    # 指定分析周期
    python main.py TSLA --period 6mo

    # 指定输出目录
    python main.py MSFT --output ./reports

    # 指定详细日志
    python main.py NVDA -v

注: 报告生成时(JSON/MD/PDF)可选择输出语言
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

from models.report_schema import StockQuery
from orchestrator import ReportOrchestrator

load_dotenv()

console = Console()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="한국 특화 Multi-Agent 금융 연구보고서 자동생성 시스템",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python main.py 삼성전자                  # 삼성전자 분석
  python main.py 삼성전자 --period 6mo    # 삼성전자, 6개월 주기
  python main.py SK하이닉스 --output ./reports  # 출력 디렉토리 지정
  python main.py NVDA -v                    # 자세한 로그 활성화
        """,
    )
    parser.add_argument("ticker", help="종목명 또는 종목코드 (예: 삼성전자, 005930)")
    parser.add_argument(
        "--period",
        default="1y",
        choices=["1mo", "3mo", "6mo", "1y", "2y"],
        help="분석 주기 (기본값: 1y)",
    )
    parser.add_argument("--output", default="./output", help="출력 디렉토리 (기본값: ./output)")
    parser.add_argument("-v", "--verbose", action="store_true", help="자세한 로그")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    query = StockQuery(
        ticker=args.ticker,
        period=args.period,
        language="ko",  # 기본 언어: 한국어
    )

    console.print(f"\n[bold]한국 특화 Multi-Agent 금융 연구보고서 시스템[/bold]")
    console.print(f"분석 대상: [bold cyan]{query.ticker}[/bold cyan]")
    console.print(f"분석 주기: {query.period}")
    console.print(f"보고서 언어: 한국어\n")

    orchestrator = ReportOrchestrator()

    try:
        final_report = await orchestrator.generate_report(query)
        
        # 최종 보고서 언어 선택
        console.print("\n[bold cyan]보고서 출력 언어 선택:[/bold cyan]")
        console.print("  [1] 한국어 (Korean)")
        console.print("  [2] 영어 (English)")
        console.print("  [3] 중국어 (Chinese)")
        console.print("  [4] 일본어 (Japanese)")
        language_choice = input("선택해주세요 [1-4] (기본값: 1): ").strip() or "1"
        
        language_map = {
            "1": "ko",
            "2": "en",
            "3": "zh",
            "4": "ja",
        }
        output_language = language_map.get(language_choice, "ko")
        
        paths = await orchestrator.save_outputs(final_report, args.output, output_language)

        console.print("\n[bold green]보고서 생성 완료![/bold green]")
        console.print(f"총 소요 시간: {final_report.metadata.get('total_time_seconds', 0):.1f} 초")
        console.print(f"병렬 처리 단계 시간: {final_report.metadata.get('stage1_parallel_time', 0):.1f} 초")

    except KeyboardInterrupt:
        console.print("\n[yellow]사용자가 작업을 취소했습니다[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]보고서 생성 실패: {e}[/bold red]")
        logging.exception("Report generation failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
