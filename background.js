chrome.action.setPopup({ popup: 'popup.html' });

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'HEARTBEAT') {
    sendResponse({ alive: true });
    return true;
  }
  if (message.type === 'GET_STATUS') {
    chrome.storage.local.get(['isRecording', 'resumableUrl', 'resumeWindowEnds'], (data) => {
      const canResume = data.resumableUrl && Date.now() < data.resumeWindowEnds;
      sendResponse({ isRecording: !!data.isRecording, canResume: !!canResume });
    });
    return true;
  }
  if (message.type === 'STOP_ACKNOWLEDGED') {
    chrome.storage.local.set({ isRecording: false, capturedTabId: null, resumableUrl: null, resumeWindowEnds: null });
    chrome.action.setBadgeText({ text: '' });
    sendResponse({ success: true });
    return true;
  }
  if (message.target === 'background' && message.type === 'START_RECORDING') {
    initializeCapture(sendResponse);
    return true;
  }
});

// Trigger 60-second resume window upon tab closure
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { capturedTabId, capturedUrl } = await chrome.storage.local.get(['capturedTabId', 'capturedUrl']);
  
  if (tabId === capturedTabId) {
    console.log('[TAB-CLOSED] Captured tab closed. Starting resume window.');
    
    chrome.storage.local.set({ 
      isRecording: false, 
      capturedTabId: null,
      resumableUrl: capturedUrl,
      resumeWindowEnds: Date.now() + 60000 
    });
    
    try {
      await chrome.runtime.sendMessage({ type: 'STOP_RECORDING', target: 'offscreen' });
    } catch (_) {}
  }
});

// Detect reopened meetings and alert the user
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url) {
    const { resumableUrl, resumeWindowEnds } = await chrome.storage.local.get(['resumableUrl', 'resumeWindowEnds']);
    
    if (resumableUrl && Date.now() < resumeWindowEnds) {
      const savedOrigin = new URL(resumableUrl).origin;
      const currentOrigin = new URL(tab.url).origin;
      
      if (savedOrigin === currentOrigin) {
        chrome.action.setBadgeText({ text: 'RESUME', tabId: tabId });
        chrome.action.setBadgeBackgroundColor({ color: '#FF0000', tabId: tabId });
      }
    } else if (resumeWindowEnds && Date.now() >= resumeWindowEnds) {
      chrome.storage.local.remove(['resumableUrl', 'resumeWindowEnds']);
      chrome.action.setBadgeText({ text: '', tabId: tabId });
    }
  }
});

async function initializeCapture(sendResponse) {
  try {
    chrome.storage.local.remove(['resumableUrl', 'resumeWindowEnds']);
    chrome.action.setBadgeText({ text: '' });

    const existing = await chrome.runtime.getContexts({
      contextTypes: ['OFFSCREEN_DOCUMENT'],
      documentUrls: [chrome.runtime.getURL('offscreen.html')]
    });

    if (existing.length > 0) {
      console.log('[INIT] Offscreen exists. Stopping old capture.');
      try {
        await chrome.runtime.sendMessage({ type: 'STOP_RECORDING', target: 'offscreen' });
      } catch (_) {}
      await new Promise(r => setTimeout(r, 300));
    } else {
      await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
        justification: 'Required for audio capture'
      });
      await new Promise(r => setTimeout(r, 300));
    }

    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      sendResponse({ success: false, error: 'Cannot capture this tab' });
      return;
    }

    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });

    await chrome.runtime.sendMessage({
      type: 'INIT_AUDIO',
      target: 'offscreen',
      data: { streamId: streamId, url: tab.url }
    }).catch((e) => console.warn('INIT_AUDIO send failed:', e));

    await chrome.storage.local.set({ isRecording: true, capturedTabId: tab.id, capturedUrl: tab.url });
    
    chrome.action.setBadgeText({ text: 'REC', tabId: tab.id });
    chrome.action.setBadgeBackgroundColor({ color: '#00FF00', tabId: tab.id });
    
    sendResponse({ success: true });
  } catch (err) {
    console.error('initializeCapture error:', err);
    sendResponse({ success: false, error: err.message });
  }
}