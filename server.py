import asyncio, os, subprocess, websockets, wave, json, struct, math, time, platform as plat
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, AuthenticationError

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

last_frame_time = 0
session_dir = ""
transcript_path = ""
raw_path = ""
final_path = ""
metadata_path = ""
health_timeline = []
stt_latency_log = []
captured_hostname = ""
sid = datetime.now().strftime("%Y%m%d_%H%M%S")


def init_workspace(platform_name, hostname="", capture_mode="dual_channel_stt_bridge", browser_version="unknown"):
    global session_dir, transcript_path, raw_path, final_path, metadata_path, captured_hostname
    captured_hostname = hostname

    # ✅ DoD: naming convention includes platform_id
    session_dir     = f"{platform_name}_session_{sid}"
    transcript_path = os.path.join(session_dir, f"{platform_name}_transcript.txt")
    raw_path        = os.path.join(session_dir, f"{platform_name}_capture.webm")
    final_path      = os.path.join(session_dir, f"{platform_name}_output.mp3")
    metadata_path   = os.path.join(session_dir, f"{platform_name}_metadata.json")

    if not os.path.exists(session_dir):
        os.makedirs(session_dir)

    # ✅ DoD: evidence pack with all required fields
    metadata = {
        "platform_id":        platform_name,
        "url_hostname":       hostname,
        "session_id":         sid,
        "capture_mode":       capture_mode,
        "browser_version":    browser_version,
        "os":                 plat.system(),
        "stt_latency_target": "30k_bucket",
        "health_timeline":    [],
        "stt_latency_log":    []
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"Platform: {platform_name.upper()} | Host: {hostname} | Session: {sid}\n" + "-" * 40 + "\n")

    open(raw_path, "wb").close()
    print(f"--- Workspace Ready: {session_dir} | Platform: {platform_name} | Host: {hostname} ---")


def _flush_evidence():
    """Write live health_timeline and stt_latency_log back into metadata.json."""
    if not metadata_path or not os.path.exists(metadata_path):
        return
    try:
        with open(metadata_path, "r") as f:
            meta = json.load(f)
        meta["health_timeline"] = health_timeline
        meta["stt_latency_log"] = stt_latency_log
        with open(metadata_path, "w") as f:
            json.dump(meta, f, indent=4)
    except Exception as e:
        print(f"Evidence flush error: {e}")


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
    if not session_dir: return
    ts = datetime.now().strftime('%H:%M:%S')
    log = f"[{ts}] {text}\n" if text else f"[{ts}] [DIAG] {status}\n"
    with open(transcript_path, "a", encoding="utf-8") as f:
        f.write(log)
        f.flush()
    msg = {"type": event, "status": status, "timestamp": ts}
    if text: msg["data"] = text
    try:
        await ws.send(json.dumps(msg))
    except:
        pass


def _do_transcription(audio_file):
    """Blocking OpenAI call — runs in a thread so Ctrl+C doesn't crash the loop."""
    with open(audio_file, "rb") as f:
        return client.audio.transcriptions.create(
            model="whisper-1", file=f, response_format="text"
        )


async def process_audio(audio_file, ws, label):
    if not os.path.exists(audio_file): return
    vol = get_rms(audio_file)
    if vol < 500: return
    try:
        t0 = time.time()

        # ── Fix 2: run blocking call in thread so KeyboardInterrupt is safe ──
        res = await asyncio.to_thread(_do_transcription, audio_file)

        text = res.strip()
        if len(text) > 2:
            ttf = round(time.time() - t0, 3)
            print(f"{label} | TTF: {ttf}s | Vol: {int(vol)} | {text}")

            # ✅ DoD: log STT latency per transcription
            stt_latency_log.append({
                "label":     label,
                "latency_s": ttf,
                "timestamp": datetime.now().strftime('%H:%M:%S')
            })

            await log_and_relay(ws, "TRANSCRIPT_UPDATE", "HEALTHY", f"{label}: {text}")
            _flush_evidence()

    # ── Fix 3: specific error handling for quota / auth issues ───────────────
    except RateLimitError as e:
        print(f"[ERROR] OpenAI quota exceeded — check your plan/billing. ({e.status_code})")
        health_timeline.append({
            "event":     "stt_quota_error",
            "label":     label,
            "timestamp": datetime.now().strftime('%H:%M:%S')
        })
        _flush_evidence()
    except AuthenticationError:
        print("[ERROR] Invalid OpenAI API key — check your .env file.")
    except asyncio.CancelledError:
        raise  # let the event loop handle shutdown cleanly
    except Exception as e:
        print(f"[ERROR] Transcription failed ({label}): {e}")


async def socket_handler(ws):
    global last_frame_time, session_dir
    print(f"Client connected at {datetime.now().strftime('%H:%M:%S')}")

    # Created here (not at module level) so it's tied to the running event loop
    platform_ready = asyncio.Event()
    pending_binary = []
    buffer, header = bytearray(), None

    try:
        async for msg in ws:
            # ── Handle text (control messages) ───────────────────────────────
            if isinstance(msg, str):
                data = json.loads(msg)
                if data.get("type") == "CAPTURE_ERROR":
                    print(f"[CAPTURE ERROR] {data.get('error')}: {data.get('message')}")
                    continue
                if data.get("type") == "PLATFORM_INFO":
                    platform_id     = data.get("platform", "unknown")
                    hostname        = data.get("hostname", "")
                    capture_mode    = data.get("capture_mode", "dual_channel_stt_bridge")
                    browser_version = data.get("browser_version", "unknown")

                    if not session_dir:
                        init_workspace(platform_id, hostname, capture_mode, browser_version)

                    # ✅ DoD: record session_start in health timeline
                    health_timeline.append({
                        "event":     "session_start",
                        "platform":  platform_id,
                        "hostname":  hostname,
                        "timestamp": datetime.now().strftime('%H:%M:%S')
                    })
                    _flush_evidence()

                    # Unblock binary processing and replay any buffered chunks
                    platform_ready.set()
                    for queued in pending_binary:
                        with open(raw_path, "ab") as f:
                            f.write(queued)
                        if header is None:
                            header = queued
                        else:
                            buffer.extend(queued)
                    pending_binary.clear()
                continue

            # ── Handle binary audio ──────────────────────────────────────────
            if not platform_ready.is_set():
                # PLATFORM_INFO hasn't arrived yet — queue the chunk
                pending_binary.append(bytes(msg))
                continue

            last_frame_time = asyncio.get_event_loop().time()
            with open(raw_path, "ab") as f:
                f.write(msg)

            if header is None:
                header = msg
                continue

            buffer.extend(msg)

            if len(buffer) > 30000:
                with open("temp.webm", "wb") as f:
                    f.write(header + buffer)

                cmd = ['ffmpeg', '-y', '-i', 'temp.webm', '-filter_complex',
                       '[0:a]channelsplit=channel_layout=stereo[l][r]',
                       '-map', '[l]', 'l.wav', '-map', '[r]', 'r.wav']
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # ✅ DoD: health event per batch
                health_timeline.append({
                    "event":        "audio_batch_processed",
                    "buffer_bytes": len(buffer),
                    "timestamp":    datetime.now().strftime('%H:%M:%S')
                })

                await process_audio('l.wav', ws, 'TAB')
                await process_audio('r.wav', ws, 'MIC')
                buffer = bytearray()

    except asyncio.CancelledError:
        pass  # clean shutdown
    except Exception as e:
        print(f"Socket error: {e}")



async def main():
    async with websockets.serve(socket_handler, "127.0.0.1", 5000):
        print("Listening on ws://127.0.0.1:5000")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nFinalizing session files...")
        if session_dir and os.path.exists(raw_path) and os.path.getsize(raw_path) > 0:
            subprocess.run(
                ['ffmpeg', '-y', '-i', raw_path, '-acodec', 'libmp3lame', '-q:a', '2', final_path],
                stderr=subprocess.DEVNULL
            )
        for f in ["l.wav", "r.wav", "temp.webm"]:
            if os.path.exists(f): os.remove(f)

        # ✅ Final evidence flush on shutdown
        health_timeline.append({"event": "session_end", "timestamp": datetime.now().strftime('%H:%M:%S')})
        _flush_evidence()
        print(f"Data saved to {session_dir}" if session_dir else "No session data to save.")