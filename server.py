from flask import Flask, request, jsonify
from flask_cors import CORS
import openai

app = Flask(__name__)
CORS(app) 

# --- PASTE YOUR API KEY HERE ---
HARDCODED_KEY = "sk" # --- END OF API KEY ---
@app.route('/', methods=['GET'])
def home():
    return "<h1>⚡ Pro Bot is Running!</h1><p>You can close this tab. The bot is now alive in your Chrome Extension.</p>"

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        page_context = data.get('context', '')
        chat_history = data.get('history', [])
        image_data = data.get('image', None)
        
        # 1. System Prompt (Upgraded for noise filtering)
        system_prompt = f"""You are a helpful AI assistant that can see the user's screen. 
        The user is currently looking at a webpage with this text content: {page_context}.
        
        CRITICAL INSTRUCTION: The user is speaking to you using voice-to-text. Sometimes the microphone picks up random background chatter, garbled words, throat clearing, or absolute nonsense. 
        If the user's message appears to be background noise, random fragments lacking intent, or accidental nonsense, YOU MUST REPLY WITH EXACTLY THE WORD "IGNORE" AND NOTHING ELSE. 
        If it is a valid question or statement, respond normally, concisely, and exclusively in text format."""

        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 2. Add past conversation history
        for past_msg in chat_history:
            messages.append(past_msg)
        
        # 3. Create the current user message
        user_content = [{"type": "text", "text": user_message}]
        
        if image_data:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": image_data}
            })

        messages.append({"role": "user", "content": user_content})

        client = openai.OpenAI(api_key=HARDCODED_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini', 
            messages=messages,
            max_tokens=300
        )
        
        return jsonify({'reply': response.choices[0].message.content})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'reply': f"Error: {str(e)}"})

if __name__ == '__main__':
    print("⚡ PRO SERVER RUNNING...")
    app.run(port=5000)