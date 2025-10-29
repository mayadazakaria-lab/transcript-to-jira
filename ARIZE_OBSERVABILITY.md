# Arize AX Observability Guide

## Overview

The Transcript-to-Jira Agent is fully instrumented with **Arize AX** (not Phoenix) for production-grade observability, allowing you to visualize agent execution, monitor performance, and debug issues.

## What Gets Traced

### 🎯 Agent Execution
- **All 4 agents**: Transcript Analysis, Priority & Impact, Context Enrichment, Ticket Synthesis
- **Parallel execution timing**: See how agents run concurrently
- **State transitions**: Track data flow between agents
- **Agent inputs and outputs**: Full visibility into what each agent processes

### 🛠️ Tool Calls
- **14 custom tools** tracked individually:
  - `extract_action_items()`
  - `identify_ticket_type()`
  - `calculate_priority_score()`
  - `estimate_effort()`
  - `assess_impact()`
  - `vector_search_company_docs()`
  - `find_related_tickets()`
  - `add_labels()`
  - `format_jira_ticket()`
  - And more...
- Tool arguments and return values
- Execution time per tool

### 🤖 LLM Calls
- Model used (gpt-3.5-turbo)
- Prompt templates
- Token usage (input/output)
- Response times
- Costs per call

### 📊 Workflow Metrics
- **Session tracking**: Each request gets a unique session_id
- **User tracking**: Optional user_id for multi-user analysis
- **Meeting metadata**:
  - Meeting type (sprint_planning, user_research, bug_triage, general)
  - Project key
  - Transcript length
  - Auto-submit setting
- **Output metrics**:
  - Number of tickets generated
  - Ticket type distribution (Bug, Story, Task, Epic)
  - Priority distribution (P0, P1, P2, P3)
  - Total tool calls executed

## Setup Instructions

### 1. Get Arize Credentials

1. Go to [https://app.arize.com/](https://app.arize.com/)
2. Create an account or log in
3. Navigate to **Settings** → **API Keys**
4. Copy your:
   - **Space ID** (looks like: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`)
   - **API Key** (looks like: `XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX`)

### 2. Configure Environment Variables

Add to your `backend/.env` file:

```env
# Arize AX Observability
ARIZE_SPACE_ID=your-space-id-here
ARIZE_API_KEY=your-api-key-here
```

### 3. Start the Server

```bash
cd backend
python main.py
```

You should see:
```
✅ Arize AX tracing initialized
📊 Project: transcript-to-jira-agent
🔍 Traces will appear at: https://app.arize.com/
```

### 4. Make Some Requests

```bash
# Use the test script
python "test scripts/test_transcript_api.py"

# Or use the web UI
open http://localhost:8000/
```

### 5. View Traces in Arize

1. Go to [https://app.arize.com/](https://app.arize.com/)
2. Select your Space
3. Navigate to **Projects** → **transcript-to-jira-agent**
4. Click on **Traces** to see your agent executions

## What You'll See in Arize

### Trace Structure

Each request creates a trace with this hierarchy:

```
analyze-transcript (Root Span)
├── session_id: abc-123
├── meeting_type: sprint_planning
├── transcript_length: 2450
│
├── Parallel Agent Execution
│   ├── transcript_analysis_agent
│   │   ├── extract_action_items()
│   │   ├── identify_ticket_type()
│   │   └── extract_requirements()
│   │
│   ├── priority_impact_agent
│   │   ├── calculate_priority_score()
│   │   ├── estimate_effort()
│   │   └── assess_impact()
│   │
│   └── context_enrichment_agent
│       ├── vector_search_company_docs()
│       ├── find_related_tickets()
│       └── add_labels()
│
└── ticket_synthesis_agent
    └── format_jira_ticket()
```

### Key Metrics to Monitor

#### Performance Metrics
- **Total latency**: End-to-end request time
- **Agent latency**: Time per agent (should be similar for parallel agents)
- **LLM latency**: Time waiting for GPT responses
- **Tool call latency**: Time for each tool execution

#### Quality Metrics
- **Tickets generated**: How many tickets per transcript
- **Tool usage**: Which tools are called most frequently
- **Priority distribution**: Are most tickets high/low priority?
- **Ticket types**: Ratio of Bugs vs Stories vs Tasks

#### Business Metrics
- **Sessions**: Unique analysis sessions
- **Meeting types**: Distribution across meeting types
- **Project keys**: Which projects are most active
- **Token usage**: Costs per request

## Advanced Features

### Session Tracking

Track multiple requests from the same user:

```python
# Request 1
POST /analyze-transcript
{
  "transcript": "...",
  "session_id": "user-123-session-1",
  "user_id": "john@company.com"
}

# Request 2 (same session)
POST /analyze-transcript
{
  "transcript": "...",
  "session_id": "user-123-session-1",
  "user_id": "john@company.com",
  "turn_index": 1
}
```

In Arize, you can filter by `session_id` or `user_id` to see all related requests.

### Custom Span Attributes

All traces include these custom attributes:

**Input Attributes:**
- `session_id`: Unique session identifier
- `meeting_type`: Type of meeting analyzed
- `project_key`: Jira project key
- `transcript_length`: Character count of transcript
- `auto_submit`: Whether tickets are auto-submitted
- `endpoint`: Always "analyze-transcript"
- `workflow`: Always "transcript-to-jira"

**Agent Attributes:**
- `agent.type`: "multi-agent-system"
- `agent.workflow`: "parallel-execution"
- `llm.model`: "gpt-3.5-turbo"
- `input.type`: "transcript"
- `output.type`: "jira-tickets"

**Output Attributes:**
- `output.ticket_count`: Number of tickets generated
- `output.tool_calls`: Total tool calls executed
- `output.ticket_types`: JSON of ticket type distribution
- `output.priority_distribution`: JSON of priority distribution

### Filtering in Arize

Use these filters to find specific traces:

**By Meeting Type:**
```
meeting_type = "sprint_planning"
meeting_type = "user_research"
meeting_type = "bug_triage"
```

**By Performance:**
```
latency > 10s
output.ticket_count > 5
output.tool_calls > 10
```

**By Project:**
```
project_key = "PROD"
project_key = "ENG"
```

**By User:**
```
user_id = "john@company.com"
session_id CONTAINS "user-123"
```

## Debugging with Arize

### Common Issues

#### 1. No Tickets Generated
**Filter:** `output.ticket_count = 0`
**Check:**
- View the transcript_analysis_agent span
- Check if extract_action_items() returned empty results
- Review the transcript content in input attributes

#### 2. Slow Response Times
**Filter:** `latency > 15s`
**Check:**
- Which agent took the longest?
- Are LLM calls timing out?
- Check token counts (higher = slower)

#### 3. Wrong Priorities
**Filter:** `output.priority_distribution CONTAINS P0`
**Check:**
- View priority_impact_agent span
- Review calculate_priority_score() outputs
- Check if assessment logic needs tuning

#### 4. Missing Context
**Filter:** `meeting_type = "sprint_planning"`
**Check:**
- View context_enrichment_agent span
- Check if vector_search_company_docs() is working
- Verify RAG is enabled (ENABLE_RAG=1)

## Architecture Details

### Instrumentation Stack

```
FastAPI (Application)
    ↓
OpenTelemetry SDK (Tracing Framework)
    ↓
OpenInference Instrumentation (LangChain/LiteLLM)
    ↓
Arize OTEL (Export to Arize)
    ↓
Arize AX Platform (Visualization)
```

### Key Components

1. **arize-otel**: Registers tracer provider and exports to Arize AX
2. **openinference-instrumentation-langchain**: Auto-instruments LangGraph/LangChain
3. **openinference-instrumentation-litellm**: Captures LLM calls
4. **opentelemetry**: Core tracing framework

### Dependencies

Already included in `requirements.txt`:
```
arize-otel>=0.8.1
openinference-instrumentation-langchain>=0.1.19
openinference-instrumentation-litellm>=0.1.0
openinference-instrumentation>=0.1.12
opentelemetry-sdk>=1.21.0
opentelemetry-exporter-otlp>=1.21.0
```

## Best Practices

### 1. Always Set Session IDs
```python
session_id = f"user-{user_id}-{timestamp}"
```

### 2. Use Meaningful User IDs
```python
user_id = "pm-john@company.com"  # Better than "user123"
```

### 3. Add Project Context
```python
project_key = "PROD"  # Helps filter by project
```

### 4. Monitor Key Metrics
- Track `output.ticket_count` distribution
- Alert on `latency > 20s`
- Monitor `output.tool_calls` for efficiency

### 5. Use Arize Dashboards
Create custom dashboards for:
- Tickets generated per meeting type
- Average latency by project
- Tool usage frequency
- Priority distribution trends

## Troubleshooting

### Traces Not Appearing

**Check 1: Credentials**
```bash
# Verify environment variables are set
echo $ARIZE_SPACE_ID
echo $ARIZE_API_KEY
```

**Check 2: Server Logs**
Look for:
```
✅ Arize AX tracing initialized
📊 Project: transcript-to-jira-agent
```

If you see:
```
⚠️ Arize tracing failed to initialize
```
Check your credentials.

**Check 3: Dependencies**
```bash
pip list | grep arize
pip list | grep openinference
```

### Partial Traces

If you see incomplete traces (missing agents or tools):

1. **Check parallel execution**: All 3 agents should run simultaneously
2. **Verify tool calls**: Each agent should have multiple tool spans
3. **Check for errors**: Look for exception spans in Arize

### Performance Issues

If tracing impacts performance:

1. **Disable during load testing**:
```env
# Comment out these lines to disable tracing
# ARIZE_SPACE_ID=...
# ARIZE_API_KEY=...
```

2. **Sampling** (if needed):
```python
# In register() call, add:
sampling_ratio=0.1  # Sample 10% of requests
```

## FAQ

**Q: Is this Phoenix or Arize AX?**  
A: This uses **Arize AX** (the production platform). Phoenix is for local development only.

**Q: What's the cost?**  
A: Arize AX has a free tier. Check [pricing](https://arize.com/pricing/) for limits.

**Q: Can I use this in production?**  
A: Yes! This instrumentation is production-ready and adds minimal overhead.

**Q: How do I export traces?**  
A: Arize allows exporting traces as JSON or CSV from the UI.

**Q: Can I integrate with other observability tools?**  
A: Yes, OpenTelemetry traces can be exported to Datadog, New Relic, etc. by changing the exporter.

**Q: Does this work with other LLMs?**  
A: Yes! LiteLLM instrumentation supports 100+ LLM providers.

## Resources

- **Arize Docs**: https://docs.arize.com/
- **OpenInference**: https://github.com/Arize-ai/openinference
- **LangChain Instrumentation**: https://docs.arize.com/arize/large-language-models/tracing/langchain
- **Support**: support@arize.com

---

**Your agent is now fully observable in Arize AX!** 🎉

View your traces at: https://app.arize.com/

