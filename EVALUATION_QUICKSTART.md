# Evaluation Quick Start Guide

Get started with evaluating your Transcript-to-Jira Agent using code-based and LLM-as-judge metrics.

---

## 📁 Files Created

```
backend/
├── evaluators.py                              # Evaluation functions (code-based + LLM judges)
├── run_evaluations.py                         # Script to run evaluations on dataset
└── data/
    └── evaluation_golden_dataset.json         # 12 sample test cases with ground truth

EVALUATION_STRATEGY.md                         # Full evaluation strategy (this document you asked for!)
EVALUATION_QUICKSTART.md                       # This quick start guide
```

---

## 🚀 Quick Start

### 1. Test the Evaluators (No API Calls)

Run code-based evaluations on a single example:

```bash
cd backend
python3 evaluators.py
```

**Expected output:**
```
Evaluation Results:
Overall Score: 4.12/5.0
Production Ready: True

Code-Based Results:
  ✅ completeness_score: 100.00 - 5/5 required fields populated (100.0%)
  ✅ priority_format_valid: 1.00 - 1/1 tickets have valid priority format
  ✅ ticket_type_valid: 1.00 - 1/1 tickets have valid type
  ...
```

### 2. Run Evaluations on Golden Dataset

Evaluate the agent on all 12 test cases:

```bash
cd backend
python3 run_evaluations.py --limit 5
```

**What this does:**
- Loads 5 samples from the golden dataset
- Runs your agent on each transcript
- Evaluates results with code-based metrics
- Compares to ground truth (expected tickets)
- Shows aggregate statistics

**Options:**
```bash
# Evaluate all samples
python3 run_evaluations.py

# Evaluate first 3 samples only
python3 run_evaluations.py --limit 3

# Save results to file
python3 run_evaluations.py --output results.json

# Enable LLM-as-judge evaluations (requires API calls)
python3 run_evaluations.py --use-llm-judges
```

### 3. Integrate with Your Agent

To actually evaluate your real agent (not the placeholder), edit `run_evaluations.py`:

```python
def run_agent_on_transcript(transcript: str) -> Dict[str, Any]:
    """Run the actual agent."""
    from main import build_graph, _init_llm, TicketState
    
    # Initialize
    graph = build_graph()
    session_id = f"eval-{int(time.time())}"
    
    # Create state
    state = TicketState(
        messages=[],
        transcript_request={
            "transcript": transcript,
            "meeting_type": "general",
            "project_key": "EVAL"
        },
        tool_calls=[]
    )
    
    # Run graph
    result = graph.invoke(state)
    
    return {
        "tickets": result.get("tickets", []),
        "tool_calls": result.get("tool_calls", [])
    }
```

---

## 📊 Understanding Evaluation Results

### Code-Based Metrics (Deterministic)

These pass/fail checks run instantly with no API calls:

| Metric | What It Checks | Threshold |
|--------|----------------|-----------|
| `completeness_score` | All required fields populated | ≥ 80% |
| `priority_format_valid` | Priority is P0/P1/P2/P3 | 100% |
| `ticket_type_valid` | Type is Bug/Story/Task/Epic | 100% |
| `effort_format_valid` | Effort is S/M/L/XL | 100% |
| `description_length_valid` | Description is 50-2000 chars | ≥ 50 chars |
| `label_count_sufficient` | At least 2 labels per ticket | ≥ 2 |
| `priority_effort_consistent` | P0/P1 shouldn't be S effort | No inconsistencies |
| `bug_priority_appropriate` | Bugs shouldn't be P3 | No P3 bugs |
| `tool_call_efficiency` | 4-8 tool calls per ticket | 4-8 range |

### LLM-as-Judge Metrics (Semantic)

These use an LLM to evaluate quality (requires API calls):

| Evaluator | What It Judges | Scale |
|-----------|----------------|-------|
| `description_clarity` | Is the description clear and detailed? | 1-5 |
| `priority_appropriateness` | Does priority match urgency in transcript? | 1-5 |
| `action_completeness` | Were all action items captured? | 1-5 |
| `label_relevance` | Are labels relevant and specific? | 1-5 |
| `component_accuracy` | Is component assignment correct? | 1-5 |
| `overall_quality` | Would you use this ticket as-is? | 1-5 |

### Production Readiness

A ticket is "production ready" if:
- ✅ All format validations pass (priority, type, effort)
- ✅ Completeness ≥ 80%
- ✅ Overall score ≥ 3.5/5.0

---

## 🔬 Analyzing Results

### Example Output

```
[1/12] Evaluating eval_001: Critical Bug - Urgent
Transcript: Emergency! The login page is completely broken on mobile Safari...
Generated 1 ticket(s)

Ground Truth Comparison:
  Ticket count: 1 (expected 1) ✅
  Type accuracy: 100.0% ✅
  Priority accuracy: 100.0% ✅
  Effort accuracy: 100.0% ✅

Evaluation Results:
  Overall Score: 4.50/5.0
  Production Ready: ✅ Yes
  ✅ All code-based checks passed!

================================================================================
AGGREGATE RESULTS
================================================================================

Overall Performance:
  Average Overall Score: 4.21/5.0
  Production Ready Rate: 91.7% (11/12)

Ground Truth Accuracy:
  Ticket Count Match: 11/12 (91.7%)
  Average Type Accuracy: 95.8%
  Average Priority Accuracy: 87.5%
  Average Effort Accuracy: 83.3%

Code-Based Metric Performance:
  ✅ completeness_score: 100.0%
  ✅ priority_format_valid: 100.0%
  ✅ ticket_type_valid: 100.0%
  ⚠️  label_count_sufficient: 75.0%
  ❌ priority_effort_consistent: 58.3%
```

### What to Focus On

**If Overall Score < 3.5:**
1. Check failed format validations → Fix data models
2. Check completeness → Ensure all fields populated
3. Review description length → Adjust prompts for detail

**If Priority Accuracy < 80%:**
1. Review failed samples → Identify priority patterns
2. Update `calculate_priority_score` tool logic
3. Add more context to priority agent prompt
4. Consider adding priority examples to prompt

**If Production Ready Rate < 85%:**
1. Focus on top 3 failed metrics
2. Add edge cases to golden dataset
3. Test with more diverse transcripts

---

## 🎯 Integration with Arize

### Option 1: Log Evaluations with Traces

Add evaluation logging to your API endpoint in `main.py`:

```python
from evaluators import evaluate_transcript_response, log_evaluations_to_arize

@app.post("/analyze-transcript")
def analyze_transcript(req: TranscriptRequest):
    # ... existing code to generate tickets ...
    
    # Run evaluations
    evaluation = evaluate_transcript_response(
        transcript=req.transcript,
        tickets=tickets,
        tool_calls=out.get("tool_calls", []),
        llm=None  # Or pass LLM for judge evaluations
    )
    
    # Log to Arize span
    if _TRACING:
        current_span = trace.get_current_span()
        log_evaluations_to_arize(evaluation, current_span)
    
    return response
```

**Result:** Every API request will include evaluation metrics in Arize traces!

### Option 2: Arize Evaluation Sets

1. Go to Arize → Projects → `transcript-to-jira-agent`
2. Click **Evaluations** tab
3. Click **Create Evaluation Set**
4. Upload `evaluation_golden_dataset.json`
5. Select evaluators:
   - Add custom evaluators using the LLM-as-judge prompts from `evaluators.py`
   - Or use Arize's built-in evaluators (hallucination, toxicity, etc.)
6. Run evaluation
7. View results dashboard

### Option 3: Continuous Evaluation

Set up a cron job or GitHub Action:

```bash
# Run daily evaluations
0 2 * * * cd /path/to/backend && python3 run_evaluations.py --output daily-eval-$(date +%Y%m%d).json
```

Track results over time to measure improvement!

---

## 📈 Monitoring in Arize

### Set Up Dashboards

Create custom dashboards to track:

```python
# In Arize UI, create charts for:
eval.overall_score (line chart over time)
eval.production_ready (pie chart)
eval.priority_appropriateness.score (histogram)
eval.completeness_score (gauge)
```

### Set Up Alerts

Create alerts for quality degradation:

```
Alert: Overall Score Drops
Condition: eval.overall_score < 3.5 for > 10 requests in 1 hour
Action: Send Slack notification + Email
```

```
Alert: Priority Accuracy Issue  
Condition: eval.priority_appropriateness.score < 3.0 for any request
Action: Log to incidents dashboard
```

---

## 🔄 Iterative Improvement Workflow

### Week 1: Baseline

```bash
# Run full evaluation
python3 run_evaluations.py --output week1-baseline.json

# Review results
cat week1-baseline.json | jq '.aggregate'
```

**Goals:**
- Document baseline scores
- Identify worst 3 metrics
- Review failed samples manually

### Week 2-3: Improve

1. **Focus on Failures:**
   - Priority accuracy low? → Update `calculate_priority_score()` logic
   - Label relevance low? → Add more examples to `add_labels()` prompt
   - Description clarity low? → Make `format_jira_ticket()` more detailed

2. **Test Changes:**
   ```bash
   # After making changes
   python3 run_evaluations.py --output week2-iteration1.json
   
   # Compare to baseline
   diff <(cat week1-baseline.json | jq '.aggregate.avg_overall_score') \
        <(cat week2-iteration1.json | jq '.aggregate.avg_overall_score')
   ```

3. **Iterate:**
   - Make 1 change at a time
   - Re-evaluate after each change
   - Keep changes that improve scores

### Week 4: Production

Once you achieve:
- ✅ Overall score ≥ 4.0
- ✅ Production ready rate ≥ 90%
- ✅ All format validations passing

**Deploy with confidence!**

---

## 🎓 Best Practices

### 1. Start with Code-Based Evaluations
- Fastest to run (no API calls)
- Catch obvious errors (format, completeness)
- Establish baseline quality

### 2. Add LLM-as-Judge for Quality
- Once code-based metrics pass consistently
- Focus on 2-3 key judges (e.g., `overall_quality`, `priority_appropriateness`)
- More expensive but catch semantic issues

### 3. Grow Your Golden Dataset
- Start with 10-12 samples (already provided!)
- Add new edge cases as you find them in production
- Include both positive and negative examples
- Cover all meeting types (sprint planning, bug triage, user research, general)

### 4. Track Over Time
- Run evaluations on every code change
- Log results to track improvement trends
- Create "evaluation report cards" for releases

### 5. Human-in-the-Loop
- Sample 10% of production requests for manual review
- Compare human scores to automated scores
- Adjust thresholds based on human feedback

---

## 🆘 Troubleshooting

### "ModuleNotFoundError: No module named 'evaluators'"

```bash
# Ensure you're in the backend directory
cd backend
python3 run_evaluations.py
```

### "FileNotFoundError: evaluation_golden_dataset.json"

```bash
# Check the file exists
ls data/evaluation_golden_dataset.json

# If running from wrong directory, use absolute path
python3 run_evaluations.py --dataset /full/path/to/data/evaluation_golden_dataset.json
```

### "No tickets generated"

Your `run_agent_on_transcript()` function is still using the placeholder. See Step 3 above to integrate your real agent.

### "All evaluations failing"

Check your ticket format matches expected structure:
```python
{
    "title": str,
    "type": str,        # Must be: Bug, Story, Task, or Epic
    "priority": str,    # Must be: P0, P1, P2, or P3
    "effort": str,      # Must be: S, M, L, or XL
    "description": str,
    "labels": list,
    "component": str
}
```

---

## 📚 Additional Resources

- **Full Strategy**: See `EVALUATION_STRATEGY.md` for detailed methodology
- **Arize Docs**: https://docs.arize.com/arize/large-language-models/evaluation
- **LLM Evaluation Best Practices**: https://www.arize.com/blog/llm-evaluation-best-practices

---

## ✅ Next Steps

1. ✅ Run `python3 evaluators.py` to test
2. ✅ Run `python3 run_evaluations.py --limit 3` to evaluate on golden dataset
3. ✅ Review results and identify improvement areas
4. ⏭️ Integrate real agent (see Step 3)
5. ⏭️ Add evaluation logging to API endpoint (see Arize Integration)
6. ⏭️ Set up Arize dashboards and alerts
7. ⏭️ Iterate on prompts based on evaluation results

**Your evaluation framework is ready!** 🎉

Start measuring quality, iterate on your agent, and ship production-ready tickets with confidence.

