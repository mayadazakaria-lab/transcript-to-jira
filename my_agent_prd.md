# Product Requirements Document: Transcript-to-Jira Agent

## Problem Statement
Product and engineering teams spend 2-3 hours weekly manually converting meeting notes and user research transcripts into actionable Jira tickets. This manual process is error-prone, inconsistent, and delays feature development. We need an AI agent system that automatically analyzes transcripts and generates well-structured, prioritized Jira tickets.

## Goals & Success Metrics
**Primary Goal**: Reduce ticket creation time by 80% while maintaining quality and consistency.

**Success Metrics**:
- Ticket creation time: < 30 seconds per ticket (vs 10-15 minutes manual)
- User acceptance rate: > 85% of generated tickets accepted with minor/no edits
- Coverage: Extract 95%+ of actionable items from transcripts
- Time saved: 2+ hours per PM per week

## Target Users
- Product Managers conducting user research and sprint planning
- Customer Success teams processing feedback calls
- Engineering leads reviewing technical discovery sessions

## Architecture Overview
Multi-agent system built on LangGraph with FastAPI backend, adapting the proven trip planner architecture:

```
Transcript Input → Parallel Agent Processing → Ticket Synthesis → Jira API Integration
```

## Agent Design

### 1. **Transcript Analysis Agent** (Research Phase)
**Purpose**: Extract actionable items, feature requests, bugs, and technical requirements  
**Tools**: `extract_action_items()`, `identify_ticket_type()`, `extract_requirements()`  
**Output**: List of potential tickets with raw requirements and context

### 2. **Priority & Impact Agent** (Budget Phase)
**Purpose**: Assess priority, effort estimation, and business impact  
**Tools**: `calculate_priority_score()`, `estimate_effort()`, `assess_impact()`  
**Output**: Priority ratings (P0-P3), effort estimates (S/M/L/XL), impact scores

### 3. **Context Enrichment Agent** (Local Phase + RAG)
**Purpose**: Add company-specific context, link related tickets, reference documentation  
**Tools**: `vector_search_company_docs()`, `find_related_tickets()`, `add_labels()`  
**RAG Data**: Company product docs, architectural decisions, past tickets  
**Output**: Enriched tickets with proper labels, components, and cross-references

### 4. **Ticket Synthesis Agent** (Itinerary Phase)
**Purpose**: Generate final Jira ticket structure and create via API  
**Tools**: `format_jira_ticket()`, `create_jira_ticket()`, `add_attachments()`  
**Output**: Created Jira tickets with proper formatting, links, and metadata

## Technical Requirements

**Core Stack** (from existing repo):
- LangGraph for multi-agent orchestration
- FastAPI for API endpoints
- LiteLLM for LLM calls (OpenAI/OpenRouter)
- Arize for observability and quality monitoring

**New Integrations**:
- Jira REST API for ticket creation
- Transcript processing (Whisper API or Deepgram for audio → text)
- Vector DB for RAG over company documentation

**Environment Variables**:
```
OPENAI_API_KEY=required
JIRA_API_TOKEN=required
JIRA_BASE_URL=required
JIRA_PROJECT_KEY=required
ENABLE_RAG=1 (for company context)
ARIZE_SPACE_ID=recommended (for monitoring)
```

## Key Features (MVP)

### Phase 1: Core Functionality
- ✅ Upload transcript (text file or meeting recording URL)
- ✅ Automatic extraction of action items and features
- ✅ Priority scoring and effort estimation
- ✅ Jira ticket generation with standard fields
- ✅ User review and edit before submission

### Phase 2: Enhancement
- Context from previous tickets and company docs (RAG)
- Automatic assignment based on team/component
- Duplicate detection
- Bulk ticket creation from long transcripts

## API Design

**POST** `/analyze-transcript`
```json
{
  "transcript": "text or file_url",
  "meeting_type": "user_research|sprint_planning|bug_triage",
  "project_key": "PROD",
  "auto_submit": false
}
```

**Response**:
```json
{
  "session_id": "uuid",
  "tickets": [
    {
      "title": "Add dark mode toggle",
      "type": "Story",
      "priority": "P1",
      "effort": "M",
      "description": "Formatted Jira description...",
      "labels": ["ui", "accessibility"],
      "jira_url": "optional if auto_submit=true"
    }
  ],
  "metadata": {
    "action_items_found": 5,
    "processing_time": "8.2s"
  }
}
```

## User Experience

1. **Upload**: User pastes transcript or provides meeting recording URL
2. **Processing**: System shows progress (analyzing → prioritizing → enriching → generating)
3. **Review**: User sees generated tickets in preview mode with edit capability
4. **Approve**: User selects which tickets to create, can edit before submission
5. **Confirmation**: System creates Jira tickets and provides links

## Non-Goals (v1)
- Real-time transcription during meetings
- Multi-language support beyond English
- Integration with tools other than Jira (Linear, Asana, etc.)
- Automated ticket assignment without human review

## Timeline
- **Week 1-2**: Adapt trip planner architecture, implement transcript analysis and priority agents
- **Week 3**: Add context enrichment (RAG) and Jira integration
- **Week 4**: Build ticket synthesis agent and API endpoints
- **Week 5**: Testing, observability setup, documentation
- **Week 6**: Beta launch with 3-5 internal teams

## Open Questions
1. Should we support real-time streaming (analyze transcript as it's being spoken)?
2. What's the preferred UX: Chrome extension, Slack bot, or web app?
3. Should tickets be created in draft mode or directly submitted?
4. Do we need approval workflows for auto-submission?

---

**Owner**: Product Team | **Engineering Lead**: TBD | **Target Launch**: 6 weeks
