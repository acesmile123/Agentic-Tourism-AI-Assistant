from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tourism_agent.agent.planner import AgentPlanner
from tourism_agent.agent.workflow import AgentWorkflow
from tourism_agent.core.config import Settings, get_settings
from tourism_agent.evaluation.analysis import (
    analyze_case,
    compare_baseline,
    markdown_report,
    recommendations,
    summarize,
)
from tourism_agent.evaluation.judge import GenerationJudge
from tourism_agent.evaluation.metrics import retrieval_metrics, routing_metrics
from tourism_agent.evaluation.models import CaseResult, EvaluationCase
from tourism_agent.mcp.client import MCPToolRegistry
from tourism_agent.mcp.server import build_tool_registry
from tourism_agent.observability import build_observability
from tourism_agent.services.generation import GeminiGenerationService


def load_dataset(path: Path) -> list[EvaluationCase]:
    cases = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            cases.append(EvaluationCase.model_validate_json(line))
        except Exception as exc:
            raise ValueError(f"Invalid dataset line {line_number}: {exc}") from exc
    if not cases:
        raise ValueError("Evaluation dataset is empty")
    return cases


class TourismEvaluationRunner:
    def __init__(self, tools, workflow: AgentWorkflow, judge: GenerationJudge, observer, k: int = 5):
        self.tools = tools
        self.workflow = workflow
        self.judge = judge
        self.observer = observer
        self.k = max(1, int(k))

    def run_case(self, case: EvaluationCase) -> CaseResult:
        with self.observer.span(
            f"evaluation.{case.id}",
            as_type="evaluator",
            input=case.model_dump(),
        ) as span:
            documents = self._retrieve_documents(case.query) if case.relevant_targets else []
            retrieval = retrieval_metrics(documents, case.relevant_targets, self.k)

            state = self.workflow.run(case.query, [])
            answer = state.get("final_answer", "")
            tool_results = state.get("tool_results", [])
            selected_tools = [str(item.get("tool_name", "")) for item in tool_results]
            routing = routing_metrics(selected_tools, case.expected_tools)
            context = "\n".join(
                str(item.get("content", "")) for item in tool_results if item.get("success")
            )
            generation = self.judge.score(case.query, answer, context, case.reference_answer)
            metrics = {
                **retrieval,
                **routing,
                "faithfulness": generation.faithfulness,
                "relevance": generation.relevance,
            }
            result = CaseResult(
                id=case.id,
                query=case.query,
                category=case.category,
                answer=answer,
                selected_tools=selected_tools,
                metrics=metrics,
                failures=analyze_case(metrics),
                metadata={
                    "judge_method": generation.method,
                    "judge_rationale": generation.rationale,
                    "retrieved_document_count": len(documents),
                    "retry_count": state.get("retry_count", 0),
                    "validation": state.get("validation", {}),
                },
            )
            span.update(
                output=result.model_dump(),
                level="WARNING" if result.failures else "DEFAULT",
            )
            return result

    def _retrieve_documents(self, query: str) -> list[dict[str, Any]]:
        result = self.tools.execute("search_tourism_knowledge", {"query": query})
        if not result.success:
            return []
        try:
            payload = json.loads(result.content)
            return list(payload.get("internal_retrieval", {}).get("chunks", []))
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []


def build_runner(settings: Settings, transport: str, use_llm_judge: bool, k: int):
    observer = build_observability(settings)
    generator = GeminiGenerationService(
        settings.gemini_api_key,
        settings.gemini_fast_model,
        settings.gemini_complex_model,
        observer=observer,
    )
    if transport == "mcp":
        tools = MCPToolRegistry(
            settings.mcp_server_url,
            settings.mcp_read_timeout_seconds,
            settings.mcp_discovery_ttl_seconds,
            observer=observer,
        )
    else:
        tools = build_tool_registry(settings, observer)
    workflow = AgentWorkflow(
        AgentPlanner(generator),
        tools,
        generator,
        max_retries=settings.agent_max_retries,
        observer=observer,
    )
    return TourismEvaluationRunner(
        tools,
        workflow,
        GenerationJudge(generator, use_llm=use_llm_judge),
        observer,
        k,
    ), observer


def run_evaluation(args: argparse.Namespace) -> tuple[dict[str, Any], bool]:
    settings = get_settings()
    cases = load_dataset(args.dataset)
    if args.limit:
        cases = cases[:args.limit]
    runner, observer = build_runner(settings, args.transport, not args.no_llm_judge, args.k)
    try:
        results = [runner.run_case(case) for case in cases]
    finally:
        observer.flush()

    summary = summarize(results)
    report: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset),
        "transport": args.transport,
        "retrieval_k": args.k,
        "summary": summary,
        "cases": [result.model_dump() for result in results],
        "recommendations": recommendations(summary),
    }
    passed = True
    if args.baseline:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        comparison = compare_baseline(summary, baseline, args.regression_tolerance)
        report["baseline_comparison"] = comparison
        passed = comparison["passed"]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = args.output_dir / f"tourism-eval-{timestamp}.json"
    markdown_path = args.output_dir / f"tourism-eval-{timestamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return report, passed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the tourism RAG + agent pipeline")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/datasets/tourism_ai_eval.jsonl"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("eval_reports"))
    parser.add_argument("--transport", choices=("local", "mcp"), default="local")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-llm-judge", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--regression-tolerance", type=float, default=0.02)
    parser.add_argument("--fail-on-regression", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _, passed = run_evaluation(args)
    return 1 if args.fail_on_regression and not passed else 0


if __name__ == "__main__":
    sys.exit(main())
