"""
Evaluation functions for Transcript-to-Jira Agent.

This module contains code-based and LLM-as-judge evaluators to assess
the quality of generated Jira tickets. Designed to integrate with Arize AX.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import json


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class EvaluationResult:
    """Result from a single evaluation."""
    metric_name: str
    score: float  # 0-1 for binary, 1-5 for LLM judges, 0-100 for percentages
    passed: bool
    reasoning: str
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "score": self.score,
            "passed": self.passed,
            "reasoning": self.reasoning,
            "metadata": self.metadata or {}
        }


@dataclass
class TicketEvaluation:
    """Complete evaluation results for a transcript analysis."""
    code_based: List[EvaluationResult]
    llm_judge: List[EvaluationResult]
    overall_score: float
    production_ready: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code_based": [e.to_dict() for e in self.code_based],
            "llm_judge": [e.to_dict() for e in self.llm_judge],
            "overall_score": self.overall_score,
            "production_ready": self.production_ready
        }


# ============================================================================
# CODE-BASED EVALUATORS
# ============================================================================

def evaluate_completeness(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Evaluate ticket completeness (required fields populated)."""
    required_fields = ["title", "type", "priority", "effort", "description"]
    
    total_fields = 0
    populated_fields = 0
    
    for ticket in tickets:
        for field in required_fields:
            total_fields += 1
            value = ticket.get(field)
            if value and str(value).strip():
                populated_fields += 1
    
    score = (populated_fields / total_fields * 100) if total_fields > 0 else 0
    passed = score >= 80
    
    return EvaluationResult(
        metric_name="completeness_score",
        score=score,
        passed=passed,
        reasoning=f"{populated_fields}/{total_fields} required fields populated ({score:.1f}%)",
        metadata={"required_fields": required_fields}
    )


def evaluate_priority_format(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Validate priority format (P0, P1, P2, P3)."""
    valid_pattern = re.compile(r'^P[0-3]$')
    
    total = len(tickets)
    valid_count = 0
    invalid_priorities = []
    
    for ticket in tickets:
        priority = ticket.get("priority", "")
        if valid_pattern.match(priority):
            valid_count += 1
        else:
            invalid_priorities.append(f"{ticket.get('title', 'Unknown')}: {priority}")
    
    passed = valid_count == total
    
    return EvaluationResult(
        metric_name="priority_format_valid",
        score=1.0 if passed else 0.0,
        passed=passed,
        reasoning=f"{valid_count}/{total} tickets have valid priority format" + 
                  (f". Invalid: {', '.join(invalid_priorities[:3])}" if invalid_priorities else ""),
        metadata={"invalid_priorities": invalid_priorities}
    )


def evaluate_ticket_type(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Validate ticket type (Bug, Story, Task, Epic)."""
    valid_types = {"Bug", "Story", "Task", "Epic"}
    
    total = len(tickets)
    valid_count = 0
    invalid_types = []
    
    for ticket in tickets:
        ticket_type = ticket.get("type", "")
        if ticket_type in valid_types:
            valid_count += 1
        else:
            invalid_types.append(f"{ticket.get('title', 'Unknown')}: {ticket_type}")
    
    passed = valid_count == total
    
    return EvaluationResult(
        metric_name="ticket_type_valid",
        score=1.0 if passed else 0.0,
        passed=passed,
        reasoning=f"{valid_count}/{total} tickets have valid type" +
                  (f". Invalid: {', '.join(invalid_types[:3])}" if invalid_types else ""),
        metadata={"valid_types": list(valid_types), "invalid_types": invalid_types}
    )


def evaluate_effort_format(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Validate effort format (S, M, L, XL)."""
    valid_efforts = {"S", "M", "L", "XL"}
    
    total = len(tickets)
    valid_count = 0
    invalid_efforts = []
    
    for ticket in tickets:
        effort = ticket.get("effort", "")
        if effort in valid_efforts:
            valid_count += 1
        else:
            invalid_efforts.append(f"{ticket.get('title', 'Unknown')}: {effort}")
    
    passed = valid_count == total
    
    return EvaluationResult(
        metric_name="effort_format_valid",
        score=1.0 if passed else 0.0,
        passed=passed,
        reasoning=f"{valid_count}/{total} tickets have valid effort format" +
                  (f". Invalid: {', '.join(invalid_efforts[:3])}" if invalid_efforts else ""),
        metadata={"valid_efforts": list(valid_efforts), "invalid_efforts": invalid_efforts}
    )


def evaluate_description_length(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Evaluate description length (should be meaningful but not too long)."""
    min_length = 50
    max_length = 2000
    warn_length = 20
    
    issues = []
    too_short = 0
    too_long = 0
    good_count = 0
    
    for ticket in tickets:
        desc = ticket.get("description", "")
        length = len(desc)
        
        if length < warn_length:
            issues.append(f"{ticket.get('title', 'Unknown')}: Too vague ({length} chars)")
            too_short += 1
        elif length < min_length:
            issues.append(f"{ticket.get('title', 'Unknown')}: Short ({length} chars)")
            too_short += 1
        elif length > max_length:
            issues.append(f"{ticket.get('title', 'Unknown')}: Too long ({length} chars)")
            too_long += 1
        else:
            good_count += 1
    
    total = len(tickets)
    passed = too_short == 0  # Fail if any are critically short
    
    return EvaluationResult(
        metric_name="description_length_valid",
        score=good_count / total if total > 0 else 0,
        passed=passed,
        reasoning=f"{good_count}/{total} descriptions are appropriate length" +
                  (f". Issues: {', '.join(issues[:3])}" if issues else ""),
        metadata={
            "min_length": min_length,
            "max_length": max_length,
            "too_short": too_short,
            "too_long": too_long
        }
    )


def evaluate_label_count(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Evaluate label assignment (should have at least 2 labels per ticket)."""
    min_labels = 2
    
    total = len(tickets)
    sufficient_count = 0
    issues = []
    
    for ticket in tickets:
        labels = ticket.get("labels", [])
        label_count = len(labels)
        
        if label_count >= min_labels:
            sufficient_count += 1
        else:
            issues.append(f"{ticket.get('title', 'Unknown')}: Only {label_count} label(s)")
    
    passed = sufficient_count == total
    
    return EvaluationResult(
        metric_name="label_count_sufficient",
        score=sufficient_count / total if total > 0 else 0,
        passed=passed,
        reasoning=f"{sufficient_count}/{total} tickets have ≥{min_labels} labels" +
                  (f". Issues: {', '.join(issues[:3])}" if issues else ""),
        metadata={"min_labels": min_labels, "issues": issues}
    )


def evaluate_priority_effort_consistency(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Check consistency between priority and effort."""
    inconsistencies = []
    
    for ticket in tickets:
        priority = ticket.get("priority", "")
        effort = ticket.get("effort", "")
        title = ticket.get("title", "Unknown")
        
        # P0/P1 with Small effort is suspicious (likely underestimated)
        if priority in ["P0", "P1"] and effort == "S":
            inconsistencies.append(f"{title}: {priority} + S effort (likely underestimated)")
        
        # P3 with XL effort is suspicious (why low priority if so much work?)
        if priority == "P3" and effort == "XL":
            inconsistencies.append(f"{title}: P3 + XL effort (why low priority for large work?)")
    
    total = len(tickets)
    consistent_count = total - len(inconsistencies)
    passed = len(inconsistencies) == 0
    
    return EvaluationResult(
        metric_name="priority_effort_consistent",
        score=consistent_count / total if total > 0 else 1.0,
        passed=passed,
        reasoning=f"{consistent_count}/{total} tickets have consistent priority-effort pairing" +
                  (f". Inconsistencies: {', '.join(inconsistencies[:3])}" if inconsistencies else ""),
        metadata={"inconsistencies": inconsistencies}
    )


def evaluate_bug_priority_baseline(tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """Check if bugs have appropriate priority (not P3)."""
    issues = []
    
    for ticket in tickets:
        ticket_type = ticket.get("type", "")
        priority = ticket.get("priority", "")
        title = ticket.get("title", "Unknown")
        
        # Bugs should typically not be P3 (lowest priority)
        if ticket_type == "Bug" and priority == "P3":
            issues.append(f"{title}: Bug marked as P3 (usually should be higher)")
    
    bugs = [t for t in tickets if t.get("type") == "Bug"]
    appropriate_count = len(bugs) - len(issues)
    passed = len(issues) == 0
    
    return EvaluationResult(
        metric_name="bug_priority_appropriate",
        score=appropriate_count / len(bugs) if bugs else 1.0,
        passed=passed,
        reasoning=f"{appropriate_count}/{len(bugs)} bugs have appropriate priority" +
                  (f". Issues: {', '.join(issues[:3])}" if issues else "") if bugs else "No bugs to evaluate",
        metadata={"issues": issues, "bug_count": len(bugs)}
    )


def evaluate_tool_call_efficiency(tool_calls: List[Dict[str, Any]], ticket_count: int) -> EvaluationResult:
    """Evaluate tool call efficiency (4-8 calls per ticket is reasonable)."""
    total_calls = len(tool_calls)
    calls_per_ticket = total_calls / ticket_count if ticket_count > 0 else 0
    
    min_expected = 4
    max_expected = 8
    
    if calls_per_ticket < min_expected:
        status = "Too few tool calls - likely incomplete analysis"
        passed = False
    elif calls_per_ticket > max_expected:
        status = "Too many tool calls - inefficient"
        passed = False
    else:
        status = "Efficient tool usage"
        passed = True
    
    return EvaluationResult(
        metric_name="tool_call_efficiency",
        score=calls_per_ticket,
        passed=passed,
        reasoning=f"{total_calls} tool calls for {ticket_count} tickets = {calls_per_ticket:.1f} calls/ticket. {status}",
        metadata={
            "total_calls": total_calls,
            "ticket_count": ticket_count,
            "calls_per_ticket": calls_per_ticket,
            "expected_range": [min_expected, max_expected]
        }
    )


# ============================================================================
# LLM-AS-JUDGE EVALUATORS
# ============================================================================

def build_llm_judge_prompt(evaluator_name: str, inputs: Dict[str, Any]) -> str:
    """Build prompt for LLM-as-judge evaluations."""
    
    prompts = {
        "description_clarity": """Role: You are evaluating the clarity of a Jira ticket description.

Input:
- Transcript excerpt: "{transcript}"
- Generated description: "{description}"

Task: Rate the clarity of the description on a scale of 1-5:
1 = Very unclear, missing key details
2 = Somewhat unclear, vague language
3 = Adequate clarity, basic details present
4 = Clear and detailed
5 = Exceptionally clear, all context included

Output format (JSON):
{{"score": <1-5>, "reasoning": "<one sentence explanation>"}}""",

        "priority_appropriateness": """Role: You are evaluating whether the assigned priority matches the urgency and impact described in the transcript.

Input:
- Transcript excerpt: "{transcript}"
- Assigned priority: "{priority}"
- Ticket type: "{type}"

Context:
- P0: Critical, blocks release, affects all users
- P1: High priority, significant impact, deadline mentioned
- P2: Medium priority, normal workflow
- P3: Low priority, nice-to-have, no urgency

Task: Rate appropriateness on a scale of 1-5:
1 = Very inappropriate (e.g., P3 for critical bug)
2 = Somewhat inappropriate
3 = Reasonable but could be adjusted
4 = Appropriate
5 = Perfectly appropriate

Output format (JSON):
{{"score": <1-5>, "reasoning": "<one sentence explanation>", "suggested_priority": "<P0-P3 or 'Correct'>"}}""",

        "action_completeness": """Role: You are evaluating whether all action items from a meeting transcript were captured as tickets.

Input:
- Full transcript: "{transcript}"
- Generated tickets: {tickets}

Task: 
1. Identify all action items mentioned in the transcript
2. Check if each is represented in the generated tickets
3. Rate completeness on a scale of 1-5:
   1 = Missed most action items (< 50%)
   2 = Missed some important items (50-70%)
   3 = Captured most items (70-85%)
   4 = Captured nearly all items (85-95%)
   5 = Captured all action items (95-100%)

Output format (JSON):
{{"score": <1-5>, "reasoning": "<list any missed items>", "missing_items": ["<item 1>", "<item 2>"] or []}}""",

        "label_relevance": """Role: You are evaluating whether the labels assigned to a ticket are relevant and helpful.

Input:
- Ticket title: "{title}"
- Ticket description: "{description}"
- Assigned labels: {labels}

Task: Rate the relevance of the labels on a scale of 1-5:
1 = Labels are irrelevant or misleading
2 = Some labels are relevant, others are not
3 = Labels are generally relevant but generic
4 = Labels are relevant and specific
5 = Labels are highly relevant, specific, and actionable

Consider:
- Do labels help categorize the ticket?
- Are labels specific enough to be useful for filtering?
- Are there obvious missing labels?

Output format (JSON):
{{"score": <1-5>, "reasoning": "<one sentence explanation>", "suggested_additions": ["<label 1>"] or []}}""",

        "component_accuracy": """Role: You are evaluating whether the assigned component is correct for the ticket.

Input:
- Ticket title: "{title}"
- Ticket description: "{description}"
- Assigned component: "{component}"

Common components: Frontend, Backend, Infrastructure, Database, API, Mobile, DevOps

Task: Rate the accuracy of the component assignment on a scale of 1-5:
1 = Wrong component
2 = Likely wrong, should be different
3 = Could be correct, but uncertain
4 = Correct component
5 = Definitely correct component

If no component is assigned, rate as 3 (neutral).

Output format (JSON):
{{"score": <1-5>, "reasoning": "<one sentence explanation>", "suggested_component": "<component or 'Correct'>"}}""",

        "overall_quality": """Role: You are a senior product manager reviewing AI-generated Jira tickets for quality.

Input:
- Original transcript excerpt: "{transcript}"
- Generated ticket: {ticket}

Task: Provide an overall quality score on a scale of 1-5:
1 = Unusable, would require complete rewrite
2 = Poor quality, significant edits needed
3 = Acceptable quality, minor edits needed
4 = Good quality, ready to use with minimal changes
5 = Excellent quality, production-ready as-is

Consider:
- Clarity of title and description
- Appropriateness of type, priority, and effort
- Usefulness of labels and component
- Completeness of information
- Actionability for development team

Output format (JSON):
{{"score": <1-5>, "reasoning": "<2-3 sentences>", "production_ready": <true/false>}}"""
    }
    
    template = prompts.get(evaluator_name, "")
    return template.format(**inputs)


def parse_llm_judge_response(response: str) -> Dict[str, Any]:
    """Parse LLM judge response (expects JSON)."""
    try:
        # Try to extract JSON from response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            return json.loads(json_str)
        return {"error": "No JSON found in response"}
    except json.JSONDecodeError:
        return {"error": "Invalid JSON in response", "raw": response}


def llm_judge_description_clarity(llm, transcript: str, ticket: Dict[str, Any]) -> EvaluationResult:
    """LLM-as-judge: Evaluate description clarity."""
    prompt = build_llm_judge_prompt("description_clarity", {
        "transcript": transcript[:500],  # Limit length
        "description": ticket.get("description", "")
    })
    
    # In real implementation, call your LLM here
    # response = llm.invoke(prompt)
    # result = parse_llm_judge_response(response)
    
    # Placeholder for demonstration
    result = {"score": 4, "reasoning": "Clear and detailed description"}
    
    score = result.get("score", 3)
    passed = score >= 3.5
    
    return EvaluationResult(
        metric_name="description_clarity",
        score=score,
        passed=passed,
        reasoning=result.get("reasoning", "No reasoning provided"),
        metadata=result
    )


def llm_judge_priority_appropriateness(llm, transcript: str, ticket: Dict[str, Any]) -> EvaluationResult:
    """LLM-as-judge: Evaluate priority appropriateness."""
    prompt = build_llm_judge_prompt("priority_appropriateness", {
        "transcript": transcript[:500],
        "priority": ticket.get("priority", ""),
        "type": ticket.get("type", "")
    })
    
    # Placeholder
    result = {"score": 4, "reasoning": "Priority matches urgency", "suggested_priority": "Correct"}
    
    score = result.get("score", 3)
    passed = score >= 4.0
    
    return EvaluationResult(
        metric_name="priority_appropriateness",
        score=score,
        passed=passed,
        reasoning=result.get("reasoning", "No reasoning provided"),
        metadata=result
    )


def llm_judge_action_completeness(llm, transcript: str, tickets: List[Dict[str, Any]]) -> EvaluationResult:
    """LLM-as-judge: Evaluate action item completeness."""
    prompt = build_llm_judge_prompt("action_completeness", {
        "transcript": transcript,
        "tickets": json.dumps([{"title": t["title"], "type": t["type"]} for t in tickets], indent=2)
    })
    
    # Placeholder
    result = {"score": 4, "reasoning": "Most action items captured", "missing_items": []}
    
    score = result.get("score", 3)
    passed = score >= 4.0
    
    return EvaluationResult(
        metric_name="action_completeness",
        score=score,
        passed=passed,
        reasoning=result.get("reasoning", "No reasoning provided"),
        metadata=result
    )


def llm_judge_overall_quality(llm, transcript: str, ticket: Dict[str, Any]) -> EvaluationResult:
    """LLM-as-judge: Evaluate overall ticket quality."""
    prompt = build_llm_judge_prompt("overall_quality", {
        "transcript": transcript[:500],
        "ticket": json.dumps(ticket, indent=2)
    })
    
    # Placeholder
    result = {
        "score": 4,
        "reasoning": "Good quality ticket, ready to use with minimal changes",
        "production_ready": True
    }
    
    score = result.get("score", 3)
    passed = score >= 3.5
    
    return EvaluationResult(
        metric_name="overall_quality",
        score=score,
        passed=passed,
        reasoning=result.get("reasoning", "No reasoning provided"),
        metadata=result
    )


# ============================================================================
# COMBINED EVALUATION PIPELINE
# ============================================================================

def run_code_based_evaluations(
    tickets: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]]
) -> List[EvaluationResult]:
    """Run all code-based evaluations."""
    results = []
    
    # Completeness and format
    results.append(evaluate_completeness(tickets))
    results.append(evaluate_priority_format(tickets))
    results.append(evaluate_ticket_type(tickets))
    results.append(evaluate_effort_format(tickets))
    results.append(evaluate_description_length(tickets))
    results.append(evaluate_label_count(tickets))
    
    # Consistency checks
    results.append(evaluate_priority_effort_consistency(tickets))
    results.append(evaluate_bug_priority_baseline(tickets))
    
    # Efficiency
    results.append(evaluate_tool_call_efficiency(tool_calls, len(tickets)))
    
    return results


def run_llm_judge_evaluations(
    llm,
    transcript: str,
    tickets: List[Dict[str, Any]]
) -> List[EvaluationResult]:
    """Run all LLM-as-judge evaluations."""
    results = []
    
    # Per-ticket evaluations
    for ticket in tickets:
        results.append(llm_judge_description_clarity(llm, transcript, ticket))
        results.append(llm_judge_priority_appropriateness(llm, transcript, ticket))
        results.append(llm_judge_overall_quality(llm, transcript, ticket))
    
    # Overall evaluations
    results.append(llm_judge_action_completeness(llm, transcript, tickets))
    
    return results


def evaluate_transcript_response(
    transcript: str,
    tickets: List[Dict[str, Any]],
    tool_calls: List[Dict[str, Any]],
    llm = None
) -> TicketEvaluation:
    """
    Run complete evaluation pipeline on a transcript analysis result.
    
    Args:
        transcript: Original meeting transcript
        tickets: Generated Jira tickets
        tool_calls: List of tool calls made during generation
        llm: Language model for LLM-as-judge evaluations (optional)
    
    Returns:
        TicketEvaluation with all results
    """
    # Run code-based evaluations
    code_based = run_code_based_evaluations(tickets, tool_calls)
    
    # Run LLM-as-judge evaluations (if LLM provided)
    llm_judge = []
    if llm:
        llm_judge = run_llm_judge_evaluations(llm, transcript, tickets)
    
    # Calculate overall score (weighted average)
    code_scores = [r.score for r in code_based if isinstance(r.score, (int, float))]
    llm_scores = [r.score for r in llm_judge if isinstance(r.score, (int, float))]
    
    # Normalize scores to 0-5 scale
    normalized_code = [s if s <= 5 else s / 20 for s in code_scores]  # Convert percentages
    normalized_llm = llm_scores  # Already 1-5
    
    all_scores = normalized_code + normalized_llm
    overall_score = sum(all_scores) / len(all_scores) if all_scores else 3.0
    
    # Determine production readiness
    critical_passed = all(r.passed for r in code_based if "format" in r.metric_name or "completeness" in r.metric_name)
    quality_passed = overall_score >= 3.5
    production_ready = critical_passed and quality_passed
    
    return TicketEvaluation(
        code_based=code_based,
        llm_judge=llm_judge,
        overall_score=overall_score,
        production_ready=production_ready
    )


# ============================================================================
# ARIZE INTEGRATION
# ============================================================================

def log_evaluations_to_arize(evaluation: TicketEvaluation, span=None):
    """Log evaluation results as span attributes in Arize."""
    if not span:
        return
    
    # Log code-based evaluations
    for result in evaluation.code_based:
        span.set_attribute(f"eval.{result.metric_name}.score", result.score)
        span.set_attribute(f"eval.{result.metric_name}.passed", result.passed)
    
    # Log LLM-judge evaluations
    for result in evaluation.llm_judge:
        span.set_attribute(f"eval.{result.metric_name}.score", result.score)
        span.set_attribute(f"eval.{result.metric_name}.passed", result.passed)
    
    # Log overall metrics
    span.set_attribute("eval.overall_score", evaluation.overall_score)
    span.set_attribute("eval.production_ready", evaluation.production_ready)
    
    # Count passes/fails
    total_checks = len(evaluation.code_based) + len(evaluation.llm_judge)
    passed_checks = sum(1 for r in evaluation.code_based + evaluation.llm_judge if r.passed)
    span.set_attribute("eval.pass_rate", passed_checks / total_checks if total_checks > 0 else 0)


if __name__ == "__main__":
    # Example usage
    sample_tickets = [
        {
            "title": "Fix dark mode bug",
            "type": "Bug",
            "priority": "P1",
            "effort": "M",
            "description": "The dark mode toggle is not working properly on the settings page. Users report that clicking the toggle does nothing.",
            "labels": ["bug", "ui", "dark-mode"],
            "component": "Frontend"
        }
    ]
    
    sample_tool_calls = [
        {"agent": "transcript_analysis", "tool": "extract_action_items"},
        {"agent": "transcript_analysis", "tool": "identify_ticket_type"},
        {"agent": "priority", "tool": "calculate_priority_score"},
        {"agent": "priority", "tool": "estimate_effort"},
        {"agent": "context_enrichment", "tool": "add_labels"},
    ]
    
    sample_transcript = "Meeting: The dark mode feature is broken. Users are complaining. We need to fix this ASAP."
    
    # Run evaluations
    evaluation = evaluate_transcript_response(
        transcript=sample_transcript,
        tickets=sample_tickets,
        tool_calls=sample_tool_calls,
        llm=None  # Would pass actual LLM for judge evaluations
    )
    
    print("Evaluation Results:")
    print(f"Overall Score: {evaluation.overall_score:.2f}/5.0")
    print(f"Production Ready: {evaluation.production_ready}")
    print(f"\nCode-Based Results:")
    for result in evaluation.code_based:
        status = "✅" if result.passed else "❌"
        print(f"  {status} {result.metric_name}: {result.score:.2f} - {result.reasoning}")

