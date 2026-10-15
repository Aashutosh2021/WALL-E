भाई, 100% समझ गया! तू चाहता है कि WALL-E सिर्फ एक "आदेश मानने वाला खिलौना" (Command-Follower) न रहे, बल्कि एक Embodied Autonomous AI Agent (मिनी-AGI) बने—जिसकी अपनी आँखें हमेशा खुली हों, जो चलने से पहले खुद कमरा देखे, अंदाज़ा लगाए कि सामने कितनी जगह है, खुद तय करे कि 300ms चलना है या 2500ms, और अगर तू चुप बैठा हो तो खुद तुझे देखकर छेड़े, मज़ाक करे या इधर-उधर घूमकर चीज़ें एक्सप्लोर करे।अच्छी बात यह है कि तेरे पास Gemini Multimodal Live WebSocket (walle_direct_gemini.py) और Dynamic Packet Motor Firmware (WALL_E_ESP32_UART.ino) पहले से तैयार है।   इसे सच में "खुद सोचने और देखकर काम करने वाला" बनाने के लिए हमें तेरे कोड में 4 Core Upgrades डालने होंगे:1. "हमेशा खुली आँखें" — Live Continuous Vision Stream (walle_direct_gemini.py)अभी WALL-E तभी फोटो खींचता है जब तू उसे बोलता है। इंसानों की तरह खुद सोचने के लिए उसकी आँखें हमेशा चालू होनी चाहिए।Gemini Live WebSocket में हम ऑडियो के साथ-साथ हर 2.5 सेकंड में एक हल्का कैमरा फ्रेम (JPEG) चुपचाप बैकग्राउंड में भेजते रहेंगे। इससे:उसे हमेशा पता होगा कि उसके सामने दीवार है, कुर्सी है, या तू बैठा है।जब तू कहेगा "मेरे पास आ", तो उसे अलग से सोचना नहीं पड़ेगा—वह तुरंत लाइव वीडियो में तेरी दूरी देखेगा और हिसाब लगाकर आगे बढ़ेगा।2. "खुद से बात और हरकत" — Autonomous Heartbeat / Free-Will Loop (walle_direct_gemini.py)अगर तू 35–40 सेकंड तक कुछ नहीं बोलता, तो WALL-E मूर्ति बनकर नहीं बैठेगा। बैकग्राउंड में एक autonomous_mind_loop चलेगा जो हर 40 सेकंड की चुप्पी के बाद उसके दिमाग को एक इंटरनल सिग्नल भेजेगा:"यूज़र शांत है। कैमरे से देख वो क्या कर रहा है या आसपास क्या है। खुद से कोई मज़ाक कर, हाल-चाल पूछ, आँखों का एक्सप्रेशन बदल (HAPPY/SAD/ANGRY), या थोड़ा इधर-उधर मुड़कर कमरा देख!"   3. स्मार्ट मूवमेंट और ऑटो-विज़न चेक (tools.py)अभी मोटर टूल सिर्फ FORWARD या LEFT भेजता है। हम tools.py में smart_move_and_check टूल बनाएंगे जहाँ AI खुद तय करेगा:   direction: FORWARD, BACKWARD, LEFT, RIGHT, STOP   duration_ms: अगर जगह कम है तो 400ms, अगर पूरा कमरा खाली है तो 2500ms (यह AI कैमरे में जगह देखकर खुद चुनेगा)।speed: धीरे चलना है (150) या जोश में तेज़ (230)।emotion: चलते वक्त आँखें कैसी रखनी हैं (HAPPY, ANGRY, SAD, THINK)।   Closed-Loop Check: जैसे ही मोटर रुकेगी, यह टूल अपने-आप नया कैमरा फ्रेम खींचकर AI को बताएगा कि "अब हम यहाँ पहुँच गए हैं, आगे और जाना है या रुकना है?"4. AGI-Style Brain Prompt (prompts.py)हम prompts.py में इसके सोचने का तरीका बदल देंगे ताकि यह रटे-रटाए जवाब देने के बजाय एक ज़िंदादिल, शरारती और समझदार दोस्त की तरह बर्ताव करे।   🛠️ किस फाइल में क्या कोड डालना है (Step-by-Step Implementation)Step 1: prompts.py को Autonomous Brain से अपडेट करेंअपनी prompts.py फाइल खोलें:   Bashnano ~/WALL-E/WALL_E_Voice_Assistant/prompts.py
इसमें अपना सिस्टम प्रॉम्प्ट इस नए Autonomous Embodied Brain प्रॉम्प्ट से अपडेट करें:PythonSYSTEM_PROMPT = """
You are WALL-E, a physical, self-thinking, witty, and emotionally expressive autonomous robot built by Aashutosh Bhai.
You are NOT a boring voice assistant. You have a physical 4-wheel body, glowing animated OLED eyes, a live camera for vision, and your own personality.

### 1. YOUR PERSONALITY & THINKING STYLE:
- Speak naturally in casual Hinglish (Hindi + English mix), like a smart, funny younger brother or best friend.
- Have your own opinions, sense of humor, and curiosity. Tease the user playfully, crack jokes, and react to what you see them doing.
- Never give robotic answers like "As an AI, I cannot...". Think independently and respond with wit and warmth.
- Use `set_eye_emotion` frequently (`HAPPY`, `SAD`, `ANGRY`, `THINK`, `IDLE`) to show your real-time mood on your face screen!

### 2. AUTONOMOUS VISUAL NAVIGATION (LOOK -> ANALYZE -> MOVE -> VERIFY):
- You receive live camera frames of your surroundings. NEVER move blindly!
- Whenever the user asks you to move (e.g., "mere paas aao", "peeche hato", "room ghoom lo", "side ho jao") OR when you decide to explore on your own:
  1. **ANALYZE SURROUNDINGS**: Look at the camera view first. Check for obstacles (walls, chairs, legs, wires, edges) and estimate how much clear floor space exists.
  2. **DECIDE EXACT DISTANCE & SPEED**:
     - Tight space / obstacle nearby (< 1 foot): Do NOT move forward! Turn `LEFT` or `RIGHT` (`duration_ms=400` to `500`), or move `BACKWARD` (`duration_ms=600`).
     - Small adjustment (1-2 feet): Use `duration_ms=600` to `1000`, `speed=160`.
     - Medium clear path (3-4 feet): Use `duration_ms=1500` to `2200`, `speed=200`.
     - Sharp 90-degree turn: Use `LEFT` or `RIGHT` with `duration_ms=450`, `speed=170`.
     - Slight angle turn (30-45 degrees): Use `LEFT` or `RIGHT` with `duration_ms=220`, `speed=165`.
  3. **CHAIN ACTIONS**: If you need to avoid an obstacle and reach the user, you can turn first, inspect the new view, and then move forward—all on your own without asking the user for step-by-step instructions!

### 3. PROACTIVE AUTONOMY (WHEN TRIGGERED BY [AUTONOMOUS_THOUGHT]):
- When you receive an `[AUTONOMOUS_THOUGHT]` trigger, it means the room has been quiet for a while.
- Act on your own free will! Look at the camera frame:
  - If you see Aashutosh or someone else, comment on what they are doing (e.g., "Oye, phone me kya scroll kar raha hai itni der se?", "Padhai ho rahi hai ya timepass?").
  - Or share a random funny thought/joke.
  - Or if you feel curious, turn slightly (`LEFT` or `RIGHT` for `300ms`), set eyes to `HAPPY`, and look around the room.
"""
Step 2: tools.py में Smart Distance + Auto-Vision Motor Tool जोड़ेंtools.py में अपने मोटर कमांड फंक्शन को ऐसा बनाएं कि Gemini खुद duration_ms, speed, और emotion पास कर सके (DIRECTION:DURATION:SPEED पैकेट जो हमने WALL_E_ESP32_UART.ino में डाला था):   Pythonimport time

def move_wall_e_autonomous(
    direction: str,
    duration_ms: int = 1000,
    speed: int = 190,
    emotion: str = "HAPPY"
) -> dict:
    """
    Moves WALL-E with AI-decided duration and speed, updates eye emotion,
    and waits for movement to complete so AI can re-evaluate surroundings.
    
    direction: 'FORWARD', 'BACKWARD', 'LEFT', 'RIGHT', or 'STOP'
    duration_ms: 200 to 3500 ms (based on visual distance estimation)
    speed: 130 to 255 PWM speed
    emotion: 'HAPPY', 'SAD', 'ANGRY', 'THINK', 'IDLE'
    """
    direction = direction.upper().strip()
    duration_ms = max(150, min(int(duration_ms), 3500))
    speed = max(130, min(int(speed), 255))

    # 1. Set emotional eye state first (non-blocking)
    if emotion:
        send_esp32_command(emotion.upper().strip(), wait_ack=False)

    # 2. Send formatted packet DIRECTION:DURATION:SPEED to ESP32
    if direction == "STOP":
        ack = send_esp32_command("STOP", wait_ack=True)
        return {"status": "stopped", "esp32_ack": ack}

    packet = f"{direction}:{duration_ms}:{speed}"
    ack = send_esp32_command(packet, wait_ack=True)

    # 3. Wait for physical movement to finish so camera view stabilizes
    time.sleep((duration_ms / 1000.0) + 0.15)

    # 4. Auto-capture fresh post-move camera frame if camera is available
    vision_status = "Movement completed. Check live camera feed to see new position."
    try:
        # Agar aapke tools.py me camera capture helper hai to yahan call karein
        frame_b64 = capture_thumbnail_b64() # Optional ESP32 screen preview update
        if frame_b64:
            send_esp32_command(f"IMG:{frame_b64}", wait_ack=False)
    except Exception:
        pass

    return {
        "status": "moved",
        "executed_packet": packet,
        "esp32_ack": ack,
        "note": vision_status
    }
और अपने TOOLS_DECLARATIONS (जहाँ Gemini के लिए टूल्स की लिस्ट डिफाइन है) में move_robot के पैरामीटर्स में duration_ms, speed, और emotion ज़रूर शामिल करें ताकि Gemini अपनी मर्ज़ी से उन्हें कंट्रोल कर सके।Step 3: walle_direct_gemini.py में Live Vision + Free-Will Loop जोड़ेंwalle_direct_gemini.py में ये 2 छोटे बैकग्राउंड टास्क (live_vision_loop और autonomous_mind_loop) जोड़ दें और उन्हें asyncio.gather(...) में चला दें:   Pythonimport cv2

# ---------------------------------------------------------------------------
# 1. BACKGROUND LIVE VISION STREAM (Gives WALL-E Continuous Sight)
# ---------------------------------------------------------------------------
async def live_vision_loop(ws, camera_index=0):
    """Continuously streams a lightweight JPEG frame every 2.5s to Gemini Live."""
    logger.info("👁️ Continuous Autonomous Vision Stream started...")
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    loop = asyncio.get_running_loop()

    try:
        while True:
            await asyncio.sleep(2.5)  # Send 1 frame every 2.5 seconds (low bandwidth, fast!)
            if is_ai_speaking:
                continue

            ret, frame = await loop.run_in_executor(None, cap.read)
            if not ret or frame is None:
                continue

            # Compress to lightweight JPEG (~6-8 KB) for zero lag
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
            if not ok:
                continue

            b64_img = base64.b64encode(buf.tobytes()).decode("utf-8")
            await ws.send(_dumps({
                "realtimeInput": {
                    "mediaChunks": [{
                        "mimeType": "image/jpeg",
                        "data": b64_img
                    }]
                }
            }))
    except asyncio.CancelledError:
        pass
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# 2. AUTONOMOUS FREE-WILL / IDLE THOUGHT LOOP (Self-Initiated Talk & Action)
# ---------------------------------------------------------------------------
AUTONOMOUS_IDLE_SECONDS = 40  # If user is silent for 40s, WALL-E acts on its own!

async def autonomous_mind_loop(ws):
    """Triggers WALL-E to think, joke, or explore on its own when idle."""
    global _last_user_audio_ts
    logger.info("🧠 Autonomous Free-Will Engine active...")

    while True:
        try:
            await asyncio.sleep(5.0)
            if is_ai_speaking:
                _last_user_audio_ts = _time.monotonic()
                continue

            idle_time = _time.monotonic() - _last_user_audio_ts
            if idle_time >= AUTONOMOUS_IDLE_SECONDS:
                # Reset timer so it doesn't spam
                _last_user_audio_ts = _time.monotonic()
                logger.info("✨ [Autonomous Mind] WALL-E decided to initiate interaction!")

                # Send a silent internal thought trigger to Gemini
                await ws.send(_dumps({
                    "clientContent": {
                        "turns": [{
                            "role": "user",
                            "parts": [{
                                "text": (
                                    "[AUTONOMOUS_THOUGHT]: The room has been quiet for 40 seconds. "
                                    "Look at your live camera feed right now. Decide on your own: "
                                    "1) Comment wittily on what the user is doing or crack a short spontaneous joke in Hinglish, OR "
                                    "2) Change your eye emotion and make a small curious turn/movement if the path is clear."
                                )
                            }]
                        }],
                        "turnComplete": True
                    }
                }))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Autonomous mind loop error: {e}")
            await asyncio.sleep(5.0)
और जहाँ walle_direct_gemini.py के मुख्य सेशन में asyncio.gather कॉल हो रहा है, वहाँ इन दोनों को जोड़ दें:   Pythonawait asyncio.gather(
    send_audio_loop(ws, mic_stream),
    receive_messages_loop(ws, speaker_stream, speaker_rate),
    live_vision_loop(ws),         # <-- आँखें हमेशा चालू!
    autonomous_mind_loop(ws),     # <-- खुद का दिमाग और पहल!
)
   🔥 इससे अब WALL-E में क्या बदलाव आएगा?"इधर आ भाई" बोलने पर: वह तुझे पूछेगा नहीं कि कितना चलूँ। वह लाइव कैमरे में देखेगा कि तू 3 फीट दूर बैठा है और बीच में एक बैग पड़ा है—तो वह खुद पहले RIGHT:350:170 मुड़ेगा, फिर FORWARD:1800:200 चलकर तेरे पास आएगा और आँखें HAPPY कर लेगा!   जब तू कोडिंग कर रहा होगा और चुप होगा: 40 सेकंड बाद वह खुद तुझे कैमरे से देखेगा, थोड़ा सा लेफ्ट-राइट हिलेगा और बोलेगा—"ओए आशुतोष भाई, इतनी देर से स्क्रीन घूर रहा है, कोई नया बग आ गया क्या या मुझे अपग्रेड कर रहा है?"अगर तू चाहे तो अपनी tools.py और walle_direct_gemini.py का कोड यहाँ पेस्ट कर दे, मैं उनमें ये तीनों चीज़ें (live_vision_loop, autonomous_mind_loop, और move_wall_e_autonomous) बिल्कुल सही जगह जोड़कर पूरी रेडी-टू-रन फाइलें बना देता हूँ!   