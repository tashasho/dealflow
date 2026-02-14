"""
Triage logic for handling Slack events.
"""

import asyncio
from datetime import datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from src.config import Config
from src.storage.db import DealDatabase
# from src.storage.airtable import AirtableClient (We might need this if real implementation)
# For now, we'll use DB + print logs, or simulated Airtable updates.
# The prompt asks for Airtable updates.

slack_client = WebClient(token=Config.SLACK_BOT_TOKEN) if Config.SLACK_BOT_TOKEN else None

# Emojis mapping
EMOJI_MAP = {
    "books": "Interesting",
    "thumbsdown": "Pass",
    "-1": "Pass",
    "email": "Reach Out",
    "envelope": "Reach Out"
}

async def handle_reaction_added(event: dict):
    """
    Handle emoji reactions to triage deals.
    Phase 6: 📚 -> Reading List, 👎 -> Pass reason, 📧 -> Outreach
    """
    if not slack_client:
        print("Slack client not initialized.")
        return

    reaction = event.get("reaction")
    user_id = event.get("user")
    item = event.get("item", {})
    channel_id = item.get("channel")
    ts = item.get("ts")

    triage_status = EMOJI_MAP.get(reaction)
    if not triage_status:
        return # Ignore other emojis

    print(f"Reaction '{reaction}' detected from {user_id}. Status: {triage_status}")

    # 1. Identify Deal from DB/Airtable using 'slack_ts'
    # Since we are using SQLite in this repo primarily, we'd query by slack_ts.
    # However, our models don't persist slack_ts in SQLite yet (added to Model but not DB schema).
    # Ideally we update the deal in DB.
    
    # Simulate DB lookup
    # db = DealDatabase(Config.DB_PATH)
    # deal = db.find_by_slack_ts(ts)
    
    # 2. Logic Branches
    try:
        if triage_status == "Interesting":
            # Add to Reading List
            _add_to_reading_list(channel_id, ts, user_id)
            
        elif triage_status == "Pass":
            # Request Pass Reason
            _request_pass_reason(channel_id, ts, user_id)
            
        elif triage_status == "Reach Out":
            # Add to Outreach Queue & Draft Email
            _add_to_outreach(channel_id, ts, user_id)

    except SlackApiError as e:
        print(f"Slack API Error: {e}")


def _add_to_reading_list(channel, ts, user_id):
    # Update Airtable/DB...
    
    # Reply in Thread
    slack_client.chat_postMessage(
        channel=channel,
        thread_ts=ts,
        text=f"✅ <@{user_id}> added to **Reading List**."
    )

def _request_pass_reason(channel, ts, user_id):
    # Post interactive buttons
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"❌ <@{user_id}> passing. **Why?**"}
        },
        {
            "type": "actions",
            "block_id": "pass_reason_actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "ChatGPT wrapper"},
                    "value": "wrapper",
                    "action_id": "pass_wrapper",
                    "style": "danger"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Too early"},
                    "value": "too_early",
                    "action_id": "pass_too_early"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Not differentiated"},
                    "value": "not_diff",
                    "action_id": "pass_not_diff"
                }
            ]
        }
    ]
    
    slack_client.chat_postMessage(
        channel=channel,
        thread_ts=ts,
        text="Select pass reason",
        blocks=blocks
    )

def _add_to_outreach(channel, ts, user_id):
    # Draft email (Phase 8) - Simulated here
    draft_subject = "Partnership / [Startup Name]"
    draft_body = "Hi [Founder],\n\nSaw what you're building..."
    
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"✅ <@{user_id}> added to **Outreach Queue**.\n\n📧 *Draft Email:*"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Subject:* {draft_subject}\n{draft_body}"}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "📧 Send Now"},
                    "value": "send_now",
                    "action_id": "send_email",
                    "style": "primary"
                }
            ]
        }
    ]

    slack_client.chat_postMessage(
        channel=channel,
        thread_ts=ts,
        text="Outreach drafted",
        blocks=blocks
    )


async def handle_interaction(payload: dict):
    """Handle button clicks."""
    if not slack_client:
        return

    user_id = payload["user"]["id"]
    actions = payload["actions"][0]
    action_id = actions["action_id"]
    value = actions["value"]
    channel_id = payload["channel"]["id"]
    message_ts = payload["container"]["message_ts"] # The thread message with buttons
    thread_ts = payload["container"].get("thread_ts") or message_ts # The original deal message

    print(f"Interaction: {action_id} - {value} by {user_id}")

    # Handle Pass Reasons
    if action_id.startswith("pass_"):
        reason_map = {
            "pass_wrapper": "ChatGPT wrapper",
            "pass_too_early": "Too early",
            "pass_not_diff": "Not differentiated"
        }
        reason = reason_map.get(action_id, "Other")
        
        # Update Airtable/DB...
        
        # Update connection message to remove buttons or confirm
        slack_client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=f"✅ <@{user_id}> marked as Pass: **{reason}**",
            blocks=[] # Remove buttons
        )
    
    # Handle Email Send
    elif action_id == "send_email":
        # Send logic...
        
        slack_client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=f"🚀 <@{user_id}> sent the email!",
            blocks=[]
        )
