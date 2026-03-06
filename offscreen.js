let socket;
let mediaRecorder;
let globalMicStream;
let globalTabStream;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.target === 'offscreen' && msg.type === 'INIT_AUDIO') {
        startCapture(msg.data.streamId, msg.data.url);
        sendResponse({ success: true });
    }
    if (msg.target === 'offscreen' && msg.type === 'STOP_RECORDING') {
        stopCapture();
    }
});

function stopCapture() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop();
    if (globalMicStream) globalMicStream.getTracks().forEach(t => t.stop());
    if (globalTabStream) globalTabStream.getTracks().forEach(t => t.stop());
    if (socket && socket.readyState === WebSocket.OPEN) socket.close();
}

async function startCapture(streamId, tabUrl) {
    socket = new WebSocket('ws://127.0.0.1:5000');
    socket.binaryType = 'arraybuffer';
    socket.onerror = (e) => console.error('[WS] Socket error:', e);

    socket.onopen = async () => {
        console.log('[WS] Socket open. tabUrl =', tabUrl);

        // Detect platform
        let platform = "unknown";
        let hostname = "unknown";
        let browser_version = "unknown";
        try {
            const url = (tabUrl || "").toString();
            if (url.includes("meet.google.com"))           platform = "meet";
            else if (url.includes("zoom.us"))              platform = "zoom";
            else if (url.includes("teams.microsoft.com") ||
                     url.includes("teams.live.com"))       platform = "teams";
            else if (url.includes("youtube.com"))          platform = "youtube";
            else if (url.includes("webex.com"))            platform = "webex";
            else if (url.includes("whereby.com"))          platform = "whereby";
            hostname = url ? new URL(url).hostname : "unknown";
            const m = navigator.userAgent.match(/Chrome\/([\d.]+)/);
            browser_version = m ? "Chrome/" + m[1] : "unknown";
        } catch (e) {
            console.error('[Platform] Detection failed:', e);
        }

        console.log(`[Platform] ${platform} | host: ${hostname}`);

        // Send handshake
        try {
            socket.send(JSON.stringify({
                type: "PLATFORM_INFO",
                platform: platform,
                hostname: hostname,
                capture_mode: "dual_channel_stt_bridge",
                browser_version: browser_version
            }));
            console.log('[WS] PLATFORM_INFO sent.');
        } catch (e) {
            console.error('[WS] Failed to send PLATFORM_INFO:', e);
        }

        await new Promise(r => setTimeout(r, 100));

        // Capture both tab + mic
        try {
            // Tab audio — uses streamId, no permission needed
            globalTabStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    mandatory: {
                        chromeMediaSource: 'tab',
                        chromeMediaSourceId: streamId
                    }
                }
            });
            console.log('[Capture] Tab stream acquired.');

            // Mic audio — requires chrome-extension://ID whitelisted in chrome://settings/content/microphone
            globalMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log('[Capture] Mic stream acquired.');

            // Merge both into stereo: left = tab, right = mic
            const ctx    = new AudioContext();
            const merger = ctx.createChannelMerger(2);
            const dest   = ctx.createMediaStreamDestination();
            ctx.createMediaStreamSource(globalTabStream).connect(merger, 0, 0);
            ctx.createMediaStreamSource(globalMicStream).connect(merger, 0, 1);
            merger.connect(dest);

            mediaRecorder = new MediaRecorder(dest.stream, { mimeType: 'audio/webm;codecs=opus' });
            mediaRecorder.ondataavailable = (e) => {
                if (e.data.size > 0 && socket.readyState === WebSocket.OPEN) {
                    socket.send(e.data);
                }
            };
            mediaRecorder.start(1000);
            console.log('[Recorder] Started — dual channel (tab + mic).');

            // Play tab audio back so user still hears the meeting
            const audio = new Audio();
            audio.srcObject = globalTabStream;
            audio.play();

        } catch (e) {
            console.error('[Capture] Failed:', e);
            try {
                socket.send(JSON.stringify({ type: 'CAPTURE_ERROR', error: e.name, message: e.message }));
            } catch (_) {}
        }
    };
}