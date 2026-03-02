chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Handle status requests from the popup
  if (message.type === 'GET_STATUS') {
    sendResponse({ isRecording: false });
    return true; 
  }

  // Handle stop acknowledgments
  if (message.type === 'STOP_ACKNOWLEDGED') {
    sendResponse({ success: true });
    return true;
  }

  // Process recording initiation
  if (message.target === 'background' && message.type === 'START_RECORDING') {
    initializeCapture(sendResponse);
    return true; 
  }
});

async function initializeCapture(sendResponse) {
  try {
    const existing = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen.html')]
    });

    // Create offscreen document if it doesn't exist
    if (existing.length === 0) {
      await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'], 
        justification: 'Required for audio capture and processing'
      });
    }

    // Identify active tab for capture
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || tab.url.startsWith('chrome://')) {
      sendResponse({ success: false, error: "Cannot capture a restricted tab" });
      return;
    }

    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });

    // Hand off stream ID to offscreen document
    setTimeout(() => {
      chrome.runtime.sendMessage({ 
        type: 'INIT_AUDIO', 
        target: 'offscreen', 
        data: streamId 
      }).catch(() => {});
    }, 1000);

    sendResponse({ success: true });
  } catch (err) {
    sendResponse({ success: false, error: err.message });
  }
}