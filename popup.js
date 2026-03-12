const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusDiv = document.getElementById('status');

chrome.storage.local.get(['isRecording'], (res) => {
    updateUI(!!res.isRecording);
});

startBtn.addEventListener('click', () => {
    statusDiv.innerText = "Starting...";

    chrome.runtime.sendMessage({ type: 'START_RECORDING', target: 'background' }, (res) => {
        if (chrome.runtime.lastError || !res) {
            statusDiv.innerText = "Background service error.";
            return;
        }
        if (res.success) {
            chrome.storage.local.set({ isRecording: true }, () => updateUI(true));
        } else {
            statusDiv.innerText = "Error: " + res.error;
        }
    });
});

stopBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'STOP_RECORDING', target: 'offscreen' });
    chrome.runtime.sendMessage({ type: 'STOP_ACKNOWLEDGED', target: 'background' });

    chrome.storage.local.set({ isRecording: false }, () => {
        updateUI(false);
        statusDiv.innerText = "Stopped.";
    });
});

function updateUI(recording) {
    if (recording) {
        statusDiv.innerText = "Recording active";
        startBtn.disabled = true;
        stopBtn.disabled = false;
    } else {
        statusDiv.innerText = "Ready";
        startBtn.disabled = false;
        stopBtn.disabled = true;
    }
}