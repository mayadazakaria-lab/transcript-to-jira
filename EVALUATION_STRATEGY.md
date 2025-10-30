# Transcript-to-Jira Agent - Evaluation Strategy

## Overview
This document outlines code-based and LLM-as-a-judge evaluations for the Transcript-to-Jira Agent, designed to be tracked in Arize AX for continuous monitoring and improvement.

---

## 1. Code-Based Evaluations (Deterministic)

These are rule-based metrics that check structural correctness and completeness.

### 1.1 Completeness Metrics

**Metric: `ticket_completeness_score`**
- **What it measures**: Percentage of required fields populated
- **Formula**: (populated_fields / total_required_fields) * 100
- **Required fields**: title, type, priority, effort, description
- **Threshold**: ≥ 80% (fail if below)

**Metric: `action_item_extraction_rate`**
- **What it measures**: Number of action items found vs expected
- **Formula**: extracted_items / expected_items (from ground truth)
- **Threshold**: ≥ 90% (fail if below)

**Metric: `label_count`**
- **What it measures**: Number of labels assigned per ticket
- **Threshold**: ≥ 2 labels per ticket (warn if below)

### 1.2 Format Validation Metrics

**Metric: `priority_format_valid`**
- **What it measures**: Priority follows P0/P1/P2/P3 format
- **Validation**: Must match regex `^P[0-3]$`
- **Threshold**: 100% (fail if invalid)

**Metric: `ticket_type_valid`**
- **What it measures**: Type is one of allowed values
- **Allowed values**: Bug, Story, Task, Epic
- **Threshold**: 100% (fail if invalid)

**Metric: `effort_format_valid`**
- **What it measures**: Effort follows S/M/L/XL format
- **Allowed values**: S, M, L, XL
- **Threshold**: 100% (fail if invalid)

**Metric: `description_length`**
- **What it measures**: Description is not too short or too long
- **Threshold**: 50 ≤ length ≤ 2000 characters
- **Fail**: < 20 characters (too vague)

### 1.3 Consistency Metrics

**Metric: `priority_effort_consistency`**
- **What it measures**: High-priority tickets should have appropriate effort
- **Logic**: P0/P1 tickets shouldn't be "S" effort (likely mis-estimated)
- **Threshold**: Warn on P0+S or P1+S combinations

**Metric: `bug_priority_baseline`**
- **What it measures**: Bugs should typically be higher priority
- **Logic**: Bugs marked as P3 are likely incorrect
- **Threshold**: Warn if Bug + P3

**Metric: `tool_call_efficiency`**
- **What it measures**: Number of tool calls per ticket
- **Expected range**: 4-8 calls per ticket
- **Threshold**: Warn if > 10 (inefficient) or < 3 (incomplete)

---

## 2. LLM-as-a-Judge Evaluations (Semantic)

These use an LLM to evaluate quality aspects that require understanding context.

### 2.1 Description Quality

**Evaluator: `description_clarity_judge`**
```
Role: You are evaluating the clarity of a Jira ticket description.

Input:
- Transcript excerpt: "{transcript}"
- Generated description: "{description}"

Task: Rate the clarity of the description on a scale of 1-5:
1 = Very unclear, missing key details
2 = Somewhat unclear, vague language
3 = Adequate clarity, basic details present
4 = Clear and detailed
5 = Exceptionally clear, all context included

Output format:
Score: [1-5]
Reasoning: [One sentence explanation]
```

**Metric: `description_clarity_score`**
- **Threshold**: ≥ 3.5 average (warn if below)
- **Track in Arize**: Distribution over time

### 2.2 Priority Appropriateness

**Evaluator: `priority_appropriateness_judge`**
```
Role: You are evaluating whether the assigned priority matches the urgency and impact described in the transcript.

Input:
- Transcript excerpt: "{transcript}"
- Assigned priority: "{priority}"
- Ticket type: "{type}"

Task: Determine if the priority is appropriate:
- P0: Critical, blocks release, affects all users
- P1: High priority, significant impact, deadline mentioned
- P2: Medium priority, normal workflow
- P3: Low priority, nice-to-have, no urgency

Rate appropriateness on a scale of 1-5:
1 = Very inappropriate (e.g., P3 for critical bug)
2 = Somewhat inappropriate
3 = Reasonable but could be adjusted
4 = Appropriate
5 = Perfectly appropriate

Output format:
Score: [1-5]
Reasoning: [One sentence explanation]
Suggested priority: [P0-P3 if different from assigned]
```

**Metric: `priority_appropriateness_score`**
- **Threshold**: ≥ 4.0 average (warn if below)
- **Track in Arize**: Suggest priority changes over time

### 2.3 Action Item Completeness

**Evaluator: `action_item_completeness_judge`**
```
Role: You are evaluating whether all action items from a meeting transcript were captured as tickets.

Input:
- Full transcript: "{transcript}"
- Generated tickets: "{tickets}" (JSON array)

Task: 
1. Identify all action items mentioned in the transcript
2. Check if each is represented in the generated tickets
3. Rate completeness on a scale of 1-5:
   1 = Missed most action items (< 50%)
   2 = Missed some important items (50-70%)
   3 = Captured most items (70-85%)
   4 = Captured nearly all items (85-95%)
   5 = Captured all action items (95-100%)

Output format:
Score: [1-5]
Reasoning: [List any missed items]
Missing items: [List of action items not captured, or "None"]
```

**Metric: `action_completeness_score`**
- **Threshold**: ≥ 4.0 average (fail if below 3.0)
- **Track in Arize**: Missed items over time

### 2.4 Label Relevance

**Evaluator: `label_relevance_judge`**
```
Role: You are evaluating whether the labels assigned to a ticket are relevant and helpful.

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

Output format:
Score: [1-5]
Reasoning: [One sentence explanation]
Suggested additions: [List of labels to add, or "None"]
```

**Metric: `label_relevance_score`**
- **Threshold**: ≥ 3.5 average (warn if below)
- **Track in Arize**: Label suggestions over time

### 2.5 Component Assignment Accuracy

**Evaluator: `component_accuracy_judge`**
```
Role: You are evaluating whether the assigned component (Frontend, Backend, Infrastructure, etc.) is correct for the ticket.

Input:
- Ticket title: "{title}"
- Ticket description: "{description}"
- Assigned component: "{component}"

Task: Rate the accuracy of the component assignment on a scale of 1-5:
1 = Wrong component
2 = Likely wrong, should be different
3 = Could be correct, but uncertain
4 = Correct component
5 = Definitely correct component

If no component is assigned, rate as 3 (neutral).

Output format:
Score: [1-5]
Reasoning: [One sentence explanation]
Suggested component: [Component name if different, or "Correct"]
```

**Metric: `component_accuracy_score`**
- **Threshold**: ≥ 4.0 average (warn if below)
- **Track in Arize**: Component re-assignments over time

### 2.6 Overall Ticket Quality

**Evaluator: `overall_quality_judge`**
```
Role: You are a senior product manager reviewing AI-generated Jira tickets for quality.

Input:
- Original transcript excerpt: "{transcript}"
- Generated ticket: "{ticket}" (JSON)

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

Output format:
Score: [1-5]
Reasoning: [2-3 sentences on strengths and weaknesses]
Would you assign this ticket as-is? [Yes/No]
```

**Metric: `overall_quality_score`**
- **Threshold**: ≥ 3.5 average (warn if below), ≥ 4.0 for production
- **Track in Arize**: Production-readiness rate over time

---

## 3. Evaluation Dataset

### Sample Test Cases

Create a golden dataset with known ground truth:

```json
[
  {
    "id": "eval_001",
    "transcript": "User reported a critical bug: Login page is completely broken on mobile Safari. Users can't access their accounts. This is blocking revenue. We need to fix this today.",
    "expected_tickets": [
      {
        "title": "Fix login page broken on mobile Safari",
        "type": "Bug",
        "priority": "P0",
        "effort": "M",
        "labels": ["bug", "mobile", "login", "safari", "critical"],
        "component": "Frontend"
      }
    ],
    "evaluation_notes": "Should be P0 due to revenue impact and 'today' urgency"
  },
  {
    "id": "eval_002",
    "transcript": "Let's add a dark mode toggle to the settings page. Users have been requesting this for a while. It would be nice to have but not urgent. Sarah will design it first.",
    "expected_tickets": [
      {
        "title": "Add dark mode toggle to settings",
        "type": "Story",
        "priority": "P2",
        "effort": "L",
        "labels": ["feature", "ui", "settings", "dark-mode"],
        "component": "Frontend"
      }
    ],
    "evaluation_notes": "Should be P2 (nice-to-have), Story (feature), L effort (design + implementation)"
  },
  {
    "id": "eval_003",
    "transcript": "During sprint planning: 1) Fix the memory leak in the background sync service. 2) Optimize the database queries on the user dashboard. 3) Add unit tests for the payment processor.",
    "expected_tickets": [
      {
        "title": "Fix memory leak in background sync service",
        "type": "Bug",
        "priority": "P1",
        "labels": ["bug", "performance", "background-sync"],
        "component": "Backend"
      },
      {
        "title": "Optimize database queries on user dashboard",
        "type": "Task",
        "priority": "P2",
        "labels": ["performance", "database", "optimization"],
        "component": "Backend"
      },
      {
        "title": "Add unit tests for payment processor",
        "type": "Task",
        "priority": "P2",
        "labels": ["testing", "payments", "technical-debt"],
        "component": "Backend"
      }
    ],
    "evaluation_notes": "Should extract 3 separate tickets from the list"
  }
]
```

### Edge Cases to Test

1. **Ambiguous priority**: "We should probably fix this sometime"
2. **Multiple action items in one sentence**: "Fix bug and refactor code"
3. **Missing context**: "The button doesn't work" (which button?)
4. **Conflicting information**: "This is urgent but low priority"
5. **No action items**: Pure discussion with no actionable items

---

## 4. Implementation in Arize

### 4.1 Logging Evaluations

Add evaluation results as span attributes:

```python
# Code-based evaluations
current_span.set_attribute("eval.completeness_score", completeness_score)
current_span.set_attribute("eval.priority_format_valid", is_valid)
current_span.set_attribute("eval.tool_call_count", tool_call_count)

# LLM-as-judge evaluations
current_span.set_attribute("eval.description_clarity", clarity_score)
current_span.set_attribute("eval.priority_appropriateness", priority_score)
current_span.set_attribute("eval.overall_quality", quality_score)

# Ground truth comparison (if available)
current_span.set_attribute("eval.ground_truth_match", match_score)
```

### 4.2 Creating Evaluation Sets in Arize

1. Go to Arize → Projects → transcript-to-jira-agent
2. Navigate to **Evaluations** tab
3. Click **Create Evaluation Set**
4. Upload your golden dataset (eval_001, eval_002, etc.)
5. Select evaluators to run:
   - Code-based: All completeness and format metrics
   - LLM-as-judge: Select 2-3 key judges (e.g., overall_quality, priority_appropriateness)

### 4.3 Monitoring Evaluation Trends

Set up dashboards to track:
- **Quality over time**: Is overall_quality_score improving?
- **Accuracy over time**: Is priority_appropriateness improving?
- **Efficiency**: Is tool_call_count decreasing?
- **Production readiness rate**: % of tickets scoring ≥ 4.0

Set up **alerts**:
- Alert if overall_quality_score drops below 3.5 for > 10 requests
- Alert if completeness_score < 80% for any request
- Alert if priority_format_valid fails

---

## 5. Iterative Improvement Process

### Week 1: Baseline
- Run evaluations on 50 sample transcripts
- Identify worst-performing metrics
- Review failed cases manually

### Week 2-3: Improve Prompts
- Focus on metrics scoring < 3.5
- Adjust agent prompts based on failure patterns
- Re-run evaluations to measure improvement

### Week 4: Optimize Tools
- Identify rarely-used tools (remove if < 5% usage)
- Add tools if evaluators suggest missing information
- Optimize tool call order for efficiency

### Monthly: Review Golden Dataset
- Add new edge cases discovered in production
- Update ground truth based on human feedback
- Re-evaluate entire dataset with new agent version

---

## 6. Success Criteria

### Minimum Viable Quality (MVP)
- Completeness: ≥ 80%
- Overall quality: ≥ 3.0
- Priority appropriateness: ≥ 3.5
- Tool efficiency: 4-8 calls/ticket

### Production-Ready Quality
- Completeness: ≥ 90%
- Overall quality: ≥ 4.0
- Priority appropriateness: ≥ 4.5
- Description clarity: ≥ 4.0
- Action completeness: ≥ 4.5

### Exceptional Quality (Goal)
- Completeness: ≥ 95%
- Overall quality: ≥ 4.5
- All LLM-judge metrics: ≥ 4.5
- Human edit rate: < 10% of tickets

---

## 7. Example: Running Evaluations

```python
# Pseudo-code for evaluation flow
def evaluate_transcript_response(transcript, generated_tickets, ground_truth=None):
    evaluations = {}
    
    # Code-based
    evaluations['completeness'] = check_completeness(generated_tickets)
    evaluations['format_valid'] = validate_formats(generated_tickets)
    evaluations['consistency'] = check_consistency(generated_tickets)
    
    # LLM-as-judge
    evaluations['description_clarity'] = llm_judge_clarity(transcript, generated_tickets)
    evaluations['priority_appropriateness'] = llm_judge_priority(transcript, generated_tickets)
    evaluations['overall_quality'] = llm_judge_overall(transcript, generated_tickets)
    
    # Ground truth (if available)
    if ground_truth:
        evaluations['accuracy'] = compare_to_ground_truth(generated_tickets, ground_truth)
    
    # Log to Arize
    log_evaluations_to_arize(evaluations)
    
    return evaluations
```

---

## Next Steps

1. ✅ Define evaluation strategy (this document)
2. ⏭️ Implement code-based evaluators
3. ⏭️ Implement LLM-as-judge evaluators
4. ⏭️ Create golden dataset (20-50 samples)
5. ⏭️ Integrate with Arize evaluation API
6. ⏭️ Run baseline evaluation
7. ⏭️ Set up monitoring dashboards
8. ⏭️ Iterate on prompts based on results

