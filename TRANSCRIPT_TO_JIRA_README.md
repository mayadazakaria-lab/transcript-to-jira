# Transcript-to-Jira Agent System

A **production-ready multi-agent AI system** that automatically analyzes meeting transcripts and generates structured Jira tickets. Built by adapting the AI Trip Planner architecture to demonstrate how to transform multi-agent systems for different domains.

## 🎯 What It Does

Transforms meeting transcripts into actionable Jira tickets by:
1. **Extracting** action items, feature requests, and bugs from conversations
2. **Prioritizing** tickets with P0-P3 scores and effort estimates (S/M/L/XL)
3. **Enriching** with company context, labels, and related ticket references
4. **Generating** structured Jira-ready tickets with proper formatting

**Time Saved**: Reduces ticket creation from 10-15 minutes to under 30 seconds per ticket.

## 🏗️ Architecture

### Multi-Agent Workflow

```
Transcript Input → Parallel Agent Processing → Ticket Synthesis → JSON Output

┌─────────────────────────────────────────────────────────┐
│              Transcript Analysis Agent                  │
│  • Extracts action items from transcript                │
│  • Identifies ticket types (Story/Bug/Task/Epic)        │
│  • Extracts requirements and acceptance criteria        │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────┼───────────────────────────────────────┐
│                 │                                        │
│  Priority &     │         Context Enrichment            │
│  Impact Agent   │              Agent                     │
│                 │                                        │
│  • Calculates   │         • Adds labels &               │
│    P0-P3        │           components                   │
│  • Estimates    │         • Finds related               │
│    S/M/L/XL     │           tickets                      │
│  • Assesses     │         • References docs             │
│    impact       │           (RAG-enabled)                │
│                 │                                        │
└─────────────────┴───────────────────────────────────────┘
                  │
          ┌───────▼────────┐
          │    Ticket      │
          │   Synthesis    │
          │     Agent      │
          └───────┬────────┘
                  │
          ┌───────▼────────┐
          │  Structured    │
          │  Jira Tickets  │
          │  (JSON Output) │
          └────────────────┘
```

### Agent Mapping from Trip Planner

| Original Agent | → | New Agent | Purpose |
|----------------|---|-----------|---------|
| Research Agent | → | **Transcript Analysis** | Extracts actionable items |
| Budget Agent | → | **Priority & Impact** | Scores priority & estimates effort |
| Local Agent (+ RAG) | → | **Context Enrichment** | Adds company-specific metadata |
| Itinerary Agent | → | **Ticket Synthesis** | Generates final Jira tickets |

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Create `backend/.env`:

```env
# Required
OPENAI_API_KEY=sk-your-key-here

# Optional: Enable RAG for company context
ENABLE_RAG=1

# Optional: Jira Integration (placeholder for v2)
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_API_TOKEN=your_jira_token
JIRA_PROJECT_KEY=PROD

# Optional: Observability
ARIZE_SPACE_ID=your_space_id
ARIZE_API_KEY=your_arize_key
```

### 3. Start the Server

```bash
cd backend
python main.py

# Or with auto-reload:
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test It

```bash
python "test scripts/test_transcript_api.py"
```

## 📡 API Usage

### POST `/analyze-transcript`

**Request:**
```json
{
  "transcript": "Product meeting transcript here...",
  "meeting_type": "sprint_planning",
  "project_key": "PROD",
  "auto_submit": false
}
```

**Response:**
```json
{
  "session_id": "uuid",
  "tickets": [
    {
      "title": "Fix dark mode toggle on mobile",
      "type": "Bug",
      "priority": "P1",
      "effort": "S",
      "description": "Dark mode toggle not working on mobile devices...",
      "labels": ["ui", "mobile", "bug"],
      "component": "frontend"
    },
    {
      "title": "Implement dashboard pagination",
      "type": "Story",
      "priority": "P0",
      "effort": "L",
      "description": "Dashboard loading time is 5-8 seconds...",
      "labels": ["performance", "backend"],
      "component": "dashboard"
    }
  ],
  "metadata": {
    "meeting_type": "sprint_planning",
    "project_key": "PROD",
    "action_items_found": 2,
    "processing_time": "8.2s"
  },
  "tool_calls": [...]
}
```

### GET `/health`

```json
{
  "status": "healthy",
  "service": "transcript-to-jira-agent"
}
```

## 🛠️ Tools by Agent

### Transcript Analysis Tools
- `extract_action_items()` - Extracts actionable items from transcript
- `identify_ticket_type()` - Classifies as Story/Bug/Task/Epic
- `extract_requirements()` - Pulls out acceptance criteria

### Priority & Impact Tools
- `calculate_priority_score()` - Assigns P0-P3 based on impact
- `estimate_effort()` - Estimates S/M/L/XL effort
- `assess_impact()` - Evaluates business & user impact

### Context Enrichment Tools
- `vector_search_company_docs()` - RAG over company documentation
- `find_related_tickets()` - Identifies duplicate/related work
- `add_labels()` - Suggests appropriate labels & components

### Ticket Synthesis Tools
- `format_jira_ticket()` - Structures ticket with proper sections
- `create_jira_ticket()` - Creates ticket via Jira API (v2)

## 🔍 Observability

All agent executions, tool calls, and LLM interactions are traced via **Arize + OpenTelemetry**:

- View agent execution flow
- Debug tool call arguments
- Monitor LLM performance
- Track session metadata

Access traces at: https://app.arize.com/

## 📊 Example Use Cases

### Sprint Planning Meeting
```
Input: 2-hour meeting transcript
Output: 6 prioritized tickets with effort estimates
Time Saved: ~90 minutes
```

### User Research Session
```
Input: Customer interview transcript
Output: 4 feature requests + 2 bug reports
Time Saved: ~60 minutes
```

### Bug Triage Meeting
```
Input: Bug discussion transcript
Output: 8 categorized bugs with priority scores
Time Saved: ~120 minutes
```

## 🎓 Learning Paths

### Beginner: Understand the System (30 min)
1. Run the system with sample transcript
2. Review generated tickets
3. Check traces in Arize dashboard
4. Modify agent prompts and observe changes

### Intermediate: Customize for Your Domain (2 hours)
1. Add custom tools specific to your workflow
2. Modify priority calculation logic
3. Integrate real company documentation for RAG
4. Adjust ticket structure for your Jira setup

### Advanced: Full Jira Integration (4 hours)
1. Implement real Jira API integration
2. Add duplicate detection against existing tickets
3. Set up automatic ticket assignment
4. Create approval workflow for auto-submission

## 🔧 Configuration Options

### Meeting Types
- `sprint_planning` - Team planning sessions
- `user_research` - Customer interviews
- `bug_triage` - Bug review meetings
- `general` - Any other meeting type

### Auto-Submit Mode
```json
{
  "auto_submit": true  // Automatically creates tickets in Jira
}
```

### RAG Context
Enable with `ENABLE_RAG=1` to search company documentation and past tickets for relevant context.

## 📁 Project Structure

```
backend/
├── main.py                 # Core agent system
├── data/
│   └── local_guides.json  # Sample data (reused for demo)
├── .env                   # Configuration
└── requirements.txt       # Dependencies

test scripts/
├── test_transcript_api.py    # API test script
└── sample_transcript.txt     # Sample meeting transcript

my_agent_prd.md              # Product requirements document
```

## 🚧 Roadmap

### Phase 1: MVP (✅ Complete)
- [x] Multi-agent architecture
- [x] Transcript analysis
- [x] Priority & effort estimation
- [x] Ticket generation
- [x] API endpoint
- [x] Sample data & tests

### Phase 2: Enhanced Features
- [ ] Real Jira API integration
- [ ] Duplicate ticket detection
- [ ] Automatic team assignment
- [ ] Voice-to-text integration
- [ ] Slack bot interface

### Phase 3: Production Ready
- [ ] User approval workflow
- [ ] Bulk processing of multiple transcripts
- [ ] Template library for different meeting types
- [ ] Analytics dashboard
- [ ] Multi-language support

## 🎯 Key Metrics

**Success Criteria** (from PRD):
- ✅ Ticket creation time: < 30 seconds (vs 10-15 min manual)
- 🎯 User acceptance rate: > 85% of tickets accepted with minor edits
- 🎯 Coverage: Extract 95%+ of actionable items
- 🎯 Time saved: 2+ hours per PM per week

## 🤝 Contributing

This is a learning project! To extend it:

1. **Add New Tools**: Follow the `@tool` decorator pattern
2. **Create New Agents**: Copy agent structure and update graph
3. **Modify Prompts**: All prompts use `{variable}` format
4. **Integrate APIs**: Add to tools with graceful LLM fallback

## 📚 References

- **Original Architecture**: AI Trip Planner (in same repo)
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **Jira API**: https://developer.atlassian.com/cloud/jira/platform/rest/v3/
- **Arize Platform**: https://docs.arize.com/

## 💡 Tips for Customization

1. **Change Domain**: Replace transcript analysis with your input type
2. **Modify Output**: Change ticket structure to match your system
3. **Add Context**: Use RAG with your company's documentation
4. **Adjust Priority Logic**: Customize scoring based on your criteria
5. **Integrate Tools**: Add Slack, Linear, GitHub Issues, etc.

---

**Built with**: LangGraph, FastAPI, OpenAI, Arize  
**Adapted from**: AI Trip Planner multi-agent architecture  
**Time to Build**: ~2 hours with existing codebase


