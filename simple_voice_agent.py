#!/usr/bin/env python3
"""
Simple AI Voice Agent - A standalone voice assistant you can talk to

This is a minimal voice agent that:
1. Records audio from your microphone
2. Transcribes speech using OpenAI Whisper
3. Generates intelligent responses using GPT
4. Speaks responses back using text-to-speech

No phone system or complex setup required!
"""

import os
import sys
import tempfile
import wave
from pathlib import Path
from typing import Optional

try:
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    from openai import OpenAI
except ImportError:
    print("Error: Required packages not installed.")
    print("Please run: pip install openai sounddevice soundfile numpy")
    sys.exit(1)


class SimpleVoiceAgent:
    """A simple voice agent that can listen, think, and speak"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the voice agent"""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter"
            )

        self.client = OpenAI(api_key=self.api_key)
        self.conversation_history = []
        self.sample_rate = 16000  # 16kHz for speech
        self.channels = 1  # Mono audio

        # System prompt - defines the agent's personality
        self.system_prompt = {
            "role": "system",
            "content": (
                "You are a helpful, friendly AI voice assistant. "
                "Keep your responses concise and conversational, "
                "as they will be spoken aloud. "
                "Be warm and engaging in your tone."
            )
        }
        self.conversation_history.append(self.system_prompt)

    def record_audio(self, duration: int = 5) -> str:
        """
        Record audio from the microphone

        Args:
            duration: Recording duration in seconds (default 5)

        Returns:
            Path to the recorded audio file
        """
        print(f"\n🎤 Recording for {duration} seconds... Speak now!")
        print("=" * 50)

        # Record audio
        recording = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.int16
        )
        sd.wait()  # Wait for recording to complete

        print("✓ Recording complete!")

        # Save to temporary WAV file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        sf.write(temp_file.name, recording, self.sample_rate)

        return temp_file.name

    def transcribe_audio(self, audio_file: str) -> str:
        """
        Transcribe audio to text using Whisper

        Args:
            audio_file: Path to audio file

        Returns:
            Transcribed text
        """
        print("🎧 Transcribing audio...")

        with open(audio_file, "rb") as f:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en"
            )

        text = transcript.text.strip()
        print(f"📝 You said: \"{text}\"")

        return text

    def generate_response(self, user_message: str) -> str:
        """
        Generate a response using GPT

        Args:
            user_message: The user's transcribed message

        Returns:
            AI-generated response
        """
        print("🤔 Thinking...")

        # Add user message to conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })

        # Generate response
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=self.conversation_history,
            max_tokens=150,  # Keep responses concise
            temperature=0.7
        )

        assistant_message = response.choices[0].message.content.strip()

        # Add assistant response to conversation history
        self.conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message

    def speak(self, text: str) -> None:
        """
        Convert text to speech and play it

        Args:
            text: Text to speak
        """
        print(f"💬 AI: \"{text}\"")
        print("🔊 Speaking...")

        # Generate speech
        response = self.client.audio.speech.create(
            model="tts-1",
            voice="alloy",  # Options: alloy, echo, fable, onyx, nova, shimmer
            input=text
        )

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        response.stream_to_file(temp_file.name)

        # Play audio using sounddevice
        try:
            data, samplerate = sf.read(temp_file.name)
            sd.play(data, samplerate)
            sd.wait()  # Wait for playback to complete
        finally:
            # Clean up
            os.unlink(temp_file.name)

        print("✓ Done speaking!")

    def chat_once(self, duration: int = 5) -> bool:
        """
        One complete interaction: listen, think, respond

        Args:
            duration: Recording duration in seconds

        Returns:
            True if conversation should continue, False to exit
        """
        try:
            # Record audio
            audio_file = self.record_audio(duration)

            try:
                # Transcribe
                user_message = self.transcribe_audio(audio_file)

                # Check for exit command
                if any(word in user_message.lower() for word in ['exit', 'quit', 'goodbye', 'bye']):
                    print("\n👋 Goodbye! Thanks for chatting!")
                    self.speak("Goodbye! It was nice talking to you.")
                    return False

                # Generate response
                response = self.generate_response(user_message)

                # Speak response
                self.speak(response)

                return True

            finally:
                # Clean up audio file
                os.unlink(audio_file)

        except KeyboardInterrupt:
            print("\n\n👋 Interrupted. Goodbye!")
            return False
        except Exception as e:
            print(f"\n❌ Error: {e}")
            return True  # Continue despite errors

    def run(self, recording_duration: int = 5):
        """
        Run the voice agent in a conversation loop

        Args:
            recording_duration: Seconds to record for each turn
        """
        print("=" * 50)
        print("🤖 Simple AI Voice Agent")
        print("=" * 50)
        print("\nWelcome! I'm your AI voice assistant.")
        print(f"I'll record for {recording_duration} seconds each time.")
        print("Say 'exit', 'quit', or 'goodbye' to end the conversation.")
        print("\nPress Ctrl+C at any time to quit.")
        print("=" * 50)

        # Initial greeting
        greeting = "Hello! I'm your AI voice assistant. How can I help you today?"
        self.speak(greeting)

        # Conversation loop
        while True:
            print("\n" + "-" * 50)
            if not self.chat_once(recording_duration):
                break

        print("\n" + "=" * 50)
        print("Session ended. Conversation history saved.")
        print("=" * 50)


def main():
    """Main entry point"""
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("=" * 50)
        print("❌ Error: OpenAI API key not found")
        print("=" * 50)
        print("\nPlease set your OpenAI API key:")
        print("  export OPENAI_API_KEY='sk-your-key-here'")
        print("\nOr on Windows:")
        print("  set OPENAI_API_KEY=sk-your-key-here")
        print("=" * 50)
        sys.exit(1)

    # Get recording duration from command line or use default
    duration = 5
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
            if duration < 1 or duration > 30:
                print("Warning: Duration should be between 1-30 seconds. Using 5.")
                duration = 5
        except ValueError:
            print("Warning: Invalid duration. Using default of 5 seconds.")

    # Create and run agent
    try:
        agent = SimpleVoiceAgent(api_key=api_key)
        agent.run(recording_duration=duration)
    except KeyboardInterrupt:
        print("\n\n👋 Interrupted. Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
