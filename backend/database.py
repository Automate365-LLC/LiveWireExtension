from pymongo import MongoClient

# Connects to a MongoDB server | Need to figure out how to connect to our existing Database
client = MongoClient("")
# Assuming we create a database to store the conversations
db = client["AI_Popups"]
conversations = db["Conversations"]

# store conversation
def save_conversation(client_id, text):
    conversations.insert_one({"client_id": client_id, "conversation": text})

# retrieve past conversation
def get_past_conversations(client_id):
    return list(conversations.find({"client_id": client_id}, {"_id": 0}))