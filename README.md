## LiveWire AI Co-Pilot

The LiveWire AI Co-Pilot is a specialized browser extension and backend system designed for high-fidelity, real-time audio capture and transcription. It is built to facilitate sales coaching and meeting documentation by capturing dual-stream audio (system/tab audio and microphone) and processing it through OpenAI's Whisper model with minimal latency.

---

##  Key Features

* **Stereo Channel Splitting**: Implements a custom "Mono Force" logic that separates tab audio (left channel) from microphone audio (right channel) to ensure clean, speaker-separated transcription.
* **Optimized Processing Loop**: Uses a high-performance 30k byte buffer strategy to minimize Time-to-First-Byte (TTF), delivering near real-time text updates.
* **Intelligent Noise Gating**: Features calibrated volume thresholds (set at 500 RMS) to filter out background noise and prevent transcription hallucinations when speakers are silent.
* **Automated Evidence Archiving**: Automatically generates a unique, timestamped `session_YYYYMMDD_HHMMSS` folder for every run, containing a full text transcript and a finalized MP3 audio mix.
* **Resource Management**: Includes aggressive cleanup logic to release browser hardware streams (microphone/tab capture) immediately upon session termination to prevent "zombie" processes.

---

##  Project Structure

* **`server.py`**: The core Python backend using WebSockets to receive audio chunks and interface with the OpenAI Whisper API.
* **`background.js`**: The extension Service Worker that orchestrates tab capture and manages the offscreen document lifecycle.
* **`offscreen.js`**: A hidden document that performs the actual `AudioContext` merging of tab and microphone streams.
* **`popup.js`**: The user interface controller, featuring persistent state management via `chrome.storage.local`.
* **`sidepanel.js`**: A real-time UI component that renders live transcriptions with color-coded speaker labels.
* **`manifest.json`**: Configured for Manifest V3 with `tabCapture` and `offscreen` permissions.

---

##  Setup Instructions

### 1. Environment Configuration

Create a `.env` file in the root directory. This file is excluded from version control via `.ignore` to protect credentials.

```bash
OPENAI_API_KEY=your_secret_key_here

```

### 2. Backend Installation

Ensure Python 3.10+ and FFmpeg are installed and added to your system PATH.

```bash
# Install dependencies
pip install -r requirements.txt

```

### 3. Extension Installation

1. Navigate to `chrome://extensions/` in Google Chrome.
2. Toggle **Developer Mode** to ON.
3. Click **Load Unpacked** and select the project root folder.

---

##  Usage Guide

1. **Start the Server**: Open your terminal in the project directory and run `python server.py`. The server will initialize a new Evidence Pack folder.
2. **Select Audio Source**: Open the browser tab you wish to record (e.g., Google Meet, Zoom, or YouTube).
3. **Initiate Capture**: Click the LiveWire extension icon and press **Start Capture**. The extension will request microphone access if not already granted.
4. **Monitor Real-time**: Open the Side Panel to view live transcription updates.
5. **Stop and Save**: Click **Stop Capture** in the extension popup or press `Ctrl+C` in the server terminal to compile the final evidence mix.

---

##  Output & Diagnostics

Upon session completion, the system produces the following in the uniquely generated session folder:

* **`transcript.txt`**: A sequential log of the conversation with timestamps and source labels (TAB/MIC).
* **`output.mp3`**: A compressed, mixed-down stereo recording of the entire session.
* **Terminal Diagnostics**: Real-time RMS volume monitoring for both channels to verify hardware health.

---

##  Troubleshooting

* **FFmpeg Errors**: Ensure FFmpeg is accessible from the command line by running `ffmpeg -version`.
* **Empty Transcripts**: Verify that the audio source (Tab) is playing before starting capture and that your microphone is not muted at the system level.
* **Connection Failures**: Ensure the backend server is running on `127.0.0.1:5000` before initiating the extension capture.

Would you like me to help you run the final Git commands to push this documentation and your code to the Automate365 repository?