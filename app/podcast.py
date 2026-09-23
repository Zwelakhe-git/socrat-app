import os
import asyncio
import edge_tts
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# Russian voices — perfect for your use case
HOST_VOICE = "ru-RU-SvetlanaNeural"   # Female, warm
EXPERT_VOICE = "ru-RU-DmitryNeural"   # Male, authoritative

PODCAST_SYSTEM_PROMPT = """You are a podcast script writer for an educational show called "Socrat".

Your task: Convert a tutoring conversation into an engaging podcast dialogue between TWO speakers:
- HOST (female, curious, asks good questions)
- EXPERT (male, knowledgeable, explains clearly)

FORMAT RULES (strict):
1. Every line MUST start with either "HOST:" or "EXPERT:"
2. Keep it conversational and natural — like two friends talking
3. No stage directions, no music cues, no brackets
4. Total length: 2-4 minutes of spoken content
5. The HOST asks the questions a student would ask
6. The EXPERT answers them with clear explanations and analogies
7. End with a short, motivating takeaway

Example:
HOST: Привет! Сегодня мы разберём, что такое декораторы в Python.
EXPERT: Отличная тема! Представь, что у тебя есть функция, и ты хочешь добавить ей новую способность...
HOST: То есть как будто мы надеваем на функцию плащ супергероя?
EXPERT: Именно! И это делается с помощью символа @...
"""

async def generate_podcast_audio(script: str, output_path: str):
    """Generate MP3 audio from a script with two alternating voices."""
    
    lines = []
    for line in script.strip().split("\n"):
        line = line.strip()
        if line.startswith("HOST:"):
            lines.append(("HOST", line.replace("HOST:", "").strip()))
        elif line.startswith("EXPERT:"):
            lines.append(("EXPERT", line.replace("EXPERT:", "").strip()))

    if not lines:
        raise ValueError("No valid dialogue lines found in script")

    # Generate audio for each line
    temp_files = []
    for i, (speaker, text) in enumerate(lines):
        voice = HOST_VOICE if speaker == "HOST" else EXPERT_VOICE
        temp_file = f"/tmp/line_{i}.mp3"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(temp_file)
        temp_files.append(temp_file)

    # Concatenate all lines
    combined = AudioSegment.empty()
    for f in temp_files:
        segment = AudioSegment.from_mp3(f)
        combined += segment + AudioSegment.silent(duration=400)  # 400ms pause between lines
        os.remove(f)

    # Export final file
    combined.export(output_path, format="mp3")
    return output_path


def generate_podcast_script(chat_history: list) -> str:
    """Ask DeepSeek to turn chat history into a podcast dialogue."""
    
    # Format the chat history as a readable transcript
    transcript = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" 
        for msg in chat_history
    )
    
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": PODCAST_SYSTEM_PROMPT},
            {"role": "user", "content": f"Here is the conversation:\n\n{transcript}\n\nNow write the podcast script."}
        ],
        temperature=0.8
    )
    
    return response.choices[0].message.content