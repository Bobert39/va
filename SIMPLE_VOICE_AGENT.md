# Simple AI Voice Agent

A minimal, standalone voice assistant that you can talk to directly using your microphone. No phone system or complex setup required!

## What It Does

This simple voice agent:
1. **Listens** to you via your microphone
2. **Transcribes** your speech using OpenAI Whisper
3. **Thinks** and generates responses using GPT-4
4. **Speaks** back to you using text-to-speech
5. **Remembers** the conversation context

## Quick Start

### 1. Install Dependencies

```bash
# Install the audio libraries
poetry install

# Or if using pip directly:
pip install openai sounddevice soundfile numpy
```

### 2. Set Your OpenAI API Key

```bash
# On Linux/Mac:
export OPENAI_API_KEY='sk-your-key-here'

# On Windows (Command Prompt):
set OPENAI_API_KEY=sk-your-key-here

# On Windows (PowerShell):
$env:OPENAI_API_KEY='sk-your-key-here'
```

### 3. Run the Agent

```bash
# Default: 5 seconds per recording
python simple_voice_agent.py

# Custom duration: 10 seconds per recording
python simple_voice_agent.py 10
```

## How to Use

1. **Run the script** - The agent will greet you
2. **Wait for the prompt** - You'll see "🎤 Recording for X seconds... Speak now!"
3. **Speak your message** - Talk naturally into your microphone
4. **Wait for the response** - The agent will think and speak back to you
5. **Continue the conversation** - The loop repeats
6. **Exit** - Say "exit", "quit", or "goodbye" to end the conversation

## Example Conversation

```
🤖 Simple AI Voice Agent
==================================================
💬 AI: "Hello! I'm your AI voice assistant. How can I help you today?"
🔊 Speaking...
✓ Done speaking!

--------------------------------------------------
🎤 Recording for 5 seconds... Speak now!
==================================================
✓ Recording complete!
🎧 Transcribing audio...
📝 You said: "What's the weather like today?"
🤔 Thinking...
💬 AI: "I don't have access to real-time weather data, but I can help you with other questions or tasks. Is there something else I can assist you with?"
🔊 Speaking...
✓ Done speaking!

--------------------------------------------------
🎤 Recording for 5 seconds... Speak now!
==================================================
✓ Recording complete!
🎧 Transcribing audio...
📝 You said: "Tell me a joke"
🤔 Thinking...
💬 AI: "Why don't scientists trust atoms? Because they make up everything!"
🔊 Speaking...
✓ Done speaking!

--------------------------------------------------
🎤 Recording for 5 seconds... Speak now!
==================================================
✓ Recording complete!
🎧 Transcribing audio...
📝 You said: "Goodbye"
👋 Goodbye! Thanks for chatting!
💬 AI: "Goodbye! It was nice talking to you."
🔊 Speaking...
```

## Features

- **Conversational Memory**: Remembers your conversation context
- **Natural Conversation**: Speaks in a friendly, conversational tone
- **Easy to Use**: No complex configuration needed
- **Customizable**: Adjust recording duration based on your needs
- **Safe Exit**: Multiple ways to exit (say goodbye, press Ctrl+C)

## Customization

### Change the Voice

Edit line 128 in `simple_voice_agent.py`:

```python
voice="alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
```

### Change the Personality

Edit the `system_prompt` in the `__init__` method (around line 45):

```python
self.system_prompt = {
    "role": "system",
    "content": (
        "You are a helpful, friendly AI voice assistant. "
        "Keep your responses concise and conversational, "
        "as they will be spoken aloud. "
        "Be warm and engaging in your tone."
    )
}
```

### Change the AI Model

Edit line 100 in `simple_voice_agent.py`:

```python
model="gpt-4",  # Options: gpt-4, gpt-3.5-turbo
```

### Adjust Response Length

Edit line 101 in `simple_voice_agent.py`:

```python
max_tokens=150,  # Increase for longer responses
```

## Troubleshooting

### "No OpenAI API key found"

Make sure you've set the `OPENAI_API_KEY` environment variable:
```bash
export OPENAI_API_KEY='sk-your-key-here'
```

### "No microphone detected" or Audio Issues

1. Check that your microphone is connected and working
2. Test your microphone with other applications
3. Make sure no other application is using the microphone
4. On Linux, you may need to install PortAudio:
   ```bash
   sudo apt-get install portaudio19-dev
   ```

### "Module not found" Errors

Install the required packages:
```bash
poetry install
# Or
pip install openai sounddevice soundfile numpy
```

### Poor Transcription Quality

1. Speak clearly and at a normal pace
2. Reduce background noise
3. Move closer to your microphone
4. Increase recording duration if you speak slower:
   ```bash
   python simple_voice_agent.py 10
   ```

### Audio Playback Issues

On some systems, you may need to install additional audio libraries:

**Linux:**
```bash
sudo apt-get install libsndfile1 portaudio19-dev
```

**macOS:**
```bash
brew install portaudio
```

**Windows:**
Usually works out of the box. If issues persist, try reinstalling sounddevice.

## Differences from the Full Platform

This simple voice agent is a **minimal demonstration**. The full Voice AI Platform in this repository includes:

- **Phone Integration** - Twilio integration for real phone calls
- **EMR Integration** - Integration with OpenEMR/FHIR for appointment scheduling
- **Dashboard** - Web-based monitoring and management interface
- **HIPAA Compliance** - Audit logging and encryption
- **Production Features** - Rate limiting, error handling, monitoring

Use this simple agent to:
- Learn how voice AI works
- Test OpenAI's speech capabilities
- Build prototypes
- Have fun with voice interactions

For production medical office deployment, use the full platform!

## API Costs

This agent uses OpenAI APIs which have usage costs:
- **Whisper (Speech-to-Text)**: $0.006 per minute
- **GPT-4 (Responses)**: ~$0.03 per 1K tokens (varies)
- **TTS (Text-to-Speech)**: $15 per 1M characters

A typical 5-minute conversation might cost:
- Transcription: 5 minutes × $0.006 = $0.03
- GPT-4: ~10 exchanges × $0.001 = $0.01
- TTS: ~500 characters × $0.000015 = $0.0075
- **Total: ~$0.05 per 5-minute conversation**

## License

Part of the Voice AI Platform project.
