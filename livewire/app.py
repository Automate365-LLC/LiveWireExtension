from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pypdf import PdfReader
import uvicorn
import tempfile
import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
from fastapi import FastAPI
from services.a365_integration import push_to_a365
from services.guardrails import GuardrailEngine

app = FastAPI()
guardrails = GuardrailEngine()

@app.post("/api/a365/push")
async def a365_push_endpoint(payload: dict):
    try:
        summary = payload.get("summary", "")
        tasks = payload.get("tasks", [])
        tags = payload.get("tags", [])
        
        result = push_to_a365(summary, tasks, tags)
        
        return {
            "status": "success",
            "pushed": result,
            "mock": True
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

@app.post("/api/objection-detected")
async def handle_objection(objection_data: dict):
    objection_type = objection_data.get("type")
    
    if not guardrails.should_show_card(objection_type):
        return {"status": "blocked", "reason": "guardrails"}
    
    return {"status": "show_card", "data": objection_data}

@app.post("/api/guardrails/reset")
async def reset_guardrails():
    guardrails.reset()
    return {"status": "reset"}
# Initialize OpenAI client
# REPLACE WITH YOUR KEY or set OPENAI_API_KEY environment variable
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global storage - per session/ call
active_sessions: Dict[str, Dict] = {}
client_info: Dict[str, str] = {}
conversation_history: List[Dict] = []
current_call_transcript: List[Dict] = []

@app.get("/")
def serve_index():
    """Serve the HTML interface"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Error: index.html not found</h1>")

@app.post("/upload_client_info")
async def upload_client_info(file: UploadFile = File(None), client_name: str = Form(None), client_notes: str = Form(None)):
    """Upload client information (PDF or text notes)"""
    global client_info
    
    try:
        client_id = client_name or "default_client"
        client_context = ""
        
        if file and file.filename.lower().endswith('.pdf'):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            reader = PdfReader(tmp_path)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            client_context = "\n\n".join(text_parts)
            os.unlink(tmp_path)
        
        if client_notes:
            client_context += f"\n\nAdditional Notes:\n{client_notes}"
        
        client_info[client_id] = client_context
        
        return JSONResponse({
            "status": "success",
            "message": f"Client information loaded for {client_id}",
            "client_id": client_id
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Failed to process client info: {str(e)}"})

@app.post("/transcribe_audio")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe audio to text using Whisper"""
    tmp_path = None
    try:
        file_ext = ".webm"
        if file.filename:
            if file.filename.endswith('.wav'):
                file_ext = ".wav"
            elif file.filename.endswith('.mp3'):
                file_ext = ".mp3"
            elif file.filename.endswith('.m4a'):
                file_ext = ".m4a"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            content = await file.read()
            if len(content) == 0:
                return JSONResponse({"status": "error", "message": "Empty audio file"})
            tmp.write(content)
            tmp_path = tmp.name
        
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
                temperature=0.0
            )
        
        try:
            os.unlink(tmp_path)
            tmp_path = None
        except:
            pass
        
        text = transcription.text.strip() if hasattr(transcription, 'text') and transcription.text else str(transcription).strip()
        
        if not text:
            return JSONResponse({"status": "error", "message": "No transcription text received"})
        
        return JSONResponse({
            "status": "success",
            "text": text
        })
        
    except Exception as e:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except:
                pass
        return JSONResponse({"status": "error", "message": f"Transcription failed: {str(e)}"})

@app.post("/submit_transcript")
async def submit_transcript(text: str = Form(...)):
    """
    Append a new piece of transcript to the history.
    This is separated from analysis to prevent data duplication.
    """
    global current_call_transcript, conversation_history
    
    timestamp = datetime.now().isoformat()
    
    # Add to internal call state
    current_call_transcript.append({
        "text": text,
        "timestamp": timestamp
    })
    
    # Add to history log
    conversation_history.append({
        "role": "user",
        "content": text,
        "timestamp": timestamp
    })
    
    return JSONResponse({"status": "success"})

@app.post("/analyze_conversation")
async def analyze_conversation(client_id: str = Form("default_client")):
    """Real-time conversation analysis based on current server state"""
    global client_info, current_call_transcript
    
    try:
        if not current_call_transcript:
            return JSONResponse({
                "status": "success",
                "message": "No transcript to analyze yet"
            })

        # Use more recent context for better real-time suggestions
        # We take the last 15 chunks to ensure we have enough context
        recent_transcript = "\n".join([t["text"] for t in current_call_transcript[-15:]])
        
        system_message = """You are an AI sales co-pilot providing real-time assistance during a live sales conversation. 
Your goal is to be helpful and proactive, offering useful insights and suggestions to help the sales rep succeed.

Provide helpful suggestions when you notice:
1. Customer objections, concerns, or hesitations that need addressing
2. Questions from the customer that need clear answers
3. Opportunities to advance the sale or move to next steps
4. Important pain points or needs the customer expresses
5. Moments where the sales rep could benefit from guidance
6. Natural conversation transitions where a helpful response would be valuable
7. Key information about the customer that should be remembered or acted upon

Be proactive but not overwhelming. For normal flowing conversation, provide brief, helpful context or reminders.
For important moments (objections, questions, opportunities), provide more detailed guidance.

Your response MUST be in JSON format:
{
  "suggestion": "Brief, helpful context about what's happening in the conversation",
  "key_points": ["Key insight 1", "Key insight 2"],
  "recommended_response": "A helpful phrase or question the sales rep could say next (if relevant)",
  "insight_type": "objection_handling|next_step|key_info|response_suggestion|close_opportunity"
}

Even for normal conversation, provide brief helpful context. Only leave fields empty if the transcript is truly unclear or just noise."""
        
        context_text = ""
        if client_id in client_info and client_info[client_id]:
            context_preview = client_info[client_id][:2000]
            context_text = f"\n\nCLIENT CONTEXT:\n{context_preview}\n"
        
        user_message = f"""Here's the recent conversation transcript:

{recent_transcript}
{context_text}

Analyze this conversation and provide helpful, actionable suggestions. What's happening? What should the sales rep be aware of or consider saying next? Be helpful and proactive."""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=400,
            temperature=0.8,
            response_format={"type": "json_object"}
        )
        
        try:
            analysis_content = response.choices[0].message.content
            analysis = json.loads(analysis_content)
        except json.JSONDecodeError:
            analysis = {
                "suggestion": analysis_content[:200] if analysis_content else "Analysis completed",
                "key_points": [],
                "recommended_response": "",
                "insight_type": "response_suggestion"
            }
        
        return JSONResponse({
            "status": "success",
            "analysis": analysis,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        })

@app.post("/clear_context")
async def clear_context():
    """Clear conversation history"""
    global conversation_history, current_call_transcript
    conversation_history = []
    current_call_transcript = []
    return JSONResponse({"status": "success", "message": "Context cleared"})

@app.post("/start_call")
async def start_call(client_id: str = Form("default_client")):
    """Initialize a new call session"""
    global current_call_transcript, active_sessions
    call_id = f"call_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    current_call_transcript = []
    active_sessions[call_id] = {
        "client_id": client_id,
        "start_time": datetime.now().isoformat(),
        "transcript": []
    }
    return JSONResponse({
        "status": "success",
        "call_id": call_id,
        "message": "Call session started"
    })

@app.post("/end_call")
async def end_call(call_id: str = Form(...)):
    """End call and get summary"""
    global active_sessions, current_call_transcript
    
    try:
        full_transcript = "\n".join([t["text"] for t in current_call_transcript])
        
        summary_prompt = f"""Analyze this sales call and provide:
1. Key discussion points
2. Customer pain points identified
3. Next steps agreed upon
4. Concerns or objections raised
5. Overall call sentiment

TRANSCRIPT:
{full_transcript[:4000]}

Provide a concise summary in bullet format."""
        
        summary_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a sales analytics AI. Provide clear, actionable call summaries."},
                {"role": "user", "content": summary_prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )
        
        summary = summary_response.choices[0].message.content
        
        if call_id in active_sessions:
            active_sessions[call_id]["end_time"] = datetime.now().isoformat()
            active_sessions[call_id]["summary"] = summary
        
        return JSONResponse({
            "status": "success",
            "summary": summary,
            "transcript_length": len(current_call_transcript)
        })
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)})

@app.get("/get_history")
async def get_history():
    """Get conversation history"""
    return JSONResponse({
        "status": "success",
        "history": conversation_history,
        "has_context": bool(client_info)
    })

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🚀 Real-Time AI Sales Assistant Starting...")
    print("="*70)
    print("\n✨ Features:")
    print("   - Real-time continuous conversation")
    print("   - AI-powered sales recommendations")
    print("   - Client information context")
    print("   - Live suggestions during calls")
    print("\n🌐 Open in browser: http://127.0.0.1:8000")
    print("="*70 + "\n")
    
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)