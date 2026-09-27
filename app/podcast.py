import os
import asyncio
import hashlib
import edge_tts
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---------- Config ----------
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge").lower()

DEEPSEEK_CLIENT = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

OPENAI_CLIENT = None
if os.getenv("OPENAI_API_KEY"):
    OPENAI_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ---------- Voice Configuration ----------

# Edge TTS voices + tuned parameters for lively podcast delivery
EDGE_VOICES = {
    "HOST": {
        "voice": "ru-RU-SvetlanaNeural",
        "rate": "+8%",     # slightly faster — more energetic
        "pitch": "+15Hz",  # slightly higher — warmer, friendlier
        "volume": "+5%",
    },
    "EXPERT": {
        "voice": "ru-RU-DmitryNeural",
        "rate": "+5%",     # a bit faster than default (which is slow)
        "pitch": "+5Hz",   # slight lift — less monotone
        "volume": "+5%",
    },
}

# OpenAI TTS voices — natural, style-steerable
OPENAI_VOICES = {
    "HOST": {
        "voice": "nova",   # bright, energetic female
        "instructions": (
            "You are the host of an educational podcast in Russian. "
            "Speak warmly, with genuine curiosity and energy. "
            "Vary your intonation — you're having a real conversation, not reading a script. "
            "Use natural pauses where you would breathe."
        ),
    },
    "EXPERT": {
        "voice": "onyx",   # deep, authoritative male
        "instructions": (
            "You are the expert guest on an educational podcast in Russian. "
            "Speak confidently but conversationally — like you're explaining to a friend, "
            "not lecturing. Vary your pace and intonation naturally. "
            "Sound engaged and interested, not robotic."
        ),
    },
}


# ---------- Podcast Script Prompt ----------

PODCAST_SYSTEM_PROMPT = """You are a podcast script writer for an educational show called "Socrat".

Your task: Convert a tutoring conversation into an engaging, NATURAL podcast dialogue between TWO speakers in russian language:
- HOST (female, curious, energetic, asks good questions)
- EXPERT (male, knowledgeable, explains clearly, warm but authoritative)

CRITICAL RULES for natural speech:
1. Every line MUST start with either "HOST:" or "EXPERT:"
2. Write like real people talk — NOT like a textbook
3. Use natural interjections: "Ага", "Интересно!", "Точно", "О, классный вопрос", "Хм, дай подумаю"
4. HOST should react to what EXPERT says ("Ого, я не знал!", "Подожди, то есть...?")
5. EXPERT should occasionally check understanding ("Понимаешь?", "Видишь, как это работает?")
6. Keep sentences SHORT. Long sentences sound robotic when spoken.
7. Avoid lists — turn them into flowing dialogue
8. No stage directions, no brackets, no music cues — ONLY "HOST:" and "EXPERT:" prefixes
9. Total length: 2-4 minutes of spoken content (roughly 15-25 lines)
10. End with a short, motivating takeaway from the EXPERT

Tone: friendly, curious, energetic. Like two smart friends explaining something.

Example of GOOD dialogue:
HOST: Привет! Сегодня разберём, что такое декораторы в Python.
EXPERT: О, отличная тема! Знаешь, это одна из тех вещей, которые кажутся сложными, пока не поймёшь суть.
HOST: Ага, я как раз из тех, кто пока не понял. С чего начнём?
EXPERT: Представь, что у тебя есть функция. Просто функция. И ты хочешь добавить ей новую способность, не меняя её код.
HOST: Подожди, то есть как будто мы надеваем на неё плащ супергероя?
EXPERT: Именно! И делается это с помощью символа @. Смотри...

Example of BAD dialogue (too robotic — DO NOT DO THIS):
HOST: Что такое декоратор в Python?
EXPERT: Декоратор в Python — это функция высшего порядка, которая принимает другую функцию в качестве аргумента и возвращает новую функцию. Она позволяет модифицировать поведение исходной функции без изменения её исходного кода.
"""


# ---------- Script Generation ----------

def generate_podcast_script(chat_history: list) -> str:
    """Ask DeepSeek to turn chat history into a natural podcast dialogue."""
    transcript = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in chat_history
    )

    response = DEEPSEEK_CLIENT.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": PODCAST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the conversation:\n\n{transcript}\n\nNow write the podcast script."}
        ],
        temperature=0.85
    )
    return response.choices[0].message.content


# ---------- Script Parsing ----------

def parse_script(script: str):
    """Extract speaker + text pairs from a script. Skip empty lines."""
    lines = []
    for raw in script.strip().split("\n"):
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("HOST:"):
            text = line[5:].strip()
            if text:
                lines.append(("HOST", text))
        elif upper.startswith("EXPERT:"):
            text = line[7:].strip()
            if text:
                lines.append(("EXPERT", text))
    return lines


# ---------- Audio Synthesis Backends ----------

async def _edge_synthesize(text: str, speaker: str, out_path: str, retries: int = 3):
    """Synthesize one line using edge-tts with retries."""
    cfg = EDGE_VOICES[speaker]

    for attempt in range(1, retries + 1):
        try:
            communicate = edge_tts.Communicate(
                text,
                cfg["voice"],
                rate=cfg["rate"],
                pitch=cfg["pitch"],
                volume=cfg["volume"],
            )
            await communicate.save(out_path)

            if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
                return True
            else:
                print(f"⚠️  Empty audio for line: '{text[:40]}...' (attempt {attempt})")
        except Exception as e:
            print(f"⚠️  Edge TTS error (attempt {attempt}/{retries}): {e}")

        await asyncio.sleep(1.5 * attempt)

    print(f"❌ Giving up on line: '{text[:40]}...'")
    return False


def _openai_synthesize(text: str, speaker: str, out_path: str):
    """Synthesize one line using OpenAI TTS."""
    if not OPENAI_CLIENT:
        raise RuntimeError("OPENAI_API_KEY not set — cannot use OpenAI TTS")

    cfg = OPENAI_VOICES[speaker]

    response = OPENAI_CLIENT.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=cfg["voice"],
        input=text,
        instructions=cfg["instructions"],
        response_format="mp3",
    )
    response.stream_to_file(out_path)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 100


# ---------- Main Audio Generation ----------

async def generate_podcast_audio(script: str, output_path: str):
    """Generate MP3 audio from a script, using the configured TTS provider."""
    lines = parse_script(script)

    if not lines:
        raise ValueError("No valid dialogue lines found in script")

    print(f"🎙️ Synthesizing {len(lines)} lines via '{TTS_PROVIDER}'...")

    temp_files = []

    for i, (speaker, text) in enumerate(lines):
        if len(text) < 2:
            continue

        temp_file = f"/tmp/line_{i}.mp3"

        if TTS_PROVIDER == "openai":
            try:
                ok = _openai_synthesize(text, speaker, temp_file)
            except Exception as e:
                print(f"⚠️  OpenAI TTS failed for line {i}: {e}")
                ok = False
        else:
            ok = await _edge_synthesize(text, speaker, temp_file)

        if ok:
            temp_files.append(temp_file)

        # Small delay to avoid rate limits (edge)
        if TTS_PROVIDER == "edge":
            await asyncio.sleep(0.3)

    if not temp_files:
        raise ValueError("No audio was generated for any line")

    print(f"🔗 Concatenating {len(temp_files)} segments...")

    combined = AudioSegment.empty()
    for f in temp_files:
        try:
            seg = AudioSegment.from_mp3(f)
            # Insert a natural pause between speakers (~500ms)
            combined += seg + AudioSegment.silent(duration=500)
        except Exception as e:
            print(f"⚠️  Skipping broken segment {f}: {e}")
        finally:
            try:
                os.remove(f)
            except Exception:
                pass

    combined.export(output_path, format="mp3")
    print(f"✅ Podcast exported: {output_path}")
    return output_path