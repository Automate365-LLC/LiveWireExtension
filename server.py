import asyncio, os, subprocess, websockets, wave, json, struct, math, time
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Create unique session folder for each run
sid = datetime.now().strftime("%Y%m%d_%H%M%S")
session_dir = f"session_{sid}"

transcript_path = os.path.join(session_dir, "transcript.txt")
raw_path = os.path.join(session_dir, "capture.webm")
final_path = os.path.join(session_dir, "output.mp3")

last_frame_time = 0

def init_workspace():
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)
        
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"Session ID: {sid}\n" + "-" * 30 + "\n")
    
    open(raw_path, "wb").close()
    print(f"Session started in {session_dir}")

def get_rms(file):
    try:
        with wave.open(file, 'rb') as wf:
            data = wf.readframes(wf.getnframes())
            if not data: return 0
            count = len(data) // 2
            shorts = struct.unpack("<%dh" % count, data)
            sum_sq = sum(s**2 for s in shorts)
            return math.sqrt(sum_sq / count) if count > 0 else 0
    except:
        return 0

async def log_and_relay(ws, event, status, text=None):
    ts = datetime.now().strftime('%H:%M:%S')
    log = f"[{ts}] {text}\n" if text else f"[{ts}] [DIAG] {status}\n"
        
    with open(transcript_path, "a", encoding="utf-8") as f:
        f.write(log)
        f.flush()

    msg = {"type": event, "status": status, "timestamp": ts}
    if text: msg["data"] = text
    try: await ws.send(json.dumps(msg))
    except: pass

async def process_audio(audio_file, ws, label):
    if not os.path.exists(audio_file): return
    
    vol = get_rms(audio_file)
    
    # Noise gate thresholds
    if vol < 500:
        return 

    try:
        t0 = time.time()
        with open(audio_file, "rb") as f:
            res = client.audio.transcriptions.create(
                model="whisper-1", 
                file=f, 
                response_format="text"
            )
        text = res.strip()
        
        if len(text) > 2:
            ttf = time.time() - t0
            print(f"{label} | TTF: {ttf:.2f}s | Vol: {int(vol)} | {text}")
            await log_and_relay(ws, "TRANSCRIPT_UPDATE", "HEALTHY", f"{label}: {text}")
    except Exception as e:
        print(f"Transcription Error: {e}")

async def monitor_connection(ws):
    global last_frame_time
    state = "HEALTHY"
    while True:
        await asyncio.sleep(1)
        if last_frame_time == 0: continue 
        diff = asyncio.get_event_loop().time() - last_frame_time
        if diff > 3.0 and state != "NO_FRAMES":
            await log_and_relay(ws, "HEALTH_UPDATE", "NO_FRAMES")
            state = "NO_FRAMES"
        elif diff <= 3.0 and state == "NO_FRAMES":
            await log_and_relay(ws, "HEALTH_UPDATE", "HEALTHY")
            state = "HEALTHY"

async def socket_handler(ws):
    global last_frame_time
    print(f"Client connected at {datetime.now().strftime('%H:%M:%S')}")
    buffer, header = bytearray(), None
    monitor = asyncio.create_task(monitor_connection(ws))
    
    try:
        async for msg in ws:
            if isinstance(msg, str): 
                continue

            last_frame_time = asyncio.get_event_loop().time()
            
            with open(raw_path, "ab") as f:
                f.write(msg)

            if header is None: 
                header = msg
                continue
            
            buffer.extend(msg)
            
            # Process chunks in 30k buckets for performance
            if len(buffer) > 30000: 
                with open("temp.webm", "wb") as f:
                    f.write(header + buffer)
                
                # Split stereo into discrete mono files
                cmd = ['ffmpeg', '-y', '-i', 'temp.webm', '-filter_complex', 
                       '[0:a]channelsplit=channel_layout=stereo[l][r]', 
                       '-map', '[l]', 'l.wav', '-map', '[r]', 'r.wav']
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                await process_audio('l.wav', ws, 'TAB')
                await process_audio('r.wav', ws, 'MIC')
                
                buffer = bytearray()
                
    except Exception as e:
        print(f"Socket error: {e}")
    finally:
        monitor.cancel()

async def main():
    init_workspace()
    async with websockets.serve(socket_handler, "127.0.0.1", 5000):
        print("Listening on ws://127.0.0.1:5000")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nFinalizing session files...")
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            subprocess.run(['ffmpeg', '-y', '-i', raw_path, '-acodec', 'libmp3lame', '-q:a', '2', final_path], 
                           stderr=subprocess.DEVNULL)
        
        # Cleanup
        for f in ["l.wav", "r.wav", "temp.webm"]:
            if os.path.exists(f): os.remove(f)
            
        print(f"Data saved to {session_dir}")