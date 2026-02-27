// --- 1. THE DESIGN (CSS) ---
const style = document.createElement('style');
style.innerHTML = `
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    
    #ai-widget-root { position: fixed; bottom: 20px; right: 20px; z-index: 2147483647; font-family: 'Inter', sans-serif; }

    #ai-launcher {
        width: 60px; height: 60px; background: linear-gradient(135deg, #6366f1, #a855f7);
        border-radius: 50%; cursor: pointer; box-shadow: 0 10px 25px rgba(99, 102, 241, 0.6);
        display: flex; align-items: center; justify-content: center; font-size: 30px; color: white;
        transition: transform 0.2s ease;
    }
    #ai-launcher:hover { transform: scale(1.1); }

    #ai-box {
        position: absolute; bottom: 80px; right: 0; width: 360px; height: 550px;
        background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1);
        border-radius: 20px; display: none; flex-direction: column; box-shadow: 0 20px 50px rgba(0,0,0,0.5);
        overflow: hidden; animation: slideUp 0.3s ease-out;
    }
    @keyframes slideUp { from { opacity:0; transform:translateY(20px); } to { opacity:1; transform:translateY(0); } }

    .ai-header {
        padding: 15px; background: linear-gradient(to right, rgba(99, 102, 241, 0.2), transparent);
        border-bottom: 1px solid rgba(255,255,255,0.1); color: white; font-weight: 600;
        display: flex; justify-content: space-between; align-items: center;
    }
    .ai-close { background: none; border: none; color: #94a3b8; font-size: 18px; cursor: pointer; }
    .ai-close:hover { color: white; }

    #ai-history {
        flex: 1; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; gap: 12px;
    }
    .ai-msg {
        max-width: 85%; padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.5; color: #f1f5f9; word-wrap: break-word;
    }
    .ai-user { align-self: flex-end; background: #6366f1; border-bottom-right-radius: 2px; }
    .ai-bot { align-self: flex-start; background: rgba(255,255,255,0.1); border-bottom-left-radius: 2px; }

    .ai-controls {
        padding: 15px; background: rgba(0,0,0,0.2); display: flex; gap: 8px; align-items: center; border-top: 1px solid rgba(255,255,255,0.05);
    }
    #ai-input {
        flex: 1; background: rgba(255,255,255,0.1); border: none; color: white; padding: 10px 14px; border-radius: 20px; outline: none;
    }
    .ai-btn {
        background: none; border: none; font-size: 18px; cursor: pointer; padding: 6px; border-radius: 50%; color: #94a3b8; transition: 0.2s;
    }
    .ai-btn:hover { background: rgba(255,255,255,0.1); color: white; }
    .active-share { color: #ef4444 !important; animation: pulse 2s infinite; }
    .active-mic { color: #10b981 !important; animation: pulse 1s infinite; }

    @keyframes pulse { 0% { text-shadow: 0 0 0 rgba(255, 255, 255, 0); } 70% { text-shadow: 0 0 10px currentColor; } 100% { text-shadow: 0 0 0 rgba(255, 255, 255, 0); } }
`;
document.head.appendChild(style);

// --- 2. THE HTML STRUCTURE ---
const root = document.createElement('div');
root.id = 'ai-widget-root';
root.innerHTML = `
    <div id="ai-launcher">⚡</div>
    <div id="ai-box">
        <div class="ai-header">
            <span>🤖 AI Companion</span>
            <button class="ai-close" id="ai-close">✕</button>
        </div>
        <div id="ai-history">
            <div class="ai-msg ai-bot">👋 I'm here! Click the mic once to enable always-on listening.</div>
        </div>
        <div class="ai-controls">
            <button class="ai-btn" id="ai-share" title="Share Screen">📺</button>
            <button class="ai-btn" id="ai-mic" title="Voice Input">🎤</button>
            <input type="text" id="ai-input" placeholder="Ask me..." autocomplete="off">
            <button class="ai-btn" id="ai-send">➤</button>
        </div>
    </div>
    <video id="ai-video" style="display:none;" autoplay></video>
    <canvas id="ai-canvas" style="display:none;"></canvas>
`;
document.body.appendChild(root);

// --- 3. THE LOGIC ---
const launcher = root.querySelector('#ai-launcher');
const box = root.querySelector('#ai-box');
const closeBtn = root.querySelector('#ai-close');
const sendBtn = root.querySelector('#ai-send');
const shareBtn = root.querySelector('#ai-share');
const micBtn = root.querySelector('#ai-mic');
const input = root.querySelector('#ai-input');
const history = root.querySelector('#ai-history');
const video = root.querySelector('#ai-video');
const canvas = root.querySelector('#ai-canvas');

let isSharing = false;
let screenStream = null;
let chatHistory = [];

launcher.onclick = () => { box.style.display = 'flex'; launcher.style.display = 'none'; };
closeBtn.onclick = () => { box.style.display = 'none'; launcher.style.display = 'flex'; };

function getPageContext() {
    return document.body.innerText.split('\n').map(line => line.trim()).filter(line => line.length > 0).slice(0, 50).join(' ');
}

// --- ALWAYS-ON MICROPHONE LOGIC ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let isActivelyListening = false; // Master switch for continuous listening

if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = true; // 🎙️ Tells the browser to KEEP listening
    recognition.interimResults = false; // Only trigger when a full sentence is formed
    
    recognition.onstart = () => {
        micBtn.classList.add('active-mic');
    };
    
    recognition.onend = () => {
        // 🔄 AUTO-RESTART: If the browser stops it, but we didn't click stop, turn it right back on!
        if (isActivelyListening) {
            try {
                recognition.start();
            } catch(e) {}
        } else {
            micBtn.classList.remove('active-mic');
        }
    };
    
    recognition.onresult = (event) => {
        // Grab the most recently finished sentence
        const current = event.resultIndex;
        const transcript = event.results[current][0].transcript.trim();
        
        if (transcript) {
            input.value = transcript;
            handleSend(); // Automatically send it to the AI to evaluate
        }
    };

    micBtn.onclick = () => {
        isActivelyListening = !isActivelyListening;
        
        if (isActivelyListening) {
            recognition.start();
            addMsg("🎙️ Always-on listening activated. I'll ignore background noise.", 'ai-bot');
        } else {
            recognition.stop();
            addMsg("🔇 Listening paused.", 'ai-bot');
        }
    };
} else {
    micBtn.style.display = 'none'; 
}

// --- SCREEN SHARING ---
shareBtn.onclick = async () => {
    if (!isSharing) {
        try {
            screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
            video.srcObject = screenStream;
            isSharing = true;
            shareBtn.classList.add('active-share');
            addMsg("📺 Screen sharing ON. I am watching.", 'ai-bot');
            screenStream.getVideoTracks()[0].onended = () => stopSharing();
        } catch (e) {
            addMsg("❌ Permission denied.", 'ai-bot');
        }
    } else {
        stopSharing();
    }
};

function stopSharing() {
    if (screenStream) screenStream.getTracks().forEach(track => track.stop());
    isSharing = false;
    shareBtn.classList.remove('active-share');
    addMsg("🛑 Screen sharing stopped.", 'ai-bot');
}

function captureFrame() {
    if (!isSharing) return null;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return canvas.toDataURL('image/jpeg', 0.5); 
}

// --- CHAT LOGIC ---
async function handleSend() {
    const text = input.value.trim();
    if (!text) return;

    // Show what was heard/typed
    addMsg(text, 'ai-user');
    input.value = '';

    const imageData = captureFrame();
    const pageContext = getPageContext();
    
    if (imageData) addMsg("📸 (Checking screen...)", 'ai-user');

    try {
        const response = await fetch('http://127.0.0.1:5000/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, context: pageContext, history: chatHistory, image: imageData })
        });
        
        const data = await response.json();
        const botReply = data.reply;
        
        // --- NOISE FILTER CHECK ---
        // If the AI determined it was just a cough or background chatter, it drops it.
        if (botReply.trim() === "IGNORE") {
            console.log("Filtered out background noise/nonsense.");
            return; 
        }
        
        addMsg(botReply, 'ai-bot');

        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: botReply });
        if (chatHistory.length > 10) chatHistory = chatHistory.slice(chatHistory.length - 10);

    } catch (err) {
        addMsg("❌ Error: Is server.py running?", 'ai-bot');
    }
}

function addMsg(text, type) {
    const div = document.createElement('div');
    div.className = `ai-msg ${type}`;
    div.innerText = text;
    history.appendChild(div);
    history.scrollTop = history.scrollHeight;
}

sendBtn.onclick = handleSend;
input.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSend(); });