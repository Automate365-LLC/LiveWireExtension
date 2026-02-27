from fastapi import FastAPI, WebSocket
from openai import OpenAI
import database
import ghl_api

app = FastAPI()
openai = OpenAI(api_key="") # Get it from .env file

# @app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept() # Tells the server to accept the connection from the frontend
    while True:
        data = await websocket.receive_text() # data = Audio text
        

        client_info = ghl_api.fetch_client_data("client_id") # Will have to update with actual info
        
        ai_response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an AI assistant."},
                {"role": "user", "content": f"Live conversation: {data}, Previous data: {client_info}"}
            ]
        )

        # ^^^ Will need to do some prompt engineering once the application is setup

        await websocket.send_text(ai_response["choices"][0]["message"]["content"]) # Sends the AI's response back to the frontend in real time.
