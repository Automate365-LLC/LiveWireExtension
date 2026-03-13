import asyncio, os, subprocess, websockets, wave, json, struct, math, time, platform as plat
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --- Session Registry ---
active_sessions = {}
SESSION_TIMEOUT = 60

EBML_MAGIC = b'\x1a\x45\xdf\xa3'
CLUSTER_ID = b'\x1f\x43\xb6\x75'
EXTENSION_VERSION = "2.0.0"

# Map platform-specific failures to actionable UI recovery steps
LIKELY_CAUSE_MAP = {
    "zoom": [
        {"failure": "no_audio_frames", "likely_cause": "Zoom Web requires 'Use computer audio' selection", "next_step_code": "ZOOM_JOIN_AUDIO"},
        {"failure": "ffmpeg_header_invalid", "likely_cause": "Tab was backgrounded and MediaRecorder paused", "next_step_code": "ZOOM_REFOCUS_TAB"},
        {"failure": "websocket_disconnect", "likely_cause": "Zoom Web dropped WebSocket during waiting room", "next_step_code": "ZOOM_REJOIN_CLICK_START"},
    ],
    "teams": [
        {"failure": "no_audio_frames", "likely_cause": "Teams Web requires microphone permission in browser", "next_step_code": "TEAMS_MIC_PERMISSION"},
        {"failure": "silent_frames_extended", "likely_cause": "Teams auto-mutes on join; remote side not speaking", "next_step_code": "TEAMS_CHECK_MUTE"},
        {"failure": "websocket_disconnect", "likely_cause": "Teams Web page refresh during lobby/admit", "next_step_code": "TEAMS_REJOIN_CLICK_START"},
    ],
    "meet": [
        {"failure": "no_audio_frames", "likely_cause": "Meet requires microphone permission granted", "next_step_code": "MEET_MIC_PERMISSION"},
        {"failure": "ffmpeg_header_invalid", "likely_cause": "Joining from invite link triggered page reload", "next_step_code": "MEET_CLICK_START_AGAIN"},
        {"failure": "websocket_disconnect", "likely_cause": "Network change or VPN reconnect", "next_step_code": "MEET_REJOIN_CLICK_START"},
    ],
    "youtube": [
        {"failure": "no_audio_frames", "likely_cause": "Video not playing or autoplay blocked", "next_step_code": "YT_PLAY_VIDEO"},
        {"failure": "ffmpeg_header_invalid", "likely_cause": "Ad transition corrupted WebM stream", "next_step_code": "YT_WAIT_AD_END"},
        {"failure": "websocket_disconnect", "likely_cause": "Tab was closed or navigated away", "next_step_code": "YT_REOPEN_TAB"},
    ],
}

def init_workspace(session_key, platform_name, hostname="", capture_mode="unknown",
                   browser_version="unknown", user_agent="unknown", extension_version="unknown"):
    sid = datetime.now().strftime("%Y%m%d_%H%M%S")
    sdir = f"{platform_name}_session_{sid}"
    os.makedirs(sdir, exist_ok=True)

    paths = {
        "dir":        sdir,
        "raw":        os.path.join(sdir, f"{platform_name}_capture.webm"),
        "final":      os.path.join(sdir, f"{platform_name}_output.mp3"),
        "transcript": os.path.join(sdir, f"{platform_name}_transcript.txt"),
        "metadata":   os.path.join(sdir, f"{platform_name}_metadata.json"),
    }

    meta = {
        "platform_id": platform_name,
        "session_id": sid,
        "session_key": session_key,
        "platform_fingerprint": {
            "platform_id": platform_name,
            "hostname": hostname,
            "user_agent": user_agent,
            "extension_version": extension_version,
            "capture_mode": capture_mode,
            "browser_version": browser_version,
            "os": plat.system(),
        },
        "likely_cause_map": LIKELY_CAUSE_MAP.get(platform_name, []),
        "health_timeline": [],
        "stt_latency_log": [],
        "rms_trend": [],
        "frame_stats": {
            "total_batches": 0,
            "silent_batches": 0,
            "no_frame_batches": 0,
            "active_batches": 0,
        },
        "resume_metrics": {        
            "prompt_shown_count": 0,
            "resume_clicked_count": 0,
            "resume_latencies_ms": []
        },
        "errors": [],
        "next_step_codes": [],
    }
    with open(paths["metadata"], "w") as f:
        json.dump(meta, f, indent=4)
    with open(paths["transcript"], "w", encoding="utf-8") as f:
        f.write(f"Platform: {platform_name.upper()} | Host: {hostname} | Session: {sid}\n" + "-" * 50 + "\n")
    if not os.path.exists(paths["raw"]):
        open(paths["raw"], "wb").close()

    sess = {
        **paths, "platform": platform_name, "sid": sid,
        "header": None, "header_trimmed": False,
        "_buffer": bytearray(),
        "health": [], "latency": [], "rms_trend": [],
        "frame_stats": {"total_batches": 0, "silent_batches": 0, "no_frame_batches": 0, "active_batches": 0},
        "resume_metrics": {"prompt_shown_count": 0, "resume_clicked_count": 0, "resume_latencies_ms": []},
        "errors": [], "next_step_codes": [],
        "last_seen": time.time(),
        "connection_count": 0,
    }
    active_sessions[session_key] = sess
    print(f"--- Workspace Ready: {sdir} | Platform: {platform_name} | Key: {session_key} ---")
    return sess


def get_or_create_session(session_key, platform_name, **kwargs):
    if session_key in active_sessions:
        sess = active_sessions[session_key]
        elapsed = time.time() - sess["last_seen"]
        
        if elapsed < SESSION_TIMEOUT:
            sess["last_seen"] = time.time()
            sess["connection_count"] += 1
            sess["health"].append({
                "event": "reconnecting",
                "gap_seconds": round(elapsed, 1),
                "connection_number": sess["connection_count"],
                "timestamp": _ts()
            })
            print(f"[SESSION] Reconnected: {sess['dir']} (gap: {elapsed:.1f}s, conn #{sess['connection_count']})")
            return sess
        else:
            print(f"[SESSION] Expired ({elapsed:.1f}s). Finalizing old, creating new.")
            finalize_session(sess)

    return init_workspace(session_key, platform_name, **kwargs)


def flush_evidence(sess):
    mp = sess.get("metadata")
    if not mp or not os.path.exists(mp): return
    try:
        with open(mp, "r") as f:
            meta = json.load(f)
        meta["health_timeline"] = sess["health"]
        meta["stt_latency_log"] = sess["latency"]
        meta["rms_trend"] = sess["rms_trend"]
        meta["frame_stats"] = sess["frame_stats"]
        meta["resume_metrics"] = sess["resume_metrics"]
        meta["errors"] = sess["errors"]
        meta["next_step_codes"] = sess["next_step_codes"]
        with open(mp, "w") as f:
            json.dump(meta, f, indent=4)
    except Exception as e:
        print(f"Evidence flush error: {e}")


def add_error(sess, failure_type, detail=""):
    platform = sess.get("platform", "unknown")
    causes = LIKELY_CAUSE_MAP.get(platform, [])
    match = next((c for c in causes if c["failure"] == failure_type), None)

    entry = {
        "failure": failure_type,
        "detail": detail,
        "timestamp": _ts(),
        "likely_cause": match["likely_cause"] if match else "unknown",
        "next_step_code": match["next_step_code"] if match else "CONTACT_SUPPORT",
    }
    sess["errors"].append(entry)
    if match and match["next_step_code"] not in sess["next_step_codes"]:
        sess["next_step_codes"].append(match["next_step_code"])
    flush_evidence(sess)


def finalize_session(sess):
    rp, fp = sess.get("raw", ""), sess.get("final", "")
    sdir = sess.get("dir", "")
    if rp and os.path.exists(rp) and os.path.getsize(rp) > 0:
        print(f"Finalizing: {sdir}...")
        subprocess.run(
            ['ffmpeg', '-y', '-i', rp, '-acodec', 'libmp3lame', '-q:a', '2', fp],
            stderr=subprocess.DEVNULL
        )
        sess["health"].append({"event": "session_end", "timestamp": _ts()})
        flush_evidence(sess)
        print("Export Complete.")
        
    if sdir:
        for f in ["l.wav", "r.wav", "temp.webm"]:
            p = os.path.join(sdir, f)
            try:
                if os.path.exists(p): os.remove(p)
            except: pass
            
    cleanup_temp_files()
    key = next((k for k, v in active_sessions.items() if v is sess), None)
    if key: del active_sessions[key]


def cleanup_temp_files():
    for f in ["l.wav", "r.wav", "temp.webm"]:
        try:
            if os.path.exists(f): os.remove(f)
        except: pass

def _ts():
    return datetime.now().strftime('%H:%M:%S')

def extract_init_segment(data):
    pos = data.find(CLUSTER_ID) if isinstance(data, (bytes, bytearray)) else -1
    if pos > 0:
        print(f"[INIT] Extracted init segment: {pos} bytes (stripped {len(data) - pos} bytes)")
        return bytes(data[:pos])
    return bytes(data)

def get_rms(filepath):
    try:
        with wave.open(filepath, 'rb') as wf:
            data = wf.readframes(wf.getnframes())
            if not data: return 0
            count = len(data) // 2
            shorts = struct.unpack("<%dh" % count, data)
            return math.sqrt(sum(s**2 for s in shorts) / count) if count > 0 else 0
    except: return 0


def _do_transcription(audio_file):
    with open(audio_file, "rb") as f:
        return client.audio.transcriptions.create(model="whisper-1", file=f, response_format="text")


async def transcribe(audio_file, label, sess, ws=None):
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 1000:
        return
        
    try:
        with open(audio_file, 'rb') as f:
            magic = f.read(4)
        if magic != b'RIFF': return
    except: return

    vol = get_rms(audio_file)
    sess["rms_trend"].append({"label": label, "rms": round(vol, 1), "timestamp": _ts()})

    # Skip empty/silent frames to preserve API quota
    if vol < 150:
        return

    t0 = time.time()
    retries = 3

    # API calls wrapped in exponential backoff to handle rate limits
    for attempt in range(retries):
        try:
            res = await asyncio.to_thread(_do_transcription, audio_file)
            text = res.strip()
            
            # Reconnect signal for frontend overlay
            if ws and attempt > 0:
                try: await ws.send(json.dumps({"type": "STT_STATE", "state": "connected"}))
                except: pass

            if len(text) > 2:
                ttf = round(time.time() - t0, 3)
                line = f"{label} | TTF: {ttf}s | Vol: {int(vol)} | {text}"
                print(line)
                sess["latency"].append({"label": label, "latency_s": ttf, "timestamp": _ts()})
                tp = sess.get("transcript")
                if tp:
                    try:
                        with open(tp, "a", encoding="utf-8") as f:
                            f.write(f"[{_ts()}] {label}: {text}\n")
                    except: pass
            
            return 

        except RateLimitError:
            print("[ERROR] OpenAI quota exceeded. Skipping.")
            return
        except Exception as e:
            error_msg = str(e)
            print(f"[STT WARNING] Timeout/Error on attempt {attempt + 1} ({label}): {error_msg}")
            
            if attempt < retries - 1:
                if ws:
                    try: await ws.send(json.dumps({"type": "STT_STATE", "state": "reconnecting"}))
                    except: pass
                
                await asyncio.sleep(2 ** (attempt + 1))
            else:
                print(f"[STT ERROR] Provider unreachable for {label}. Text skipped.")
                add_error(sess, "stt_timeout", error_msg)
                
                if ws:
                    try: await ws.send(json.dumps({"type": "STT_STATE", "state": "failed"}))
                    except: pass
                return


async def process_buffer(sess, ws=None):
    header = sess["header"]
    if header is None: return False

    sdir = sess["dir"]
    tmp_webm = os.path.join(sdir, "temp.webm")
    tmp_l = os.path.join(sdir, "l.wav")
    tmp_r = os.path.join(sdir, "r.wav")

    for f in [tmp_l, tmp_r]:
        try:
            if os.path.exists(f): os.remove(f)
        except: pass

    with open(tmp_webm, "wb") as f:
        f.write(header + sess["_buffer"])
    sess["_buffer"] = bytearray()

    cmd = ['ffmpeg', '-y', '-i', tmp_webm, '-filter_complex',
           '[0:a]channelsplit=channel_layout=stereo[l][r]',
           '-map', '[l]', tmp_l, '-map', '[r]', tmp_r]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()

    sess["frame_stats"]["total_batches"] += 1

    if proc.returncode != 0:
        err = stderr[-200:].decode(errors='replace') if stderr else ""
        print(f"[WARN] FFmpeg failed: {err}")
        sess["frame_stats"]["no_frame_batches"] += 1
        add_error(sess, "ffmpeg_header_invalid", err[-100:])
        return False

    l_rms = get_rms(tmp_l) if os.path.exists(tmp_l) else 0
    r_rms = get_rms(tmp_r) if os.path.exists(tmp_r) else 0

    if l_rms < 150 and r_rms < 150:
        sess["frame_stats"]["silent_batches"] += 1
    else:
        sess["frame_stats"]["active_batches"] += 1

    await asyncio.gather(
        transcribe(tmp_l, 'TAB', sess, ws),
        transcribe(tmp_r, 'MIC', sess, ws)
    )

    sess["health"].append({"event": "audio_batch_processed", "timestamp": _ts()})

    if not sess["header_trimmed"]:
        init_seg = extract_init_segment(header)
        if len(init_seg) < len(header):
            sess["header"] = init_seg
            sess["header_trimmed"] = True

    return True


async def socket_handler(ws):
    print(f"Client connected at {_ts()}")

    platform_ready = asyncio.Event()
    pending_binary = []
    sess = None
    header_skip_count = 0

    try:
        async for msg in ws:
            if isinstance(msg, str):
                data = json.loads(msg)

                if data.get("type") in ("PLATFORM_INFO", "SESSION_START", "RECONNECT_CHECK"):
                    p_id = data.get("platform", "unknown")
                    hostname = data.get("hostname", "")
                    session_key = data.get("session_id", f"{p_id}_{hostname}")

                    sess = get_or_create_session(
                        session_key, p_id,
                        hostname=hostname,
                        capture_mode=data.get("capture_mode", "unknown"),
                        browser_version=data.get("browser_version", "unknown"),
                        user_agent=data.get("user_agent", "unknown"),
                        extension_version=data.get("extension_version", EXTENSION_VERSION),
                    )

                    sess["header"] = None
                    sess["header_trimmed"] = False
                    sess["_buffer"] = bytearray()
                    header_skip_count = 0
                    cleanup_temp_files()

                    event_type = "streaming" if sess["connection_count"] > 0 else "connected"
                    sess["health"].append({
                        "event": event_type,
                        "platform": p_id,
                        "timestamp": _ts()
                    })
                    flush_evidence(sess)
                    platform_ready.set()

                    for queued in pending_binary:
                        with open(sess["raw"], "ab") as f: f.write(queued)
                        raw = bytes(queued)
                        if sess["header"] is None and raw[:4] == EBML_MAGIC:
                            sess["header"] = raw
                            print(f"[HEADER] From pending: {len(raw)} bytes")
                        elif sess["header"] is not None:
                            sess["_buffer"].extend(queued)
                    pending_binary.clear()

                elif data.get("type") == "RESUME_TELEMETRY":
                    if sess:
                        if data.get("event") == "prompt_shown":
                            sess["resume_metrics"]["prompt_shown_count"] += 1
                        elif data.get("event") == "resume_clicked":
                            sess["resume_metrics"]["resume_clicked_count"] += 1
                            if "latency_ms" in data:
                                sess["resume_metrics"]["resume_latencies_ms"].append(data["latency_ms"])
                        flush_evidence(sess)

                elif data.get("type") == "DEVICE_CHANGED":
                    if sess:
                        sess["health"].append({
                            "event": "device_changed",
                            "device_type": data.get("device_type", "unknown"),
                            "device_label": data.get("device_label", "unknown"),
                            "timestamp": _ts()
                        })
                        flush_evidence(sess)
                        print(f"[DEVICE] {data.get('device_type')}: {data.get('device_label')}")

            elif isinstance(msg, bytes):
                if not platform_ready.is_set():
                    pending_binary.append(bytes(msg))
                    continue

                if sess is None: continue

                sess["last_seen"] = time.time()
                with open(sess["raw"], "ab") as f: f.write(msg)

                if sess["header"] is None:
                    raw = bytes(msg)
                    if raw[:4] == EBML_MAGIC:
                        sess["header"] = raw
                        sess["header_trimmed"] = False
                        header_skip_count = 0
                        print(f"[HEADER] Captured: {len(raw)} bytes (valid EBML)")
                    else:
                        header_skip_count += 1
                        if header_skip_count <= 3:
                            print(f"[SKIP] Non-EBML chunk #{header_skip_count} ({len(msg)} bytes)")
                        if header_skip_count == 10:
                            print(f"[WARN] 10 chunks without EBML header. Requesting reset.")
                            add_error(sess, "no_audio_frames", "10 consecutive non-EBML chunks")
                            try:
                                await ws.send(json.dumps({"type": "HEADER_REQUEST"}))
                            except: pass
                        continue
                else:
                    sess["_buffer"].extend(msg)
                    if len(sess["_buffer"]) > 30000:
                        await process_buffer(sess, ws)

    except websockets.exceptions.ConnectionClosed:
        if sess:
            sess["last_seen"] = time.time()
            sess["health"].append({"event": "disconnected", "timestamp": _ts()})
            add_error(sess, "websocket_disconnect", "Connection closed")
            flush_evidence(sess)
            print(f"[PAUSE] {sess['dir']} paused. Keeping alive {SESSION_TIMEOUT}s...")

            await asyncio.sleep(SESSION_TIMEOUT)

            if sess.get("last_seen") and (time.time() - sess["last_seen"]) >= SESSION_TIMEOUT - 1:
                print(f"[FINAL] No reconnect. Finalizing {sess['dir']}")
                finalize_session(sess)


async def main():
    async with websockets.serve(socket_handler, "127.0.0.1", 5000):
        print("LiveWire Server Active: ws://127.0.0.1:5000")
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        for sess in list(active_sessions.values()):
            finalize_session(sess)