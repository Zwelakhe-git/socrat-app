### celerey app task fails to combine audio files
possible Problems:
1. Rate limiting — You fired 10+ TTS requests in rapid succession (one per dialogue line). Microsoft silently throttles you and returns empty audio for the throttled ones.
2. Empty text — One of the parsed lines came out blank (e.g., a stray HOST: with nothing after it).
3. Special characters — Emoji, brackets, or Unicode that the voice didn't understand.
4. Network blip — The connection to Microsoft's endpoint dropped.

### solutions:
6. Filter empty lines before sending them to TTS
7. Add retry logic with exponential backoff
8. Add a small delay between TTS calls to avoid rate limiting
9. Store the script in the DB so we don't regenerate it — your suggestion, and it's the right one

