import os
import re
import requests
import azure.cognitiveservices.speech as speechsdk
from typing import Any, Dict, List, Optional


class SpeechService:
    # Handles Azure AI Speech for speech-to-text (STT) and text-to-speech (TTS).

    def __init__(self, key: str, region: str) -> None:
        # Initialize Azure Speech configuration, synthesizer, and recognizer.
        self.speech_config: speechsdk.SpeechConfig = speechsdk.SpeechConfig(subscription=key, region=region)
        self.speech_config.speech_recognition_language = "en-US"
        self.speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"  # Call center–friendly voice.

        self.synthesizer: speechsdk.SpeechSynthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config)
        self.recognizer: speechsdk.SpeechRecognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config)

    def recognize_speech(self) -> str:
        # Listen to microphone and return recognized text.
        print("[Listening ...]")
        result: speechsdk.SpeechRecognitionResult = self.recognizer.recognize_once_async().get()
        return result.text

    def speak_text(self, text: str) -> None:
        # Speak text aloud.
        self.synthesizer.speak_text_async(text).get()


class ReActAgent:
    # ReAct-based agent — keeps conversation history and calls OpenAI API.

    def __init__(self, api_key: str, system_prompt: str, speech_service: SpeechService) -> None:
        # API credentials and endpoint.
        self.api_key: str = api_key
        self.endpoint: str = "https://api.openai.com/v1/chat/completions"

        # gpt-4o-mini is a free-tier model, so good for OpenAI experimentation.
        # But it has a low RPM, so can't support more agent loop iterations or multi-turn conversations.
        # llama3-70b-8192 is a better free-tier option if an OpenAI model isn't required.
        self.model: str = "gpt-4o-mini"

        # Azure Speech service instance.
        self.speech: SpeechService = speech_service

        # Conversation history (system + user + assistant messages).
        self.messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    def step(self, user_input: Optional[str] = None) -> str:
        # Executes one step of the agent loop and returns the assistant's response.
        if user_input and user_input.strip():
            self.messages.append({"role": "user", "content": user_input})

        # Prepare the payload.
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": self.messages,
            "temperature": 0.7,  # Lower temperature for call center consistency.
            "max_tokens": 500
        }

        # Call the OpenAI API.
        headers: Dict[str, str] = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.post(self.endpoint, headers=headers, json=payload)
        resp.raise_for_status()

        # Extract the assistant's reply.
        data: Dict[str, Any] = resp.json()
        content: str = data.get("choices", [{}])[0].get("message", {}).get("content", "Error: No response")

        self.messages.append({"role": "assistant", "content": content})
        return content


def do_action(result: str) -> str:
    # Executes a tool call by sending it to the MCP server.
    # Returns the next prompt string for the agent loop.
    match = re.search(r"Action: ([a-zA-Z0-9_]+): (.+)", result, re.IGNORECASE)

    if match:
        # Extract tool name and argument.
        tool: str = match.group(1).strip()
        arg: str = match.group(2).strip().strip("'")

        try:
            # Prepare the MCP server JSON-RPC payload.
            payload: Dict[str, Any] = {
                "jsonrpc": "2.0",
                "method": tool,
                "params": {"input": arg},
                "id": "1"
            }

            # Call the MCP server.
            resp = requests.post("http://localhost:5000/mcp", json=payload, timeout=10)
            resp.raise_for_status()
            mcp_result: Dict[str, Any] = resp.json()

            # Extract the result or error message.
            if "result" in mcp_result:
                observation: str = mcp_result["result"]
            elif "error" in mcp_result:
                observation = f"Error: {mcp_result['error'].get('message', 'Unknown error')}"
            else:
                observation = "Error: Invalid MCP server response"

        except Exception as e:
            observation = f"Error calling MCP server: {e}"

        next_prompt: str = f"Observation: {observation}"
        print(next_prompt)
        return next_prompt

    return ""


def do_answer(result: str, answer_prefix: str, speech: SpeechService) -> str:
    # Speaks the answer, then asks if the user needs more help.
    # Returns the next prompt string or an empty string to end the loop.
    result = result.replace(answer_prefix, "")

    speech.speak_text(result)
    speech.speak_text("Is there anything else I can help you with?")

    reply: str = speech.recognize_speech()

    if "no" in reply.lower():
        speech.speak_text("OK. Thank you for being our customer. Goodbye.")
        return ""
    else:
        return reply


def run_agent() -> None:
    # Main agent loop — runs up to max_iterations.
    system_prompt: str = open("system_prompt.txt").read().strip()

    # Environment variables for API keys.
    openai_key: str = os.environ["OPENAI_API_KEY"]
    speech_key: str = os.environ["AZURE_SPEECH_KEY"]

    # Initialize services.
    speech = SpeechService(speech_key, "westus")
    agent = ReActAgent(openai_key, system_prompt, speech)

    # Initial greeting and first prompt.
    speech.speak_text("Welcome to Wa Fed bank. How may I help you?")
    next_prompt: str = speech.recognize_speech()
    max_iterations: int = 10

    # Run the agent loop.
    for _ in range(max_iterations):
        result: str = agent.step(next_prompt)
        print(result)

        # Check for Action or Answer in the result.
        if "PAUSE" in result and "Action" in result:
            next_prompt = do_action(result)
            continue

        answer_prefix: str = "Answer: "
        if answer_prefix in result:
            next_prompt = do_answer(result, answer_prefix, speech)
            if not next_prompt:
                break


if __name__ == "__main__":
    print("Press Enter to call the agent...")
    input()
    run_agent()