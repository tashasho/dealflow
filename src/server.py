"""
FastAPI server to handle Slack events and interactive components.
"""

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn
import json

from src.config import Config
from src.triage import handle_reaction_added, handle_interaction

app = FastAPI()

@app.post("/slack/events")
async def events_handler(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack Event Subscriptions (url_verification, reaction_added)."""
    
    # 1. Parse request body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content={"error": "Invalid JSON"}, status_code=400)

    # 2. Handle URL Verification (for initial setup)
    if body.get("type") == "url_verification":
        return JSONResponse(content={"challenge": body.get("challenge")})

    # 3. Handle Events
    event = body.get("event", {})
    event_type = event.get("type")

    if event_type == "reaction_added":
        # Process in background to avoid styling out
        background_tasks.add_task(handle_reaction_added, event)
    
    return JSONResponse(content={"status": "ok"})


@app.post("/slack/interact")
async def interact_handler(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack Interactive Components (Button clicks)."""
    
    # Slack sends interaction payload as form-encoded 'payload' field
    form = await request.form()
    payload_str = form.get("payload")
    if not payload_str:
        return JSONResponse(content={"error": "Missing payload"}, status_code=400)
        
    payload = json.loads(payload_str)
    
    # Process in background
    background_tasks.add_task(handle_interaction, payload)

    # Immediate acknowledgement required by Slack
    return JSONResponse(content={"status": "ok"})

if __name__ == "__main__":
    uvicorn.run("src.server:app", host="0.0.0.0", port=3000, reload=True)
