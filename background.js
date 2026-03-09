chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_STATUS') {
    sendResponse({ isRecording: false });
    return true;
  }
  if (message.type === 'STOP_ACKNOWLEDGED') {
    sendResponse({ success: true });
    return true;
  }
  if (message.target === 'background' && message.type === 'START_RECORDING') {
    initializeCapture(sendResponse);
    return true;
  }
});

// Poll chrome.storage every 500ms until micPermissionGranted is set (by mic-permission.html)
function waitForMicPermission(timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const interval = setInterval(async () => {
      const stored = await chrome.storage.local.get(['micPermissionGranted', 'micPermissionTime']);
      if (stored.micPermissionGranted) {
        clearInterval(interval);
        resolve(true);
      } else if (Date.now() - start > timeoutMs) {
        clearInterval(interval);
        reject(new Error('Mic permission timed out — did you click Allow?'));
      }
    }, 500);
  });
}

async function initializeCapture(sendResponse) {
  try {
    // Check if mic already granted from a previous session
    const stored = await chrome.storage.local.get(['micPermissionGranted']);

    if (!stored.micPermissionGranted) {
      // Open the permission tab
      chrome.tabs.create({
        url: chrome.runtime.getURL('mic-permission.html'),
        active: true
      });

      // Wait until mic-permission.html writes to storage
      try {
        await waitForMicPermission(60000);
      } catch (e) {
        sendResponse({ success: false, error: e.message });
        return;
      }
    }

    // Ensure offscreen document exists
    const existing = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen.html')]
    });

    if (existing.length === 0) {
      await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
        justification: 'Required for audio capture'
      });
    }

    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      sendResponse({ success: false, error: 'Cannot capture a restricted tab' });
      return;
    }

    const tabUrl = tab.url;

    // Get streamId and send IMMEDIATELY — token expires in ~1s
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });

    await chrome.runtime.sendMessage({
      type: 'INIT_AUDIO',
      target: 'offscreen',
      data: { streamId: streamId, url: tabUrl }
    }).catch((e) => console.warn('INIT_AUDIO send failed:', e));

    sendResponse({ success: true });
  } catch (err) {
    console.error('initializeCapture error:', err);
    sendResponse({ success: false, error: err.message });
  }
}