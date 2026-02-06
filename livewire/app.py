from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import openai
import base64
import mimetypes
import io
from PyPDF2 import PdfReader

app = Flask(__name__)
CORS(app)

# --- HARDCODED API KEY ---
HARDCODED_KEY = "sk...." 

# --- PERSISTENT MEMORY STORAGE ---
KNOWLEDGE_BASE = ""

# --- SYSTEM PERSONA ---
BASE_SYSTEM_PROMPT = """
You are 'Little Helper', an enthusiastic, charismatic AI Sales Assistant.
You can see the user's screen if they share it.

YOUR GOAL:
1. If the user sends an image or screen capture, ANALYZE it for sales opportunities or explain what is on screen.
2. Answer questions based on the "KNOWLEDGE BASE" or the Visual Input provided.
3. Be persuasive, brief, and exciting.

FORMATTING RULES:
- Keep responses SHORT (under 2-3 sentences).
- Use emojis and bold text.
- Format options: "🎯 BEST CHOICE:", "🔥 HOT TAKE:", "💎 PREMIUM TIP:"
"""

# --- HTML TEMPLATE (WITH SCREEN SHARE) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sales Bot Widget</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        :root {
            --primary: #6366f1;
            --accent: #ec4899;
            --text: #f8fafc;
            --gradient: linear-gradient(135deg, #6366f1, #ec4899);
        }
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: 'Inter', sans-serif;
            background: transparent;
            min-height: 100vh;
            overflow: hidden;
        }

        /* --- LAUNCHER --- */
        .launcher {
            position: fixed;
            bottom: 30px;
            right: 30px;
            width: 60px;
            height: 60px;
            background: var(--gradient);
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 10px 25px rgba(99, 102, 241, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            transition: all 0.3s;
            animation: pulse 3s infinite;
        }
        .launcher:hover { transform: scale(1.1) rotate(5deg); }
        .launcher span { font-size: 30px; }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(236, 72, 153, 0.7); }
            70% { box-shadow: 0 0 0 15px rgba(236, 72, 153, 0); }
            100% { box-shadow: 0 0 0 0 rgba(236, 72, 153, 0); }
        }

        /* --- WIDGET CONTAINER --- */
        .widget-container {
            position: fixed;
            bottom: 100px;
            right: 30px;
            width: 380px;
            height: 600px;
            background: rgba(30, 41, 59, 0.95);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            z-index: 999;
            opacity: 0;
            transform: translateY(20px) scale(0.95);
            transition: all 0.4s;
            pointer-events: none;
        }
        .widget-container.active { opacity: 1; transform: translateY(0) scale(1); pointer-events: all; }

        .header {
            padding: 20px;
            background: linear-gradient(to right, rgba(99, 102, 241, 0.1), transparent);
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .brand { display: flex; align-items: center; gap: 12px; }
        .avatar { width: 40px; height: 40px; border-radius: 12px; background: var(--gradient); display: flex; justify-content: center; align-items: center; font-size: 20px; }
        .title h2 { font-size: 1rem; color: var(--text); font-weight: 700; }
        .title p { font-size: 0.75rem; color: #94a3b8; }
        .close-btn { background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 1.2rem; }

        /* --- CHAT AREA --- */
        #chat-history {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }
        .msg { display: flex; max-width: 85%; }
        .msg.user { align-self: flex-end; }
        .msg.ai { align-self: flex-start; }
        
        .bubble {
            padding: 12px 16px;
            border-radius: 16px;
            font-size: 0.9rem;
            line-height: 1.5;
        }
        .user .bubble { background: var(--primary); color: white; border-bottom-right-radius: 4px; }
        .ai .bubble { background: rgba(255, 255, 255, 0.05); color: var(--text); border-bottom-left-radius: 4px; }
        
        .msg img {
            max-width: 100%;
            border-radius: 8px;
            margin-bottom: 5px;
            border: 1px solid rgba(255,255,255,0.2);
        }

        /* --- CONTROLS --- */
        .controls {
            padding: 15px;
            background: rgba(15, 23, 42, 0.6);
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .icon-btn {
            background: transparent;
            border: none;
            color: #94a3b8;
            cursor: pointer;
            font-size: 1.2rem;
            padding: 8px;
            border-radius: 8px;
            transition: all 0.2s;
        }
        .icon-btn:hover { background: rgba(255,255,255,0.1); color: var(--accent); }
        .icon-btn.active-screen { color: #10b981; animation: pulseGreen 2s infinite; }

        @keyframes pulseGreen {
            0% { text-shadow: 0 0 0 rgba(16, 185, 129, 0); }
            50% { text-shadow: 0 0 10px rgba(16, 185, 129, 0.5); }
            100% { text-shadow: 0 0 0 rgba(16, 185, 129, 0); }
        }

        #micBtn {
            background: var(--gradient);
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            justify-content: center;
            align-items: center;
            color: white;
            margin-left: auto;
        }
        #micBtn:hover { transform: scale(1.05); }

        /* Hidden video element for capturing screen */
        #screenVideo { display: none; }
        
    </style>
</head>
<body>

    <div class="launcher" id="launcherBtn"><span>⚡</span></div>

    <div class="widget-container" id="widget">
        <div class="header">
            <div class="brand">
                <div class="avatar">🤖</div>
                <div class="title"><h2>Little Helper</h2><p>Visual Sales Assistant</p></div>
            </div>
            <button class="close-btn" id="closeBtn">✕</button>
        </div>

        <div id="chat-history">
            <div class="msg ai"><div class="bubble">👋 I can see! Click the 📺 icon to share your screen.</div></div>
        </div>

        <div class="controls">
            <label class="icon-btn" title="Upload File">
                📎 <input type="file" id="fileInput" style="display:none">
            </label>

            <button class="icon-btn" id="screenBtn" title="Share Screen">📺</button>

            <button id="micBtn">🎤</button>
        </div>
    </div>

    <video id="screenVideo" autoplay></video>
    <canvas id="screenCanvas" style="display:none;"></canvas>

<script>
    // --- UI ELEMENTS ---
    const widget = document.getElementById('widget');
    const launcherBtn = document.getElementById('launcherBtn');
    const closeBtn = document.getElementById('closeBtn');
    const micBtn = document.getElementById('micBtn');
    const screenBtn = document.getElementById('screenBtn');
    const chatHistory = document.getElementById('chat-history');
    const fileInput = document.getElementById('fileInput');
    const screenVideo = document.getElementById('screenVideo');
    const screenCanvas = document.getElementById('screenCanvas');

    let screenStream = null;
    let isScreenSharing = false;

    // Toggle Widget
    launcherBtn.onclick = () => widget.classList.add('active');
    closeBtn.onclick = () => widget.classList.remove('active');

    // --- SCREEN SHARING LOGIC ---
    screenBtn.onclick = async () => {
        if (!isScreenSharing) {
            try {
                // Ask user for permission
                screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
                screenVideo.srcObject = screenStream;
                isScreenSharing = true;
                screenBtn.classList.add('active-screen');
                addBubble("📺 Screen sharing active! I'm watching...", 'ai');
                
                // Handle user stopping share via browser UI
                screenStream.getVideoTracks()[0].onended = () => stopScreenShare();
            } catch (err) {
                console.error("Error sharing screen:", err);
            }
        } else {
            stopScreenShare();
        }
    };

    function stopScreenShare() {
        if (screenStream) {
            screenStream.getTracks().forEach(track => track.stop());
            screenVideo.srcObject = null;
        }
        isScreenSharing = false;
        screenBtn.classList.remove('active-screen');
        addBubble("🛑 Screen sharing stopped.", 'ai');
    }

    function captureScreenFrame() {
        if (!isScreenSharing) return null;
        
        const context = screenCanvas.getContext('2d');
        screenCanvas.width = screenVideo.videoWidth;
        screenCanvas.height = screenVideo.videoHeight;
        context.drawImage(screenVideo, 0, 0, screenCanvas.width, screenCanvas.height);
        return screenCanvas.toDataURL('image/jpeg', 0.7); // Return base64 image
    }

    // --- CHAT LOGIC ---
    let recognition;
    let conversation = [];

    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        
        micBtn.onclick = () => { micBtn.style.background = '#ef4444'; recognition.start(); };
        recognition.onend = () => { micBtn.style.background = ''; };
        
        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            handleInteraction(text);
        };
    }

    async function handleInteraction(text) {
        // 1. Show User Message
        addBubble(text, 'user');

        const formData = new FormData();
        formData.append('message', text);
        formData.append('history', JSON.stringify(conversation));
        
        // 2. CHECK FOR FILE
        if (fileInput.files.length > 0) {
            formData.append('file', fileInput.files[0]);
            addBubble(`📎 Sending file...`, 'user');
        }

        // 3. CHECK FOR SCREEN SHARE
        if (isScreenSharing) {
            const screenShot = captureScreenFrame();
            if (screenShot) {
                formData.append('screen_image', screenShot); // Send the captured frame
                // Optional: Show a tiny thumbnail in chat
                // addImageBubble(screenShot, 'user'); 
            }
        }

        // 4. Send to Backend
        try {
            const res = await fetch('/chat', { method: 'POST', body: formData });
            const data = await res.json();

            if (data.success) {
                addBubble(data.reply, 'ai');
                conversation.push({ role: "user", content: text });
                conversation.push({ role: "assistant", content: data.reply });
                
                const speech = new SpeechSynthesisUtterance(data.reply);
                window.speechSynthesis.speak(speech);
                
                fileInput.value = ''; // Clear file
            }
        } catch (e) {
            addBubble("❌ Connection error.", 'ai');
        }
    }

    function addBubble(text, sender) {
        const div = document.createElement('div');
        div.className = `msg ${sender}`;
        div.innerHTML = `<div class="bubble">${text}</div>`;
        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
    
    function addImageBubble(b64, sender) {
        const div = document.createElement('div');
        div.className = `msg ${sender}`;
        div.innerHTML = `<div class="bubble"><img src="${b64}" width="150"></div>`;
        chatHistory.appendChild(div);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }
</script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def home():
    return render_template_string(HTML_TEMPLATE)

def extract_text_from_file(file_storage):
    filename = file_storage.filename.lower()
    if filename.endswith('.pdf'):
        try:
            pdf_reader = PdfReader(file_storage)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text, False
        except: return "", False
    try:
        file_storage.seek(0)
        return file_storage.read().decode('utf-8'), False
    except: return "", False

@app.route('/chat', methods=['POST'])
def chat():
    global KNOWLEDGE_BASE
    
    try:
        user_message = request.form.get('message', '')
        history_json = request.form.get('history', '[]')
        
        # Screen Capture Data (Base64 string from canvas)
        screen_image_data = request.form.get('screen_image')
        
        import json
        client_history = json.loads(history_json)
        
        uploaded_file = request.files.get('file')
        if uploaded_file:
            content, _ = extract_text_from_file(uploaded_file)
            if content: KNOWLEDGE_BASE += f"\n[FILE DATA]: {content}\n"

        # --- BUILD MESSAGE PAYLOAD ---
        # Current system prompt + knowledge
        sys_prompt = BASE_SYSTEM_PROMPT
        if KNOWLEDGE_BASE: sys_prompt += f"\n\n📕 MEMORY:\n{KNOWLEDGE_BASE}"
        
        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(client_history)

        # Create the user message content block
        user_content = [{"type": "text", "text": user_message}]

        # If we have a screen image, attach it!
        if screen_image_data:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": screen_image_data}
            })
            print("📺 Analyzing Screen Capture...")

        messages.append({"role": "user", "content": user_content})

        client = openai.OpenAI(api_key=HARDCODED_KEY)
        response = client.chat.completions.create(
            model='gpt-4o-mini', # Or gpt-4o for better vision
            messages=messages,
            max_tokens=200
        )
        
        reply = response.choices[0].message.content
        return jsonify({'success': True, 'reply': reply})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("⚡ WIDGET STARTED")
    app.run(debug=True, port=5000)
