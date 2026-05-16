#!/usr/bin/env python3
"""
DAG-Based Evaluation Runner

This script runs the complete evaluation pipeline using a DAG (Directed Acyclic Graph)
for better organization, visualization, and maintainability.

Usage:
    # Run full evaluation
    python -m evaluation.runners.run_dag_evaluation

    # Run with a specific ground-truth file
    python -m evaluation.runners.run_dag_evaluation --ground-truth evaluation/ground_truth_v2_revised.json

    # Run with parallel workers
    python -m evaluation.runners.run_dag_evaluation --ground-truth evaluation/ground_truth_v2_revised.json --workers 4

    # Generate visualization only
    python -m evaluation.runners.run_dag_evaluation --visualize-only

    # Run and save DAG visualization
    python -m evaluation.runners.run_dag_evaluation --save-dag-visualization

    # Resume a crashed/interrupted run from its existing run id
    python -m evaluation.runners.run_dag_evaluation --resume-run-id 20260516_120000
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env")

from evaluation.dag import create_evaluation_pipeline  # noqa: E402


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be >= 1")
    return parsed


def _llamaindex_mode(value: str) -> str:
    valid_modes = {"context", "sql_draft", "hybrid"}
    normalized = value.strip().lower()
    if normalized not in valid_modes:
        raise argparse.ArgumentTypeError(
            "value must be one of: context, sql_draft, hybrid"
        )
    return normalized


def export_ex_zero_failures(
    dag_results: Dict[str, Any],
    output_dir: Path,
    run_id: str | None = None,
) -> Optional[Path]:
    """
    Generate a text file listing only the ground truths with EX score == 0.

    Args:
        dag_results: Results returned by dag.execute()
        output_dir: Directory where the file should be written

    Returns:
        Path to the generated file, or None if no failures were found/created
    """

    eval_task = dag_results.get("evaluate_questions")

    if not eval_task or not getattr(eval_task, "success", False):
        print("⚠️  EX=0 export skipped: evaluate_questions task not available or failed")
        return None

    detailed_results = eval_task.data.get("detailed_results", []) if eval_task.data else []

    ex_zero_entries: List[Tuple[str, str]] = []

    for item in detailed_results:
        metrics = item.get("metrics", {})
        ex_metric = metrics.get("Execution Accuracy (EX)")

        # Skip if metric is missing
        if ex_metric is None:
            continue

        score = ex_metric.get("score", 0)

        try:
            score_float = float(score)
        except (TypeError, ValueError):
            score_float = 0.0

        if score_float == 0.0:
            question_id = item.get("question_id") or item.get("id") or "UNKNOWN_ID"
            question_text = item.get("question", "").strip()
            ex_zero_entries.append((str(question_id), question_text))

    if not ex_zero_entries:
        print("✅ Nenhum ground truth com EX = 0; arquivo não gerado")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"ex_zero_ground_truth_{timestamp}.txt"

    lines = ["Ground truths com EX = 0", "----------------------------------------"]
    for qid, question in ex_zero_entries:
        if question:
            lines.append(f"{qid} | {question} | EX = 0")
        else:
            lines.append(f"{qid} | EX = 0")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"⚠️  {len(ex_zero_entries)} ground truths com EX = 0")
    print(f"    Lista salva em: {output_path}")

    return output_path


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Run Text-to-SQL evaluation using DAG-based pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full evaluation
  python -m evaluation.runners.run_dag_evaluation

  # Run full evaluation with the revised ground truth
  python -m evaluation.runners.run_dag_evaluation --ground-truth evaluation/ground_truth_v2_revised.json

  # Run full evaluation with the revised ground truth and 4 workers
  python -m evaluation.runners.run_dag_evaluation --ground-truth evaluation/ground_truth_v2_revised.json --workers 4

  # Generate visualization only (no execution)
  python -m evaluation.runners.run_dag_evaluation --visualize-only

  # Run and save visualization
  python -m evaluation.runners.run_dag_evaluation --save-dag-visualization

  # Resume a crashed/interrupted run
  python -m evaluation.runners.run_dag_evaluation --resume-run-id 20260516_120000
        """,
    )

    parser.add_argument(
        "--visualize-only",
        action="store_true",
        help="Only generate DAG visualization without running evaluation",
    )

    parser.add_argument(
        "--save-dag-visualization",
        action="store_true",
        help="Save DAG visualization after execution",
    )

    parser.add_argument(
        "--dag-output",
        type=str,
        default="docs/evaluation_pipeline_dag.png",
        help="Path to save DAG visualization (default: docs/evaluation_pipeline_dag.png)",
    )

    parser.add_argument(
        "--ground-truth",
        "--dataset",
        dest="ground_truth_path",
        type=str,
        default="evaluation/ground_truth.json",
        help=(
            "Path to the ground-truth JSON file to evaluate. Relative paths are resolved "
            "from the project root. Default: evaluation/ground_truth.json"
        ),
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help=(
            "Use a fixed run id and output folder evaluation/results/dag_evaluation_<run-id>. "
            "By default a timestamp run id is generated."
        ),
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reuse completed per-query traces in the selected --run-id output folder.",
    )

    parser.add_argument(
        "--resume-run-id",
        type=str,
        default=None,
        help="Resume evaluation from evaluation/results/dag_evaluation_<run-id>.",
    )

    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore existing per-query traces and overwrite them as queries are re-evaluated.",
    )

    parser.add_argument(
        "--workers",
        "--max-workers",
        dest="max_workers",
        type=_positive_int,
        default=1,
        help=(
            "Number of worker threads for question evaluation. "
            "Use 1 for sequential mode. Default: 1"
        ),
    )

    parser.add_argument(
        "--llamaindex-mode",
        type=_llamaindex_mode,
        default=None,
        help=(
            "LlamaIndex mode for the agent inside the DAG: context, "
            "sql_draft, or hybrid. If omitted, LLAMAINDEX_MODE from .env is used "
            "when present; otherwise context."
        ),
    )

    parser.add_argument(
        "--llamaindex-top-k-tables",
        type=_positive_int,
        default=None,
        help="Number of schema tables to retrieve with LlamaIndex. Default: env or 6",
    )

    parser.add_argument(
        "--llamaindex-index-dir",
        type=str,
        default=None,
        help="Directory for the persisted LlamaIndex schema index. Default: env or .llamaindex_schema",
    )

    parser.add_argument(
        "--llamaindex-rebuild-index",
        action="store_true",
        help="Force rebuilding the LlamaIndex schema index before retrieval",
    )
    parser.add_argument(
        "--verify-llamaindex-schema-with-db",
        action="store_true",
        help="Call sql_db_schema to verify LlamaIndex schema context during evaluation",
    )

    return parser.parse_args()


def main():
    """Main entry point"""
    args = parse_arguments()

    print("\n" + "=" * 80)
    print("TEXT-TO-SQL EVALUATION - DAG-BASED PIPELINE")
    print("=" * 80 + "\n")

    try:
        # Create pipeline DAG
        print("Creating evaluation pipeline DAG...")
        dag = create_evaluation_pipeline()

        # Validate DAG structure
        if not dag.validate():
            print("❌ DAG validation failed - cannot proceed")
            sys.exit(1)

        print("✅ DAG created and validated successfully\n")

        # Print pipeline summary
        if args.verbose:
            dag.print_summary()

        # Visualize only mode
        if args.visualize_only:
            print(f"Generating visualization: {args.dag_output}")
            dag.visualize(output_path=args.dag_output, show_descriptions=True)
            print(f"✅ Visualization saved to: {args.dag_output}")
            print("\nNote: Use without --visualize-only to run evaluation")
            return

        if args.resume_run_id and args.run_id and args.resume_run_id != args.run_id:
            print("❌ Use either --run-id or --resume-run-id, or pass the same value to both")
            sys.exit(2)

        # Execute pipeline
        print("Starting pipeline execution...\n")
        print(f"Ground truth: {args.ground_truth_path}")
        print(f"Workers: {args.max_workers}\n")
        effective_llamaindex_mode = (
            args.llamaindex_mode or os.getenv("LLAMAINDEX_MODE") or "context"
        )
        print(f"LlamaIndex mode: {effective_llamaindex_mode}")
        if args.llamaindex_top_k_tables:
            print(f"LlamaIndex top-k tables: {args.llamaindex_top_k_tables}")
        if args.llamaindex_index_dir:
            print(f"LlamaIndex index dir: {args.llamaindex_index_dir}")
        if args.llamaindex_rebuild_index:
            print("LlamaIndex rebuild index: true")
        if args.verify_llamaindex_schema_with_db:
            print("Verify LlamaIndex schema with DB: true")
        print("")
        run_id = args.resume_run_id or args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        run_output_dir = project_root / "evaluation" / "results" / f"dag_evaluation_{run_id}"
        resume_enabled = bool(args.resume or args.resume_run_id)
        if args.resume_run_id and not run_output_dir.exists():
            print(f"❌ Cannot resume: output directory not found: {run_output_dir}")
            sys.exit(2)
        if args.run_id and run_output_dir.exists() and not resume_enabled and not args.force_rerun:
            print(f"❌ Output directory already exists: {run_output_dir}")
            print("   Use --resume to reuse completed traces, or --force-rerun to overwrite them.")
            sys.exit(2)
        run_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output directory: {run_output_dir}\n")
        if resume_enabled and not args.force_rerun:
            print(f"Resume: enabled (completed traces in {run_output_dir / 'queries'} will be reused)\n")
        elif args.force_rerun:
            print("Resume: disabled by --force-rerun\n")
        start_time = datetime.now()

        results = dag.execute(
            initial_data={
                "ground_truth_path": args.ground_truth_path,
                "max_workers": args.max_workers,
                "run_id": run_id,
                "output_dir": str(run_output_dir),
                "resume": resume_enabled,
                "resume_run_id": args.resume_run_id,
                "force_rerun": args.force_rerun,
                "llamaindex_mode": args.llamaindex_mode,
                "llamaindex_top_k_tables": args.llamaindex_top_k_tables,
                "llamaindex_index_dir": args.llamaindex_index_dir,
                "llamaindex_rebuild_index": args.llamaindex_rebuild_index,
                "verify_llamaindex_schema_with_db": args.verify_llamaindex_schema_with_db,
            }
        )

        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()

        # Check execution results
        successful_tasks = sum(1 for r in results.values() if r.success)
        failed_tasks = len(results) - successful_tasks

        print(f"\n{'=' * 80}")
        print("PIPELINE EXECUTION SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total time: {total_time:.2f}s ({total_time / 60:.1f} minutes)")
        print(f"Successful tasks: {successful_tasks}/{len(results)}")
        print(f"Failed tasks: {failed_tasks}/{len(results)}")

        if failed_tasks > 0:
            print("\n⚠️  Some tasks failed:")
            for task_name, result in results.items():
                if not result.success:
                    print(f"  - {task_name}: {result.error}")

        # Save DAG visualization if requested
        if args.save_dag_visualization:
            dag_output = Path(args.dag_output)
            if not dag_output.is_absolute():
                dag_output = run_output_dir / dag_output.name
            print(f"\nSaving DAG visualization: {dag_output}")
            dag.visualize(output_path=str(dag_output), show_descriptions=True)
            print("✅ DAG visualization saved")

        # Export ground truths com EX = 0
        export_ex_zero_failures(
            dag_results=results,
            output_dir=run_output_dir,
            run_id=run_id,
        )

        # Final status
        print(f"\n{'=' * 80}")
        if failed_tasks == 0:
            print("✅ EVALUATION COMPLETED SUCCESSFULLY")
            print(f"{'=' * 80}\n")

            # Print summary from save_results task
            if "save_results" in results and results["save_results"].success:
                save_data = results["save_results"].data
                print("📊 Results saved to:")
                print(f"   - Directory: {save_data['output_dir']}")
                print(f"   - JSON: {save_data['json_path']}")
                print(f"   - Report: {save_data['report_path']}")
                print(f"   - Trace: {save_data['trace_path']}")
                print(f"   - Analysis: {save_data['analysis_path']}")

        else:
            print("⚠️  EVALUATION COMPLETED WITH ERRORS")
            print(f"{'=' * 80}\n")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️  Evaluation interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
