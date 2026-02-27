import requests

# Not sure how the GHL stuff works. Assuming that we need to get the API keys for them
GHL_API_KEY = "your-ghl-api-key"
GHL_BASE_URL = "https://api.gohighlevel.com/v1"

# Function to fetch client's past info
def fetch_client_data(client_id):
    response = requests.get(f"{GHL_BASE_URL}/contacts/{client_id}", headers={
        "Authorization": f"Bearer {GHL_API_KEY}"
    })
    return response.json() if response.status_code == 200 else {} # returns the contact's (client's) info
