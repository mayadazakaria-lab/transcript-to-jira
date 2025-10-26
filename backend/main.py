from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import time
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

# Minimal observability via Arize/OpenInference (optional)
try:
    from arize.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from openinference.instrumentation import using_prompt_template, using_metadata, using_attributes
    from opentelemetry import trace
    _TRACING = True
except Exception:
    def using_prompt_template(**kwargs):  # type: ignore
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()
    def using_metadata(*args, **kwargs):  # type: ignore
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()
    def using_attributes(*args, **kwargs):  # type: ignore
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield
        return _noop()
    _TRACING = False

# LangGraph + LangChain
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict, Annotated
import operator
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import InMemoryVectorStore
import httpx


class TranscriptRequest(BaseModel):
    transcript: str
    meeting_type: Optional[str] = "general"  # user_research, sprint_planning, bug_triage, general
    project_key: Optional[str] = "PROJ"
    auto_submit: Optional[bool] = False
    # Optional fields for enhanced session tracking and observability
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    turn_index: Optional[int] = None


class JiraTicket(BaseModel):
    title: str
    type: str  # Story, Bug, Task, Epic
    priority: str  # P0, P1, P2, P3
    effort: str  # S, M, L, XL
    description: str
    labels: List[str] = []
    component: Optional[str] = None
    jira_url: Optional[str] = None


class TranscriptResponse(BaseModel):
    session_id: str
    tickets: List[JiraTicket]
    metadata: Dict[str, Any] = {}
    tool_calls: List[Dict[str, Any]] = []


def _init_llm():
    # Simple, test-friendly LLM init
    class _Fake:
        def __init__(self):
            pass
        def bind_tools(self, tools):
            return self
        def invoke(self, messages):
            class _Msg:
                content = "Test itinerary"
                tool_calls: List[Dict[str, Any]] = []
            return _Msg()

    if os.getenv("TEST_MODE"):
        return _Fake()
    if os.getenv("OPENAI_API_KEY"):
        return ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7, max_tokens=1500)
    elif os.getenv("OPENROUTER_API_KEY"):
        # Use OpenRouter via OpenAI-compatible client
        return ChatOpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            model=os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            temperature=0.7,
        )
    else:
        # Require a key unless running tests
        raise ValueError("Please set OPENAI_API_KEY or OPENROUTER_API_KEY in your .env")


llm = _init_llm()


# Feature flag for optional RAG demo (opt-in for learning)
ENABLE_RAG = os.getenv("ENABLE_RAG", "0").lower() not in {"0", "false", "no"}


# RAG helper: Load curated local guides as LangChain documents
def _load_local_documents(path: Path) -> List[Document]:
    """Load local guides JSON and convert to LangChain Documents."""
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return []

    docs: List[Document] = []
    for row in raw:
        description = row.get("description")
        city = row.get("city")
        if not description or not city:
            continue
        interests = row.get("interests", []) or []
        metadata = {
            "city": city,
            "interests": interests,
            "source": row.get("source"),
        }
        # Prefix city + interests in content so embeddings capture location context
        interest_text = ", ".join(interests) if interests else "general travel"
        content = f"City: {city}\nInterests: {interest_text}\nGuide: {description}"
        docs.append(Document(page_content=content, metadata=metadata))
    return docs


class LocalGuideRetriever:
    """Retrieves curated local experiences using vector similarity search.
    
    This class demonstrates production RAG patterns for students:
    - Vector embeddings for semantic search
    - Fallback to keyword matching when embeddings unavailable
    - Graceful degradation with feature flags
    """
    
    def __init__(self, data_path: Path):
        """Initialize retriever with local guides data.
        
        Args:
            data_path: Path to local_guides.json file
        """
        self._docs = _load_local_documents(data_path)
        self._embeddings: Optional[OpenAIEmbeddings] = None
        self._vectorstore: Optional[InMemoryVectorStore] = None
        
        # Only create embeddings when RAG is enabled and we have an API key
        if ENABLE_RAG and self._docs and not os.getenv("TEST_MODE"):
            try:
                model = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
                self._embeddings = OpenAIEmbeddings(model=model)
                store = InMemoryVectorStore(embedding=self._embeddings)
                store.add_documents(self._docs)
                self._vectorstore = store
            except Exception:
                # Gracefully degrade to keyword search if embeddings fail
                self._embeddings = None
                self._vectorstore = None

    @property
    def is_empty(self) -> bool:
        """Check if any documents were loaded."""
        return not self._docs

    def retrieve(self, destination: str, interests: Optional[str], *, k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve top-k relevant local guides for a destination.
        
        Args:
            destination: City or destination name
            interests: Comma-separated interests (e.g., "food, art")
            k: Number of results to return
            
        Returns:
            List of dicts with 'content', 'metadata', and 'score' keys
        """
        if not ENABLE_RAG or self.is_empty:
            return []

        # Use vector search if available, otherwise fall back to keywords
        if not self._vectorstore:
            return self._keyword_fallback(destination, interests, k=k)

        query = destination
        if interests:
            query = f"{destination} with interests {interests}"
        
        try:
            # LangChain retriever ensures embeddings + searches are traced
            retriever = self._vectorstore.as_retriever(search_kwargs={"k": max(k, 4)})
            docs = retriever.invoke(query)
        except Exception:
            return self._keyword_fallback(destination, interests, k=k)

        # Format results with metadata and scores
        top_docs = docs[:k]
        results = []
        for doc in top_docs:
            score_val: float = 0.0
            if isinstance(doc.metadata, dict):
                maybe_score = doc.metadata.get("score")
                if isinstance(maybe_score, (int, float)):
                    score_val = float(maybe_score)
            results.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": score_val,
            })

        if not results:
            return self._keyword_fallback(destination, interests, k=k)
        return results

    def _keyword_fallback(self, destination: str, interests: Optional[str], *, k: int) -> List[Dict[str, Any]]:
        """Simple keyword-based retrieval when embeddings unavailable.
        
        This demonstrates graceful degradation for students learning about
        fallback strategies in production systems.
        """
        dest_lower = destination.lower()
        interest_terms = [part.strip().lower() for part in (interests or "").split(",") if part.strip()]

        def _score(doc: Document) -> int:
            score = 0
            city_match = doc.metadata.get("city", "").lower()
            # Match city name
            if dest_lower and dest_lower.split(",")[0] in city_match:
                score += 2
            # Match interests
            for term in interest_terms:
                if term and term in " ".join(doc.metadata.get("interests") or []).lower():
                    score += 1
                if term and term in doc.page_content.lower():
                    score += 1
            return score

        scored_docs = [(_score(doc), doc) for doc in self._docs]
        scored_docs.sort(key=lambda item: item[0], reverse=True)
        top_docs = scored_docs[:k]
        
        results = []
        for score, doc in top_docs:
            if score > 0:
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score),
                })
        return results


# Initialize retriever at module level (loads data once at startup)
_DATA_DIR = Path(__file__).parent / "data"
GUIDE_RETRIEVER = LocalGuideRetriever(_DATA_DIR / "local_guides.json")


# Search API configuration and helpers
SEARCH_TIMEOUT = 10.0  # seconds


def _compact(text: str, limit: int = 200) -> str:
    """Compact text to a maximum length, truncating at word boundaries."""
    if not text:
        return ""
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated.rstrip(",.;- ")


def _search_api(query: str) -> Optional[str]:
    """Search the web using Tavily or SerpAPI if configured, return None otherwise.
    
    This demonstrates graceful degradation: tools work with or without API keys.
    Students can enable real search by adding TAVILY_API_KEY or SERPAPI_API_KEY.
    """
    query = query.strip()
    if not query:
        return None

    # Try Tavily first (recommended for AI apps)
    tavily_key = os.getenv("TAVILY_API_KEY")
    if tavily_key:
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": tavily_key,
                        "query": query,
                        "max_results": 3,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                answer = data.get("answer") or ""
                snippets = [
                    item.get("content") or item.get("snippet") or ""
                    for item in data.get("results", [])
                ]
                combined = " ".join([answer] + snippets).strip()
                if combined:
                    return _compact(combined)
        except Exception:
            pass  # Fail gracefully, try next option

    # Try SerpAPI as fallback
    serp_key = os.getenv("SERPAPI_API_KEY")
    if serp_key:
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT) as client:
                resp = client.get(
                    "https://serpapi.com/search",
                    params={
                        "api_key": serp_key,
                        "engine": "google",
                        "num": 5,
                        "q": query,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                organic = data.get("organic_results", [])
                snippets = [item.get("snippet", "") for item in organic]
                combined = " ".join(snippets).strip()
                if combined:
                    return _compact(combined)
        except Exception:
            pass  # Fail gracefully

    return None  # No search APIs configured


def _llm_fallback(instruction: str, context: Optional[str] = None) -> str:
    """Use the LLM to generate a response when search APIs aren't available.
    
    This ensures tools always return useful information, even without API keys.
    """
    prompt = "Respond with 200 characters or less.\n" + instruction.strip()
    if context:
        prompt += "\nContext:\n" + context.strip()
    response = llm.invoke([
        SystemMessage(content="You are a concise travel assistant."),
        HumanMessage(content=prompt),
    ])
    return _compact(response.content)


def _with_prefix(prefix: str, summary: str) -> str:
    """Add a prefix to a summary for clarity."""
    text = f"{prefix}: {summary}" if prefix else summary
    return _compact(text)


# Tools for transcript analysis and ticket generation
@tool
def extract_action_items(transcript: str) -> str:
    """Extract actionable items, feature requests, and bugs from a transcript."""
    # Use LLM to extract action items from the transcript
    instruction = (
        "Analyze this meeting transcript and extract all actionable items, feature requests, bugs, and tasks. "
        "For each item, provide: 1) A clear title, 2) Description, 3) Type (Story/Bug/Task). "
        "Return as a structured list.\n\n"
        f"Transcript: {transcript[:2000]}"  # Limit length for context
    )
    return _llm_fallback(instruction)


@tool
def identify_ticket_type(item_description: str) -> str:
    """Identify the type of Jira ticket (Story, Bug, Task, Epic) based on description."""
    instruction = (
        f"Analyze this item and determine if it should be a Story, Bug, Task, or Epic ticket. "
        f"Provide reasoning.\n\n"
        f"Item: {item_description}"
    )
    return _llm_fallback(instruction)


@tool
def extract_requirements(action_item: str) -> str:
    """Extract detailed requirements and acceptance criteria from an action item."""
    instruction = (
        f"Given this action item, extract detailed requirements, acceptance criteria, and technical considerations. "
        f"Be specific and actionable.\n\n"
        f"Action Item: {action_item}"
    )
    return _llm_fallback(instruction)


# Tools for Priority & Impact Agent
@tool
def calculate_priority_score(ticket_description: str, impact: str = "medium") -> str:
    """Calculate priority score (P0-P3) based on ticket description and business impact."""
    instruction = (
        f"Assess the priority of this ticket. Consider urgency, business impact ({impact}), "
        f"user pain points, and dependencies. Assign P0 (critical), P1 (high), P2 (medium), or P3 (low). "
        f"Provide reasoning.\n\n"
        f"Ticket: {ticket_description}"
    )
    return _llm_fallback(instruction)


@tool
def estimate_effort(ticket_description: str, technical_complexity: str = "unknown") -> str:
    """Estimate development effort (S/M/L/XL) for a ticket."""
    instruction = (
        f"Estimate the development effort for this ticket. Consider technical complexity ({technical_complexity}), "
        f"dependencies, testing needs, and unknown factors. "
        f"Assign S (small, <1 day), M (medium, 1-3 days), L (large, 1 week), or XL (extra large, >1 week). "
        f"Provide reasoning.\n\n"
        f"Ticket: {ticket_description}"
    )
    return _llm_fallback(instruction)


@tool
def assess_impact(ticket_description: str, ticket_type: str = "Story") -> str:
    """Assess business and user impact of implementing this ticket."""
    instruction = (
        f"Assess the business and user impact of this {ticket_type}. "
        f"Consider: user pain points addressed, business value, potential risks, and strategic alignment. "
        f"Provide a concise impact assessment.\n\n"
        f"Ticket: {ticket_description}"
    )
    return _llm_fallback(instruction)


# Tools for Context Enrichment Agent
@tool
def vector_search_company_docs(query: str) -> str:
    """Search company documentation and past tickets for relevant context."""
    # This is a placeholder - in production would use real vector search
    instruction = (
        f"Based on typical company documentation patterns, suggest relevant context, "
        f"related components, common labels, and similar past tickets for: {query}"
    )
    return _llm_fallback(instruction)


@tool
def find_related_tickets(ticket_summary: str) -> str:
    """Find related or duplicate tickets based on similarity."""
    # Placeholder - would query Jira API in production
    instruction = (
        f"Suggest what related or potentially duplicate tickets might exist for: {ticket_summary}. "
        f"Include suggestions for linking to related work."
    )
    return _llm_fallback(instruction)


@tool
def add_labels(ticket_description: str, ticket_type: str) -> str:
    """Suggest appropriate labels and components based on ticket content."""
    instruction = (
        f"Suggest appropriate Jira labels, components, and tags for this {ticket_type}. "
        f"Consider technical area, feature category, and team ownership.\n\n"
        f"Ticket: {ticket_description}"
    )
    return _llm_fallback(instruction)


# Tools for Ticket Synthesis Agent
@tool
def format_jira_ticket(title: str, description: str, ticket_type: str, priority: str, effort: str) -> str:
    """Format ticket information into proper Jira structure."""
    instruction = (
        f"Format this information into a well-structured Jira ticket description with sections for: "
        f"Summary, Description, Acceptance Criteria, Technical Notes, and Dependencies.\n\n"
        f"Title: {title}\n"
        f"Type: {ticket_type}\n"
        f"Priority: {priority}\n"
        f"Effort: {effort}\n"
        f"Description: {description}"
    )
    return _llm_fallback(instruction)


@tool
def create_jira_ticket(ticket_data: Dict[str, Any]) -> str:
    """Create a Jira ticket via API (placeholder for actual implementation)."""
    # This is a placeholder - real implementation would call Jira REST API
    jira_url = os.getenv("JIRA_BASE_URL", "https://your-company.atlassian.net")
    project_key = ticket_data.get("project_key", "PROJ")
    ticket_id = f"{project_key}-{int(time.time()) % 10000}"
    
    return f"Ticket created: {jira_url}/browse/{ticket_id}"


@tool
def local_flavor(destination: str, interests: Optional[str] = None) -> str:
    """Suggest authentic local experiences matching optional interests."""
    focus = interests or "local culture"
    query = f"{destination} authentic local experiences {focus}"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} {focus}", summary)
    
    instruction = f"Recommend authentic local experiences in {destination} that highlight {focus}."
    return _llm_fallback(instruction)


@tool
def day_plan(destination: str, day: int) -> str:
    """Return a simple day plan outline for a specific day number."""
    query = f"{destination} day {day} itinerary highlights"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"Day {day} in {destination}", summary)
    
    instruction = f"Outline key activities for day {day} in {destination}, covering morning, afternoon, and evening."
    return _llm_fallback(instruction)


# Additional simple tools per agent (to mirror original multi-tool behavior)
@tool
def weather_brief(destination: str) -> str:
    """Return a brief weather summary for planning purposes."""
    query = f"{destination} weather forecast travel season temperatures rainfall"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} weather", summary)
    
    instruction = f"Give a weather brief for {destination} noting season, temperatures, rainfall, humidity, and packing guidance."
    return _llm_fallback(instruction)


@tool
def visa_brief(destination: str) -> str:
    """Return a brief visa guidance for travel planning."""
    query = f"{destination} tourist visa requirements entry rules"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} visa", summary)
    
    instruction = f"Provide a visa guidance summary for visiting {destination}, including advice to confirm with the relevant embassy."
    return _llm_fallback(instruction)


@tool
def attraction_prices(destination: str, attractions: Optional[List[str]] = None) -> str:
    """Return pricing information for attractions."""
    items = attractions or ["popular attractions"]
    focus = ", ".join(items)
    query = f"{destination} attraction ticket prices {focus}"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} attraction prices", summary)
    
    instruction = f"Share typical ticket prices and savings tips for attractions such as {focus} in {destination}."
    return _llm_fallback(instruction)


@tool
def local_customs(destination: str) -> str:
    """Return cultural etiquette and customs information."""
    query = f"{destination} cultural etiquette travel customs"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} customs", summary)
    
    instruction = f"Summarize key etiquette and cultural customs travelers should know before visiting {destination}."
    return _llm_fallback(instruction)


@tool
def hidden_gems(destination: str) -> str:
    """Return lesser-known attractions and experiences."""
    query = f"{destination} hidden gems local secrets lesser known spots"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} hidden gems", summary)
    
    instruction = f"List lesser-known attractions or experiences that feel like hidden gems in {destination}."
    return _llm_fallback(instruction)


@tool
def travel_time(from_location: str, to_location: str, mode: str = "public") -> str:
    """Return travel time estimates between locations."""
    query = f"travel time {from_location} to {to_location} by {mode}"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{from_location}→{to_location} {mode}", summary)
    
    instruction = f"Estimate travel time from {from_location} to {to_location} by {mode} transport."
    return _llm_fallback(instruction)


@tool
def packing_list(destination: str, duration: str, activities: Optional[List[str]] = None) -> str:
    """Return packing recommendations for the trip."""
    acts = ", ".join(activities or ["sightseeing"])
    query = f"what to pack for {destination} {duration} {acts}"
    summary = _search_api(query)
    if summary:
        return _with_prefix(f"{destination} packing", summary)
    
    instruction = f"Suggest packing essentials for a {duration} trip to {destination} focused on {acts}."
    return _llm_fallback(instruction)


class TicketState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    transcript_request: Dict[str, Any]
    analysis: Optional[str]  # From transcript analysis agent
    priority: Optional[str]  # From priority & impact agent
    context: Optional[str]  # From context enrichment agent
    tickets: Optional[List[Dict[str, Any]]]  # Final tickets from synthesis agent
    tool_calls: Annotated[List[Dict[str, Any]], operator.add]


def transcript_analysis_agent(state: TicketState) -> TicketState:
    """Analyze transcript and extract actionable items for Jira tickets."""
    req = state["transcript_request"]
    transcript = req["transcript"]
    meeting_type = req.get("meeting_type", "general")
    
    prompt_t = (
        "You are a transcript analysis expert.\n"
        "Analyze this {meeting_type} meeting transcript and extract all actionable items, "
        "feature requests, bugs, and tasks that should become Jira tickets.\n"
        "Use your tools to extract and categorize each item.\n\n"
        "Transcript excerpt: {transcript_preview}"
    )
    vars_ = {
        "meeting_type": meeting_type,
        "transcript_preview": transcript[:500] + "..." if len(transcript) > 500 else transcript
    }
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [extract_action_items, identify_ticket_type, extract_requirements]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    
    # Agent metadata and prompt template instrumentation
    with using_attributes(tags=["transcript_analysis", "ticket_extraction"]):
        if _TRACING:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("metadata.agent_type", "transcript_analysis")
                current_span.set_attribute("metadata.agent_node", "transcript_analysis_agent")
                current_span.set_attribute("metadata.meeting_type", meeting_type)
        
        with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
            res = agent.invoke(messages)
    
    # Collect tool calls and execute them
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "transcript_analysis", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        
        # Add tool results and ask for synthesis
        messages.append(res)
        messages.extend(tr["messages"])
        
        synthesis_prompt = (
            "Based on the extracted items, provide a structured summary of all potential Jira tickets. "
            "For each ticket, include: title, type, brief description, and why it's important."
        )
        messages.append(SystemMessage(content=synthesis_prompt))
        
        # Instrument synthesis LLM call
        synthesis_vars = {"meeting_type": meeting_type, "context": "tool_results"}
        with using_prompt_template(template=synthesis_prompt, variables=synthesis_vars, version="v1-synthesis"):
            final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "analysis": out, "tool_calls": calls}


def priority_impact_agent(state: TicketState) -> TicketState:
    """Assess priority, effort, and impact for potential tickets."""
    req = state["transcript_request"]
    meeting_type = req.get("meeting_type", "general")
    transcript = req.get("transcript", "")
    
    prompt_t = (
        "You are a prioritization expert.\n"
        "Analyze this transcript and assess potential tickets for:\n"
        "1. Priority (P0-P3) based on urgency and business impact\n"
        "2. Effort estimate (S/M/L/XL) based on complexity\n"
        "3. Business and user impact\n\n"
        "Meeting type: {meeting_type}\n"
        "Transcript excerpt: {transcript_preview}"
    )
    vars_ = {
        "meeting_type": meeting_type,
        "transcript_preview": transcript[:400] + "..." if len(transcript) > 400 else transcript
    }
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [calculate_priority_score, estimate_effort, assess_impact]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    
    # Agent metadata and prompt template instrumentation
    with using_attributes(tags=["priority", "impact_analysis"]):
        if _TRACING:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("metadata.agent_type", "priority")
                current_span.set_attribute("metadata.agent_node", "priority_impact_agent")
        
        with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
            res = agent.invoke(messages)
    
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "priority", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        
        # Add tool results and ask for synthesis
        messages.append(res)
        messages.extend(tr["messages"])
        
        synthesis_prompt = (
            "Provide a prioritized summary of tickets with priority scores (P0-P3), "
            "effort estimates (S/M/L/XL), and impact assessments. Order by priority."
        )
        messages.append(SystemMessage(content=synthesis_prompt))
        
        # Instrument synthesis LLM call
        synthesis_vars = {"meeting_type": meeting_type}
        with using_prompt_template(template=synthesis_prompt, variables=synthesis_vars, version="v1-synthesis"):
            final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "priority": out, "tool_calls": calls}


def context_enrichment_agent(state: TicketState) -> TicketState:
    """Add company-specific context, related tickets, and labels to tickets."""
    req = state["transcript_request"]
    project_key = req.get("project_key", "PROJ")
    transcript = req.get("transcript", "")
    
    # RAG: Retrieve company documentation if enabled
    context_lines = []
    if ENABLE_RAG:
        # Use existing retriever as placeholder for company docs
        # In production, this would query a vector DB of company docs and past tickets
        query = f"{project_key} documentation architecture past tickets"
        retrieved = GUIDE_RETRIEVER.retrieve(query, None, k=2)
        if retrieved:
            context_lines.append("=== Company Context (from knowledge base) ===")
            for idx, item in enumerate(retrieved, 1):
                content = item["content"]
                source = item["metadata"].get("source", "Unknown")
                context_lines.append(f"{idx}. {content}")
                context_lines.append(f"   Source: {source}")
            context_lines.append("=== End of Company Context ===\n")
    
    context_text = "\n".join(context_lines) if context_lines else ""
    
    prompt_t = (
        "You are a context enrichment specialist.\n"
        "Analyze this transcript and suggest for each potential ticket:\n"
        "1. Relevant labels, components, and tags\n"
        "2. Related or potentially duplicate tickets\n"
        "3. References to relevant documentation or architectural decisions\n\n"
        "Project: {project_key}\n"
        "Transcript excerpt: {transcript_preview}"
    )
    
    # Add retrieved context to prompt if available
    if context_text:
        prompt_t += "\n\nRelevant company context:\n{context}\n"
    
    vars_ = {
        "project_key": project_key,
        "transcript_preview": transcript[:300] + "..." if len(transcript) > 300 else transcript,
        "context": context_text if context_text else "No company context available.",
    }
    
    messages = [SystemMessage(content=prompt_t.format(**vars_))]
    tools = [vector_search_company_docs, find_related_tickets, add_labels]
    agent = llm.bind_tools(tools)
    
    calls: List[Dict[str, Any]] = []
    
    # Agent metadata and prompt template instrumentation
    with using_attributes(tags=["context_enrichment", "ticket_metadata"]):
        if _TRACING:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("metadata.agent_type", "context_enrichment")
                current_span.set_attribute("metadata.agent_node", "context_enrichment_agent")
                current_span.set_attribute("metadata.project_key", project_key)
                if ENABLE_RAG and context_text:
                    current_span.set_attribute("metadata.rag_enabled", "true")
        
        with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
            res = agent.invoke(messages)
    
    if getattr(res, "tool_calls", None):
        for c in res.tool_calls:
            calls.append({"agent": "context_enrichment", "tool": c["name"], "args": c.get("args", {})})
        
        tool_node = ToolNode(tools)
        tr = tool_node.invoke({"messages": [res]})
        
        # Add tool results and ask for synthesis
        messages.append(res)
        messages.extend(tr["messages"])
        
        synthesis_prompt = (
            "Provide enriched ticket metadata including recommended labels, components, "
            "related tickets, and documentation references for each ticket."
        )
        messages.append(SystemMessage(content=synthesis_prompt))
        
        # Instrument synthesis LLM call
        synthesis_vars = {"project_key": project_key}
        with using_prompt_template(template=synthesis_prompt, variables=synthesis_vars, version="v1-synthesis"):
            final_res = llm.invoke(messages)
        out = final_res.content
    else:
        out = res.content

    return {"messages": [SystemMessage(content=out)], "context": out, "tool_calls": calls}


def ticket_synthesis_agent(state: TicketState) -> TicketState:
    """Synthesize all agent outputs into structured Jira tickets."""
    req = state["transcript_request"]
    project_key = req.get("project_key", "PROJ")
    auto_submit = req.get("auto_submit", False)
    
    prompt_parts = [
        "Create structured Jira tickets based on the following inputs:",
        "",
        "Analysis: {analysis}",
        "Priority & Impact: {priority}",
        "Context & Metadata: {context}",
        "",
        "Generate a JSON array of tickets with this structure:",
        '[{{"title": "...", "type": "Story|Bug|Task", "priority": "P0-P3", '
        '"effort": "S|M|L|XL", "description": "...", "labels": [...], "component": "..."}}]',
        "",
        "Project: {project_key}",
    ]
    
    prompt_t = "\n".join(prompt_parts)
    vars_ = {
        "analysis": (state.get("analysis") or "")[:400],
        "priority": (state.get("priority") or "")[:400],
        "context": (state.get("context") or "")[:400],
        "project_key": project_key,
    }
    
    # Add span attributes for better observability in Arize
    with using_attributes(tags=["ticket_synthesis", "final_agent"]):
        if _TRACING:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("metadata.agent_type", "ticket_synthesis")
                current_span.set_attribute("metadata.agent_node", "ticket_synthesis_agent")
                current_span.set_attribute("metadata.project_key", project_key)
                current_span.set_attribute("metadata.auto_submit", str(auto_submit))
        
        # Prompt template wrapper for Arize Playground integration
        with using_prompt_template(template=prompt_t, variables=vars_, version="v1"):
            res = llm.invoke([SystemMessage(content=prompt_t.format(**vars_))])
    
    # Parse the LLM response to extract tickets
    # In production, would have more robust JSON parsing
    content = res.content
    tickets = []
    
    # Simple extraction - in production use proper JSON parsing
    # For now, create a structured response
    try:
        import re
        # Try to extract JSON array if present
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            tickets_data = json.loads(json_match.group())
            tickets = tickets_data
    except:
        # Fallback: create a single ticket from the response
        tickets = [{
            "title": "Tickets from meeting",
            "type": "Task",
            "priority": "P2",
            "effort": "M",
            "description": content[:500],
            "labels": [project_key.lower()],
            "component": None
        }]
    
    return {
        "messages": [SystemMessage(content=content)],
        "tickets": tickets
    }


def build_graph():
    """Build the transcript-to-Jira agent workflow graph."""
    g = StateGraph(TicketState)
    g.add_node("analysis_node", transcript_analysis_agent)
    g.add_node("priority_node", priority_impact_agent)
    g.add_node("context_node", context_enrichment_agent)
    g.add_node("synthesis_node", ticket_synthesis_agent)

    # Run analysis, priority, and context agents in parallel
    g.add_edge(START, "analysis_node")
    g.add_edge(START, "priority_node")
    g.add_edge(START, "context_node")
    
    # All three agents feed into the synthesis agent
    g.add_edge("analysis_node", "synthesis_node")
    g.add_edge("priority_node", "synthesis_node")
    g.add_edge("context_node", "synthesis_node")
    
    g.add_edge("synthesis_node", END)

    # Compile without checkpointer to avoid state persistence issues
    return g.compile()


app = FastAPI(title="Transcript-to-Jira Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def serve_frontend():
    here = os.path.dirname(__file__)
    path = os.path.join(here, "..", "frontend", "index.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "frontend/index.html not found"}


@app.get("/health")
def health():
    return {"status": "healthy", "service": "transcript-to-jira-agent"}


# Initialize tracing once at startup, not per request
if _TRACING:
    try:
        space_id = os.getenv("ARIZE_SPACE_ID")
        api_key = os.getenv("ARIZE_API_KEY")
        if space_id and api_key:
            tp = register(space_id=space_id, api_key=api_key, project_name="ai-trip-planner")
            LangChainInstrumentor().instrument(tracer_provider=tp, include_chains=True, include_agents=True, include_tools=True)
            LiteLLMInstrumentor().instrument(tracer_provider=tp, skip_dep_check=True)
    except Exception:
        pass

@app.post("/analyze-transcript", response_model=TranscriptResponse)
def analyze_transcript(req: TranscriptRequest):
    """Analyze meeting transcript and generate Jira tickets."""
    graph = build_graph()
    
    # Generate session ID if not provided
    import uuid
    session_id = req.session_id or str(uuid.uuid4())
    
    # Only include necessary fields in initial state
    # Agent outputs (analysis, priority, context, tickets) will be added during execution
    state = {
        "messages": [],
        "transcript_request": req.model_dump(),
        "tool_calls": [],
    }
    
    # Add session and user tracking attributes to the trace
    user_id = req.user_id
    turn_idx = req.turn_index
    
    # Build attributes for session and user tracking
    attrs_kwargs = {}
    if session_id:
        attrs_kwargs["session_id"] = session_id
    if user_id:
        attrs_kwargs["user_id"] = user_id
    
    # Add turn_index as a custom span attribute if provided
    if turn_idx is not None and _TRACING:
        with using_attributes(**attrs_kwargs):
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("turn_index", turn_idx)
                current_span.set_attribute("meeting_type", req.meeting_type)
            out = graph.invoke(state)
    else:
        with using_attributes(**attrs_kwargs):
            out = graph.invoke(state)
    
    # Extract tickets from the output
    tickets_data = out.get("tickets", [])
    tickets = []
    for t in tickets_data:
        tickets.append(JiraTicket(
            title=t.get("title", "Untitled"),
            type=t.get("type", "Task"),
            priority=t.get("priority", "P2"),
            effort=t.get("effort", "M"),
            description=t.get("description", ""),
            labels=t.get("labels", []),
            component=t.get("component"),
            jira_url=t.get("jira_url")
        ))
    
    return TranscriptResponse(
        session_id=session_id,
        tickets=tickets,
        metadata={
            "meeting_type": req.meeting_type,
            "project_key": req.project_key,
            "action_items_found": len(tickets),
        },
        tool_calls=out.get("tool_calls", [])
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
