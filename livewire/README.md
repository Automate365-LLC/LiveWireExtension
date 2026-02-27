# Real-Time AI Sales Assistant

A FastAPI app for real-time sales call transcription and AI-powered suggestions.

## Features

- Real-time audio transcription (OpenAI Whisper)
- AI sales suggestions (OpenAI GPT)
- Client info upload and context
- Modern web UI

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Set your OpenAI API key as an environment variable:
   ```
   export OPENAI_API_KEY=your-key-here
   ```

3. Run the app:
   ```
   uvicorn app:app --reload
   ```

4. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Notes

- Requires Python 3.8+
- Do **not** commit your OpenAI API key to GitHub!

