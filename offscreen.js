// offscreen.js
let socket;
let mediaRecorder;

// 🛠️ SPRINT 6 FIX 3: Store the streams globally so we can kill them later
let globalMicStream;
let globalTabStream;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.target === 'offscreen' && msg.type === 'INIT_AUDIO') {
        startCapture(msg.data);
        sendResponse({ success: true });
    }
    // 🛠️ SPRINT 6 FIX 3: Handle the STOP command from popup.js
    if (msg.target === 'offscreen' && msg.type === 'STOP_RECORDING') {
        stopCapture();
    }
});

// 🛠️ SPRINT 6 FIX 3: The aggressive shutdown sequence
function stopCapture() {
    console.log("Stopping capture and releasing tracks...");
    
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
    
    if (globalMicStream) {
        globalMicStream.getTracks().forEach(track => track.stop());
    }
    
    if (globalTabStream) {
        globalTabStream.getTracks().forEach(track => track.stop());
    }
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
    }
}

async function startCapture(streamId) {
    socket = new WebSocket('ws://127.0.0.1:5000');
    socket.binaryType = 'arraybuffer';
    
    socket.onopen = async () => {
        try {
            // 🛠️ SPRINT 6 FIX 3: Assign streams to the global variables
            globalMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            globalTabStream = await navigator.mediaDevices.getUserMedia({
                audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } }
            });

            const ctx = new AudioContext();
            if (ctx.state === 'suspended') await ctx.resume();

            const merger = ctx.createChannelMerger(2);
            const dest = ctx.createMediaStreamDestination();

            ctx.createMediaStreamSource(globalTabStream).connect(merger, 0, 0); // Left
            ctx.createMediaStreamSource(globalMicStream).connect(merger, 0, 1); // Right
            merger.connect(dest);

            mediaRecorder = new MediaRecorder(dest.stream, { mimeType: 'audio/webm;codecs=opus' });
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0 && socket.readyState === 1) socket.send(e.data);
            };
            mediaRecorder.start(1000);
            
            const audio = new Audio();
            audio.srcObject = globalTabStream;
            audio.play();
        } catch (e) { console.error("Mic Capture Failed:", e); }
    };
}