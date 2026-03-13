(function () {
  if (window !== window.top) return;
  if (window.__livewireActive) return;
  window.__livewireActive = true;

  const CONFERENCING_DOMAINS = [
    'meet.google.com', 'teams.microsoft.com', 'teams.live.com', 'zoom.us'
  ];
  const hostname = window.location.hostname;
  if (CONFERENCING_DOMAINS.some(d => hostname.includes(d))) return;

  let socket = null;
  let mediaRecorder = null;
  let audioCtx = null;
  let micStream = null;

  function detectPlatform() {
    if (hostname.includes('youtube.com')) return 'youtube';
    return 'video_site';
  }

  function killEverything() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      try { mediaRecorder.stop(); } catch (_) {}
    }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    if (audioCtx && audioCtx.state !== 'closed') {
      try { audioCtx.close(); } catch (_) {}
      audioCtx = null;
    }
    if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
    socket = null;
    mediaRecorder = null;
  }

  async function startCapture(videoEl) {
    if (socket && socket.readyState === WebSocket.OPEN) return;
    killEverything();

    let tabStream;
    try {
      tabStream = videoEl.captureStream();
      if (tabStream.getAudioTracks().length === 0) return;
    } catch (e) {
      return;
    }

    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {}

    audioCtx = new AudioContext();
    const merger = audioCtx.createChannelMerger(2);
    const dest = audioCtx.createMediaStreamDestination();

    const tabAudio = tabStream.getAudioTracks();
    if (tabAudio.length > 0) {
      audioCtx.createMediaStreamSource(new MediaStream(tabAudio)).connect(merger, 0, 0);
    }
    if (micStream) {
      audioCtx.createMediaStreamSource(micStream).connect(merger, 0, 1);
    }
    merger.connect(dest);

    try {
      socket = new WebSocket('ws://127.0.0.1:5000');
    } catch (e) { return; }
    socket.binaryType = 'arraybuffer';

    socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'STT_STATE') {
          let overlay = document.getElementById('livewire-stt-overlay');
          if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'livewire-stt-overlay';
            overlay.style.cssText = 'position:fixed;top:20px;right:20px;z-index:999999;padding:8px 16px;border-radius:4px;font-family:sans-serif;font-weight:bold;font-size:14px;color:white;transition:0.3s;box-shadow:0 4px 6px rgba(0,0,0,0.3);';
            document.body.appendChild(overlay);
          }
          
          if (msg.state === 'reconnecting') {
            overlay.innerText = '⚠️ AI Reconnecting... (Audio saving)';
            overlay.style.background = '#f39c12';
            overlay.style.display = 'block';
          } else if (msg.state === 'connected') {
            overlay.innerText = '🟢 AI Connected';
            overlay.style.background = '#27ae60';
            setTimeout(() => overlay.style.display = 'none', 3000);
          } else if (msg.state === 'failed') {
            overlay.innerText = '❌ AI Offline. Audio still recording.';
            overlay.style.background = '#c0392b';
          }
        }
      } catch (e) {}
    };

    socket.onclose = () => {
      socket = null;
      setTimeout(() => {
        chrome.storage.local.get(['livewireEnabled'], (d) => {
          if (d.livewireEnabled === true) tryCapture();
        });
      }, 5000);
    };

    socket.onopen = () => {
      socket.send(JSON.stringify({
        type: 'PLATFORM_INFO',
        platform: detectPlatform(),
        hostname: hostname,
        session_id: detectPlatform() + '_' + hostname,
        capture_mode: 'content_script_auto',
        browser_version: (navigator.userAgent.match(/Chrome\/([\d.]+)/) || [])[0] || 'unknown'
      }));

      mediaRecorder = new MediaRecorder(dest.stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0 && socket && socket.readyState === WebSocket.OPEN) {
          socket.send(e.data);
        }
      };
      mediaRecorder.start(1000);
      console.log('[LiveWire] Recording');
    };
  }

  function tryCapture() {
    if (socket && socket.readyState === WebSocket.OPEN) return;
    const video = document.querySelector('video');
    if (!video) return;
    if (video.readyState >= 2) startCapture(video);
    else {
      video.addEventListener('loadeddata', () => startCapture(video), { once: true });
      video.addEventListener('playing', () => startCapture(video), { once: true });
    }
  }

  chrome.storage.local.get(['livewireEnabled'], (data) => {
    if (data.livewireEnabled !== true) {
      console.log('[LiveWire] Not enabled. Click Start in popup.');
      return;
    }

    console.log('[LiveWire] Enabled. Looking for video...');

    if (document.querySelector('video')) {
      tryCapture();
    } else {
      const observer = new MutationObserver(() => {
        if (document.querySelector('video')) {
          observer.disconnect();
          tryCapture();
        }
      });
      observer.observe(document.body || document.documentElement, {
        childList: true, subtree: true
      });
    }

    if (hostname.includes('youtube.com')) {
      document.addEventListener('yt-navigate-finish', () => {
        killEverything();
        chrome.storage.local.get(['livewireEnabled'], (d) => {
          if (d.livewireEnabled === true) setTimeout(tryCapture, 1500);
        });
      });
    }
  });

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.livewireEnabled && changes.livewireEnabled.newValue === false) {
      console.log('[LiveWire] Stop signal received.');
      killEverything();
      window.__livewireActive = false;
    }
    if (changes.livewireEnabled && changes.livewireEnabled.newValue === true) {
      console.log('[LiveWire] Start signal received.');
      tryCapture();
    }
  });

  window.addEventListener('beforeunload', killEverything);
})();