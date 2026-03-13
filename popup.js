const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusDiv = document.getElementById('status');

let isResuming = false;

chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (data) => {
    if (data) {
        updateUI(data.isRecording, data.canResume);
    }
});

startBtn.addEventListener('click', () => {
    statusDiv.innerText = isResuming ? "Resuming session..." : "Starting...";
    startBtn.disabled = true;

    chrome.runtime.sendMessage({ type: 'START_RECORDING', target: 'background' }, (res) => {
        if (chrome.runtime.lastError || !res) {
            statusDiv.innerText = "Error: background not responding";
            startBtn.disabled = false;
            return;
        }
        if (res.success) {
            updateUI(true, false);
        } else {
            statusDiv.innerText = "Error: " + res.error;
            startBtn.disabled = false;
        }
    });
});

stopBtn.addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'STOP_RECORDING', target: 'offscreen' });
    chrome.runtime.sendMessage({ type: 'STOP_ACKNOWLEDGED', target: 'background' });
    updateUI(false, false);
});

function updateUI(recording, canResume) {
    if (recording) {
        statusDiv.innerText = "Recording...";
        startBtn.innerText = "Start Capture";
        startBtn.disabled = true;
        stopBtn.disabled = false;
        isResuming = false;
    } else if (canResume) {
        statusDiv.innerText = "Session paused. Click to reconnect.";
        startBtn.innerText = "Resume Capture";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        isResuming = true;
    } else {
        statusDiv.innerText = "Ready. Join a call and click Start.";
        startBtn.innerText = "Start Capture";
        startBtn.disabled = false;
        stopBtn.disabled = true;
        isResuming = false;
    }
}