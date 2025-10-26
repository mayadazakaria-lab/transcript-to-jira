#!/usr/bin/env python3
"""
Test script for the Transcript-to-Jira Agent API
"""
import requests
import json
from pathlib import Path

# API endpoint
BASE_URL = "http://localhost:8000"

def test_health():
    """Test the health endpoint"""
    print("🏥 Testing health endpoint...")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()

def test_analyze_transcript():
    """Test the analyze-transcript endpoint with sample data"""
    print("📝 Testing transcript analysis...")
    
    # Load sample transcript
    transcript_file = Path(__file__).parent / "sample_transcript.txt"
    if transcript_file.exists():
        transcript = transcript_file.read_text()
    else:
        # Fallback sample transcript
        transcript = """
        Product Team Meeting - Sprint Planning
        
        Sarah (PM): We need to fix the dark mode toggle bug on mobile. It's affecting 30% of users.
        Mike (Engineer): That's high priority. Also, dashboard loading is taking 5-8 seconds. We need pagination.
        Lisa (Designer): Users want PDF export feature. It came up in multiple interviews.
        Tom (QA): Don't forget unit tests for the new auth flow.
        
        Action Items:
        - Fix dark mode toggle (Bug, High Priority)
        - Implement dashboard pagination (Critical, P0)
        - Add PDF export (Story, Medium Priority)
        - Add unit tests for auth (Task, High Priority)
        """
    
    # Prepare request payload
    payload = {
        "transcript": transcript,
        "meeting_type": "sprint_planning",
        "project_key": "PROD",
        "auto_submit": False
    }
    
    print(f"Transcript length: {len(transcript)} characters")
    print(f"Meeting type: {payload['meeting_type']}")
    print(f"Project key: {payload['project_key']}")
    print()
    
    # Make API request
    response = requests.post(
        f"{BASE_URL}/analyze-transcript",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Success! Generated {len(data['tickets'])} tickets\n")
        print(f"Session ID: {data['session_id']}")
        print(f"Metadata: {json.dumps(data['metadata'], indent=2)}")
        print("\n" + "="*80)
        print("GENERATED TICKETS:")
        print("="*80 + "\n")
        
        for idx, ticket in enumerate(data['tickets'], 1):
            print(f"Ticket #{idx}:")
            print(f"  Title: {ticket['title']}")
            print(f"  Type: {ticket['type']}")
            print(f"  Priority: {ticket['priority']}")
            print(f"  Effort: {ticket['effort']}")
            print(f"  Description: {ticket['description'][:100]}...")
            print(f"  Labels: {', '.join(ticket['labels'])}")
            if ticket.get('component'):
                print(f"  Component: {ticket['component']}")
            print()
        
        print(f"\nTool Calls: {len(data.get('tool_calls', []))}")
        if data.get('tool_calls'):
            print("\nAgent Tool Usage:")
            for call in data['tool_calls'][:5]:  # Show first 5
                print(f"  - {call.get('agent')}: {call.get('tool')}")
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.text)

def main():
    print("="*80)
    print("Transcript-to-Jira Agent API Test")
    print("="*80 + "\n")
    
    try:
        test_health()
        test_analyze_transcript()
        
        print("\n" + "="*80)
        print("✅ Tests completed!")
        print("="*80)
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Cannot connect to API server")
        print("Make sure the server is running: python backend/main.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()

