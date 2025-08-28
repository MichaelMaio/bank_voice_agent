import os
import re
import requests
import azure.cognitiveservices.speech as speechsdk


class SpeechService:
    # Handles Azure AI Speech for speech-to-text (STT) and text-to-speech (TTS).
    def __init__(self, key, region):
        # Create speech configuration with subscription key and region.
        self.speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
        self.speech_config.speech_recognition_language = "en-US"
        self.speech_config.speech_synthesis_voice_name = "en-US-JennyNeural"  # Call center–friendly voice.

        # Create synthesizer (for output) and recognizer (for input).
        self.synthesizer = speechsdk.SpeechSynthesizer(speech_config=self.speech_config)
        self.recognizer = speechsdk.SpeechRecognizer(speech_config=self.speech_config)

    def recognize_speech(self):
        # Listen to microphone and return recognized text.
        print("[Listening ...]")
        result = self.recognizer.recognize_once_async().get()
        return result.text

    def speak_text(self, text):
        # Speak text aloud.
        self.synthesizer.speak_text_async(text).get()


class ReActAgent:
    # ReAct-based agent — keeps conversation history and calls OpenAI API.
    def __init__(self, api_key, system_prompt, speech_service):
        # API credentials and end point.
        self.api_key = api_key
        self.endpoint = "https://api.openai.com/v1/chat/completions"
        
        # gpt-4o-mini is a free-tier model, so good for OpenAI experimentation.
        # But it has a low RPM, so can't support more agent loop iterations or multi-turn conversations.
        # llama3-70b-8192 is a better free-tier option if an OpenAI model isn't required.
        self.model = "gpt-4o-mini"

        # Azure Speech service instance.
        self.speech = speech_service

        # Conversation history (system + user + assistant messages).
        self.messages = [{"role": "system", "content": system_prompt}]

    def step(self, user_input=None):
        # Executes one step of the agent loop.

        # Add user message if provided.
        if user_input and user_input.strip():
            self.messages.append({"role": "user", "content": user_input})

        # Build OpenAI request payload.
        payload = {
            "model": self.model,
            "messages": self.messages,
            "temperature": 0.7, # Lower temperature for call center consistency.
            "max_tokens": 500
        }

        # Prepare HTTP request.
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.post(self.endpoint, headers=headers, json=payload)
        resp.raise_for_status()

        # Parse response.
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "Error: No response")

        # Add assistant response to conversation history.
        self.messages.append({"role": "assistant", "content": content})

        return content

    # --- Local tool implementations ---

    # Tool: Get the name of the account holder.
    @staticmethod
    def get_account_holder():
        # TODO - enable this once multi-turn conversation is supported.
        # Requires a different model to avoid RPM violations.
        return ""

    # Tool: Get account number by name.
    @staticmethod
    def get_account_number(name):
        name = name.lower()
        if name == "michael":
            return "123456"
        elif name == "mary":
            return "789012"
        return "0"

    # Tool: Get balance for account number.
    @staticmethod
    def get_account_balance(account_number):
        if account_number == "123456":
            return "1500.00"
        elif account_number == "789012":
            return "150.00"
        return "0.00"

    # Tool: Get mailing address for account number.
    @staticmethod
    def get_account_address(account_number):
        if account_number == "123456":
            return "123 Sesame Street Suite 1, New York, NY 55555"
        elif account_number == "789012":
            return "123 Sesame Street Suite 2, New York, NY 55555"
        return ""

    # Tool: Simulate sending a new card.
    @staticmethod
    def send_new_card(address):
        return "false" if not address.strip() else "true"


# Executes a tool call based on the agent's output.
def do_action(result, tool_registry):
    # Parse tool and argument using regex.
    match = re.search(r"Action: ([a-z_]+): (.+)", result, re.IGNORECASE)

    if match:
        tool = match.group(1).strip()
        arg = match.group(2).strip().strip("'")

        # Look up and invoke the tool dynamically.
        if tool in tool_registry:
            observation = tool_registry[tool](arg
                                              )
            next_prompt = f"Observation: {observation}"
        else:
            next_prompt = "Observation: Tool not found"

        print(next_prompt)
        return next_prompt
    
    return ""


# Speaks the answer, then asks if the user needs more help.
def do_answer(result, answer_prefix, speech):
    result = result.replace(answer_prefix, "")

    # Speak the result and prompt for further assistance.
    speech.speak_text(result)
    speech.speak_text("Is there anything else I can help you with?")

    # Get user reply
    reply = speech.recognize_speech()

    if "no" in reply.lower():
        speech.speak_text("OK. Thank you for being our customer. Goodbye.")
        return ""
    else:
        # TODO - enable this once multi-turn conversation is supported.
        # Requires a different model to avoid RPM violations.
        return reply


def get_tool_registry():
    # Create tool registry mapping tool names to functions.
    tool_registry = {
        "GetAccountHolder": ReActAgent.get_account_holder,
        "GetAccountNumber": ReActAgent.get_account_number,
        "GetAccountBalance": ReActAgent.get_account_balance,
        "GetAccountAddress": ReActAgent.get_account_address,
        "SendNewCard": ReActAgent.send_new_card
    }

    return tool_registry


# Main agent loop — runs up to max_iterations.
def run_agent():
    # Load system prompt from file.
    system_prompt = open("system_prompt.txt").read().strip()

    # Load API key and Azure Speech key from environment.
    openai_key = os.environ["OPENAI_API_KEY"]
    speech_key = os.environ["AZURE_SPEECH_KEY"]

    # Create tool registry.
    tool_registry = get_tool_registry()

    # Initialize speech service and agent.
    speech = SpeechService(speech_key, "westus")

    # Initialize ReAct agent.
    agent = ReActAgent(openai_key, system_prompt, speech)

    # Greet the user and get initial prompt.
    speech.speak_text("Welcome to Wa Fed bank. How may I help you?")
    next_prompt = speech.recognize_speech()
    max_iterations = 10

    for _ in range(max_iterations):
        # Send prompt to agent and get response.
        result = agent.step(next_prompt)
        print(result)

        # If agent requests an action, parse and execute it.
        if "PAUSE" in result and "Action" in result:
            next_prompt = do_action(result, tool_registry)
            continue

        # If agent provides an answer.
        answer_prefix = "Answer: "

        if answer_prefix in result:
            next_prompt = do_answer(result, answer_prefix, speech)

            # Exit if user is done.
            if not next_prompt:
                break


if __name__ == "__main__":
    print("Press Enter to call the agent...")
    input()
    run_agent()