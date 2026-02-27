from pymongo import MongoClient
from datetime import datetime
import logging

# Configure logging for database operations
logger = logging.getLogger(__name__)

# Connect to MongoDB
# (Ensure your local MongoDB service is running!)
try:
    client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=2000)
    db = client["AI_Popups"]
    conversations = db["Conversations"]
    # Quick connectivity test
    client.server_info()
except Exception as e:
    logger.warning(f"MongoDB not connected: {e}. Logs will not be saved.")
    conversations = None

def save_conversation(client_id, cards_payload):
    """
    Saves the generated cards to MongoDB for analytics.
    Input: cards_payload (List[Dict]) - The JSON output sent to frontend
    """
    if conversations is None:
        return

    try:
        record = {
            "client_id": client_id,
            "timestamp": datetime.now(),
            "cards": cards_payload  # Stores the full JSON structure
        }
        conversations.insert_one(record)
        logger.info(f"💾 Saved conversation log for {client_id}")
    except Exception as e:
        logger.error(f"Failed to save to DB: {e}")

def get_past_conversations(client_id):
    if conversations is None:
        return []
    return list(conversations.find({"client_id": client_id}, {"_id": 0}))