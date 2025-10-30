"""
Run evaluations on the Transcript-to-Jira Agent using the golden dataset.

This script loads the golden evaluation dataset, runs the agent on each sample,
and evaluates the results using both code-based and LLM-as-judge metrics.
"""

import json
import os
import sys
from typing import Dict, Any, List
from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from evaluators import (
    evaluate_transcript_response,
    log_evaluations_to_arize,
    EvaluationResult,
    TicketEvaluation
)

# Load environment variables
load_dotenv()


def load_golden_dataset(path: str = "data/evaluation_golden_dataset.json") -> List[Dict[str, Any]]:
    """Load the golden evaluation dataset."""
    with open(path, 'r') as f:
        return json.load(f)


def run_agent_on_transcript(transcript: str) -> Dict[str, Any]:
    """
    Run the transcript-to-jira agent on a transcript.
    Returns generated tickets and tool calls.
    
    This would call your actual agent in production.
    For now, it's a placeholder that you'd replace with actual agent invocation.
    """
    # Placeholder - in reality, you'd call:
    # from main import build_graph, _init_llm
    # graph = build_graph()
    # state = {"transcript_request": {"transcript": transcript, ...}, ...}
    # result = graph.invoke(state)
    
    # For demonstration, return mock results
    return {
        "tickets": [
            {
                "title": "Example ticket from transcript",
                "type": "Task",
                "priority": "P2",
                "effort": "M",
                "description": "This is an example ticket.",
                "labels": ["example", "test"],
                "component": "Backend"
            }
        ],
        "tool_calls": [
            {"agent": "transcript_analysis", "tool": "extract_action_items"},
            {"agent": "priority", "tool": "calculate_priority_score"},
        ]
    }


def compare_to_ground_truth(
    generated_tickets: List[Dict[str, Any]],
    expected_tickets: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare generated tickets to ground truth.
    
    Returns metrics like:
    - Ticket count match
    - Type accuracy
    - Priority accuracy
    - Field completeness
    """
    metrics = {}
    
    # Ticket count accuracy
    gen_count = len(generated_tickets)
    exp_count = len(expected_tickets)
    metrics["count_match"] = gen_count == exp_count
    metrics["count_difference"] = abs(gen_count - exp_count)
    
    # If counts match, compare individual tickets
    if gen_count == exp_count and gen_count > 0:
        type_matches = 0
        priority_matches = 0
        effort_matches = 0
        
        for gen, exp in zip(generated_tickets, expected_tickets):
            if gen.get("type") == exp.get("type"):
                type_matches += 1
            if gen.get("priority") == exp.get("priority"):
                priority_matches += 1
            if gen.get("effort") == exp.get("effort"):
                effort_matches += 1
        
        metrics["type_accuracy"] = type_matches / gen_count
        metrics["priority_accuracy"] = priority_matches / gen_count
        metrics["effort_accuracy"] = effort_matches / gen_count
    else:
        metrics["type_accuracy"] = 0
        metrics["priority_accuracy"] = 0
        metrics["effort_accuracy"] = 0
    
    return metrics


def run_evaluation_on_dataset(
    dataset: List[Dict[str, Any]],
    use_llm_judges: bool = False,
    limit: int = None
) -> Dict[str, Any]:
    """
    Run evaluations on all samples in the dataset.
    
    Args:
        dataset: List of evaluation samples
        use_llm_judges: Whether to run LLM-as-judge evaluations (requires API calls)
        limit: Optionally limit to first N samples
    
    Returns:
        Aggregated evaluation results
    """
    if limit:
        dataset = dataset[:limit]
    
    all_results = []
    ground_truth_comparisons = []
    
    print(f"Running evaluations on {len(dataset)} samples...")
    print("=" * 80)
    
    for i, sample in enumerate(dataset):
        sample_id = sample["id"]
        transcript = sample["transcript"]
        expected_tickets = sample.get("expected_tickets", [])
        
        print(f"\n[{i+1}/{len(dataset)}] Evaluating {sample_id}: {sample['name']}")
        print(f"Transcript: {transcript[:100]}...")
        
        # Run agent
        try:
            agent_result = run_agent_on_transcript(transcript)
            generated_tickets = agent_result["tickets"]
            tool_calls = agent_result.get("tool_calls", [])
            
            print(f"Generated {len(generated_tickets)} ticket(s)")
            
            # Run evaluations
            llm = None  # Would pass actual LLM if use_llm_judges=True
            evaluation = evaluate_transcript_response(
                transcript=transcript,
                tickets=generated_tickets,
                tool_calls=tool_calls,
                llm=llm
            )
            
            # Compare to ground truth
            if expected_tickets:
                ground_truth = compare_to_ground_truth(generated_tickets, expected_tickets)
                ground_truth_comparisons.append(ground_truth)
                
                print(f"Ground Truth Comparison:")
                print(f"  Ticket count: {len(generated_tickets)} (expected {len(expected_tickets)})")
                if ground_truth["count_match"]:
                    print(f"  Type accuracy: {ground_truth['type_accuracy']:.1%}")
                    print(f"  Priority accuracy: {ground_truth['priority_accuracy']:.1%}")
                    print(f"  Effort accuracy: {ground_truth['effort_accuracy']:.1%}")
            
            # Print evaluation summary
            print(f"\nEvaluation Results:")
            print(f"  Overall Score: {evaluation.overall_score:.2f}/5.0")
            print(f"  Production Ready: {'✅ Yes' if evaluation.production_ready else '❌ No'}")
            
            # Show failed checks
            failed_checks = [r for r in evaluation.code_based if not r.passed]
            if failed_checks:
                print(f"  Failed Checks ({len(failed_checks)}):")
                for check in failed_checks:
                    print(f"    ❌ {check.metric_name}: {check.reasoning}")
            else:
                print(f"  ✅ All code-based checks passed!")
            
            all_results.append({
                "sample_id": sample_id,
                "evaluation": evaluation,
                "ground_truth": ground_truth if expected_tickets else None
            })
            
        except Exception as e:
            print(f"ERROR: Failed to evaluate {sample_id}: {e}")
            continue
    
    # Aggregate results
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)
    
    if all_results:
        avg_overall_score = sum(r["evaluation"].overall_score for r in all_results) / len(all_results)
        production_ready_count = sum(1 for r in all_results if r["evaluation"].production_ready)
        production_ready_rate = production_ready_count / len(all_results)
        
        print(f"\nOverall Performance:")
        print(f"  Average Overall Score: {avg_overall_score:.2f}/5.0")
        print(f"  Production Ready Rate: {production_ready_rate:.1%} ({production_ready_count}/{len(all_results)})")
        
        # Aggregate ground truth metrics
        if ground_truth_comparisons:
            avg_type_accuracy = sum(gt["type_accuracy"] for gt in ground_truth_comparisons) / len(ground_truth_comparisons)
            avg_priority_accuracy = sum(gt["priority_accuracy"] for gt in ground_truth_comparisons) / len(ground_truth_comparisons)
            avg_effort_accuracy = sum(gt["effort_accuracy"] for gt in ground_truth_comparisons) / len(ground_truth_comparisons)
            count_matches = sum(1 for gt in ground_truth_comparisons if gt["count_match"])
            
            print(f"\nGround Truth Accuracy:")
            print(f"  Ticket Count Match: {count_matches}/{len(ground_truth_comparisons)} ({count_matches/len(ground_truth_comparisons):.1%})")
            print(f"  Average Type Accuracy: {avg_type_accuracy:.1%}")
            print(f"  Average Priority Accuracy: {avg_priority_accuracy:.1%}")
            print(f"  Average Effort Accuracy: {avg_effort_accuracy:.1%}")
        
        # Aggregate code-based metrics
        print(f"\nCode-Based Metric Performance:")
        metric_pass_rates = {}
        for result in all_results:
            for eval_result in result["evaluation"].code_based:
                metric_name = eval_result.metric_name
                if metric_name not in metric_pass_rates:
                    metric_pass_rates[metric_name] = []
                metric_pass_rates[metric_name].append(1 if eval_result.passed else 0)
        
        for metric_name, passes in sorted(metric_pass_rates.items()):
            pass_rate = sum(passes) / len(passes)
            status = "✅" if pass_rate >= 0.9 else "⚠️" if pass_rate >= 0.7 else "❌"
            print(f"  {status} {metric_name}: {pass_rate:.1%}")
    
    return {
        "results": all_results,
        "aggregate": {
            "avg_overall_score": avg_overall_score if all_results else 0,
            "production_ready_rate": production_ready_rate if all_results else 0,
            "total_samples": len(all_results)
        }
    }


def main():
    """Main evaluation runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run evaluations on Transcript-to-Jira Agent")
    parser.add_argument("--dataset", default="data/evaluation_golden_dataset.json", help="Path to golden dataset")
    parser.add_argument("--limit", type=int, help="Limit number of samples to evaluate")
    parser.add_argument("--use-llm-judges", action="store_true", help="Enable LLM-as-judge evaluations (requires API calls)")
    parser.add_argument("--output", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Load dataset
    try:
        dataset = load_golden_dataset(args.dataset)
        print(f"Loaded {len(dataset)} evaluation samples from {args.dataset}")
    except FileNotFoundError:
        print(f"ERROR: Dataset file not found: {args.dataset}")
        print(f"Current directory: {os.getcwd()}")
        return
    
    # Run evaluations
    results = run_evaluation_on_dataset(
        dataset=dataset,
        use_llm_judges=args.use_llm_judges,
        limit=args.limit
    )
    
    # Save results if requested
    if args.output:
        with open(args.output, 'w') as f:
            # Convert to JSON-serializable format
            output_data = {
                "aggregate": results["aggregate"],
                "samples": [
                    {
                        "sample_id": r["sample_id"],
                        "overall_score": r["evaluation"].overall_score,
                        "production_ready": r["evaluation"].production_ready,
                        "ground_truth": r["ground_truth"]
                    }
                    for r in results["results"]
                ]
            }
            json.dump(output_data, f, indent=2)
        print(f"\n✅ Results saved to {args.output}")
    
    print("\n" + "=" * 80)
    print("Evaluation complete!")
    print("\nNext steps:")
    print("1. Review failed samples and identify patterns")
    print("2. Adjust agent prompts to address common failures")
    print("3. Re-run evaluations to measure improvement")
    print("4. Set up Arize monitoring for production")


if __name__ == "__main__":
    main()

