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
HARDCODED_KEY = 
# --- SYSTEM PERSONA ---
# This controls how the AI acts and forces it to be short
SYSTEM_PROMPT = """
You are a 'Little Helper'. You are enthusiastic, kind, and helpful.
CRITICAL INSTRUCTION: Keep your responses VERY SHORT (under 2 sentences). 
Do not lecture. Just give the answer or a quick suggestion. 
If you need to summarize a file, do it in bullet points but keep it brief.
"""

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Little Helper Assistant</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Inter', sans-serif;
            background: #0a0a0a; color: #fff;
            min-height: 100vh; display: flex; align-items: center; justify-content: center;
            padding: 20px; overflow: hidden; position: relative;
        }
        body::before {
            content: ''; position: fixed; top: -50%; left: -50%; width: 200%; height: 200%;
            background: radial-gradient(circle at 20% 50%, rgba(120, 119, 198, 0.3), transparent 50%),
                        radial-gradient(circle at 80% 80%, rgba(74, 86, 226, 0.3), transparent 50%);
            z-index: 0;
        }
        .container {
            position: relative; z-index: 1; width: 100%; max-width: 900px;
            background: rgba(20, 20, 25, 0.7); backdrop-filter: blur(40px);
            border-radius: 32px; padding: 48px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .header { text-align: center; margin-bottom: 30px; }
        h1 {
            font-size: 2.5rem; font-weight: 700;
            background: linear-gradient(135deg, #fff 0%, #a78bfa 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        #chat-history {
            height: 400px; overflow-y: auto; padding: 24px; margin-bottom: 20px;
            background: rgba(0, 0, 0, 0.2); border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .msg { margin-bottom: 16px; display: flex; animation: fade 0.4s; }
        @keyframes fade { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .msg-content { max-width: 75%; padding: 14px 18px; border-radius: 18px; font-size: 0.95rem; line-height: 1.5; }
        .user-msg { justify-content: flex-end; }
        .user-msg .msg-content { background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); color: #fff; }
        .ai-msg { justify-content: flex-start; }
        .ai-msg .msg-content { background: rgba(255, 255, 255, 0.08); border: 1px solid rgba(255, 255, 255, 0.1); }
        
        .controls { display: flex; gap: 12px; justify-content: center; align-items: center; flex-wrap: wrap; }
        button { padding: 16px 30px; border: none; border-radius: 16px; cursor: pointer; font-weight: 600; transition: all 0.2s; }
        #startBtn { background: #7c3aed; color: white; flex: 1; min-width: 150px; }
        #stopBtn { background: #ef4444; color: white; display: none; flex: 1; min-width: 150px; }
        #clearBtn { background: rgba(255,255,255,0.1); color: white; }
        
        .file-wrapper { position: relative; }
        input[type="file"] { display: none; }
        .file-btn {
            background: rgba(255,255,255,0.1); color: white; padding: 16px; border-radius: 16px;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .file-btn:hover { background: rgba(255,255,255,0.2); }
        .file-btn.has-file { background: #22c55e; border-color: #22c55e; }
        .file-preview {
            position: absolute; bottom: 110%; left: 0; background: #22c55e; color: black;
            padding: 4px 8px; border-radius: 8px; font-size: 0.75rem; white-space: nowrap; display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Little Helper</h1>
            <div class="subtitle">Fast, Short, & Helpful</div>
        </div>

        <div id="chat-history"></div>

        <div class="controls">
            <div class="file-wrapper">
                <div id="filePreview" class="file-preview"></div>
                <label for="fileInput" class="file-btn" id="fileBtnLabel">📎</label>
                <input type="file" id="fileInput">
            </div>
            <button id="startBtn">Start Listening</button>
            <button id="stopBtn">Stop</button>
            <button id="clearBtn">Clear</button>
        </div>
    </div>

<script>
    const BACKEND_URL = '/chat';
    const chatHistory = document.getElementById('chat-history');
    const startBtn = document.getElementById('startBtn');
    const stopBtn = document.getElementById('stopBtn');
    const fileInput = document.getElementById('fileInput');
    const fileBtnLabel = document.getElementById('fileBtnLabel');
    const filePreview = document.getElementById('filePreview');
    
    let recognition;
    let isActive = false;
    let isAiTalking = false;
    let conversation = [];

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            fileBtnLabel.classList.add('has-file');
            filePreview.textContent = fileInput.files[0].name;
            filePreview.style.display = 'block';
        } else {
            fileBtnLabel.classList.remove('has-file');
            filePreview.style.display = 'none';
        }
    });

    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onstart = () => { if (isActive && !isAiTalking) console.log("Listening..."); };
        recognition.onend = () => { 
            if (isActive && !isAiTalking) setTimeout(() => { try { recognition.start(); } catch(e){} }, 200); 
        };
        recognition.onresult = (event) => {
            const lastResult = event.results[event.results.length - 1];
            if (lastResult.isFinal) {
                const text = lastResult[0].transcript;
                if (text.trim()) handleUserInput(text);
            }
        };
    } else { alert('Speech recognition not supported. Use Chrome.'); }

    function speak(text) {
        isAiTalking = true;
        recognition.stop();
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.1;
        utterance.onend = () => {
            isAiTalking = false;
            if (isActive) setTimeout(() => { try { recognition.start(); } catch(e){} }, 300);
        };
        window.speechSynthesis.speak(utterance);
    }

    async function handleUserInput(text) {
        isAiTalking = true;
        recognition.stop();
        addMessage(text, 'user-msg');

        const formData = new FormData();
        formData.append('message', text);
        formData.append('history', JSON.stringify(conversation));
        
        if (fileInput.files.length > 0) {
            formData.append('file', fileInput.files[0]);
            addMessage(`[Uploaded: ${fileInput.files[0].name}]`, 'user-msg');
        }

        try {
            const response = await fetch(BACKEND_URL, { method: 'POST', body: formData });
            const data = await response.json();
            
            if (data.error) throw new Error(data.error);

            conversation.push({ role: "user", content: text });
            conversation.push({ role: "assistant", content: data.reply });
            
            addMessage(data.reply, 'ai-msg');
            speak(data.reply);

            fileInput.value = '';
            fileBtnLabel.classList.remove('has-file');
            filePreview.style.display = 'none';

        } catch (err) {
            console.error(err);
            addMessage("Error processing request.", 'ai-msg');
            speak("Sorry, I had trouble with that.");
            isAiTalking = false;
        }
    }

    function addMessage(text, className) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `msg ${className}`;
        msgDiv.innerHTML = `<div class="msg-content">${text}</div>`;
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    startBtn.onclick = () => {
        isActive = true;
        startBtn.style.display = 'none';
        stopBtn.style.display = 'block';
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(''));
        try { recognition.start(); } catch (e) {}
    };

    stopBtn.onclick = () => {
        isActive = false;
        isAiTalking = false;
        startBtn.style.display = 'block';
        stopBtn.style.display = 'none';
        window.speechSynthesis.cancel();
        try { recognition.stop(); } catch (e) {}
    };

    document.getElementById('clearBtn').onclick = () => {
        chatHistory.innerHTML = '';
        conversation = [];
    };
</script>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def home():
    return render_template_string(HTML_TEMPLATE)

def extract_text_from_file(file_storage):
    filename = file_storage.filename.lower()
    
    # 1. Handle PDF
    if filename.endswith('.pdf'):
        try:
            pdf_reader = PdfReader(file_storage)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text, False
        except Exception as e:
            raise Exception(f"Failed to read PDF: {str(e)}")

    # 2. Handle Image
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type and mime_type.startswith('image'):
        file_storage.seek(0)
        image_data = base64.b64encode(file_storage.read()).decode('utf-8')
        return f"data:{mime_type};base64,{image_data}", True

    # 3. Handle Text/Code
    try:
        file_storage.seek(0)
        return file_storage.read().decode('utf-8'), False
    except UnicodeDecodeError:
        raise Exception("File type not supported. Please upload Text, PDF, or Images.")

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_message = request.form.get('message', '')
        history_json = request.form.get('history', '[]')
        
        import json
        client_history = json.loads(history_json)
        
        uploaded_file = request.files.get('file')
        new_user_content = []
        new_user_content.append({"type": "text", "text": user_message})

        if uploaded_file:
            print(f"Processing file: {uploaded_file.filename}")
            try:
                content, is_image = extract_text_from_file(uploaded_file)
                
                if is_image:
                    new_user_content.append({
                        "type": "image_url",
                        "image_url": {"url": content}
                    })
                else:
                    file_context = f"\n\n--- FILE CONTENT ({uploaded_file.filename}) ---\n{content}\n--- END FILE ---\n"
                    new_user_content[0]['text'] += file_context
                    
            except Exception as e:
                return jsonify({'error': str(e)}), 400

        # --- CONSTRUCT MESSAGES WITH SYSTEM PROMPT ---
        final_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        final_messages.extend(client_history) # Add history
        final_messages.append({"role": "user", "content": new_user_content}) # Add new message

        client = openai.OpenAI(api_key=HARDCODED_KEY)
        
        print("Sending to OpenAI...")
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=final_messages,
            max_tokens=150  # <--- LIMITS RESPONSE LENGTH TO BE FAST
        )
        
        reply = response.choices[0].message.content
        return jsonify({'success': True, 'reply': reply})

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("📍 Running at: http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
