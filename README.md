# LiveKit Voice Interruption Handler: Smart Filler Filtering

This project implements an intelligent extension layer to refine LiveKit's Voice Activity Detection (VAD) interruptions, ensuring a more seamless and natural conversational flow by intelligently filtering out common filler words ("uh," "umm," "haan") when the agent is speaking. This extension layer operates externally to LiveKit's core SDK, preserving the base VAD logic.

-----

## 1\. What Changed: Overview of New Modules, Params, and Logic

This feature introduces two key components and significant modifications to the main agent logic to implement contextual filler filtering.

### New Module: `examples/voice_agents/interrupt_handler.py`

A new modular class, **`SmartInterruptHandler`**, was created to contain the state and core filtering logic.

| Component | Logic/Function | Description |
| :--- | :--- | :--- |
| `_is_agent_speaking` | State Variable | Tracks the agent's current TTS status (True/False). Updated via session event callbacks. |
| `DEFAULT_FILLERS` | Configuration | Loads ignored words (default: **`'uh', 'umm', 'hmm', 'haan'`**) from the optional environment variable `IGNORED_WORDS`. |
| `should_process_transcription` | **Core Filtering Logic** | 1. If the agent is **quiet**, returns `True` (all speech is valid input). 2. If the agent is **speaking**, cleans the input (removes punctuation) and checks if the entire transcription consists **only** of ignored filler words. If so, returns `False` (drops the event to maintain flow). Otherwise, returns `True` (real interruption detected). |
| `update_ignored_words` | **Bonus Challenge** | Dynamically modifies the `_ignored_words` set at runtime for flexibility and language agnosticism. |

### Edits to `basic_agent.py`

The existing `basic_agent.py` file required three crucial modifications for integration:

| Change Category | Implementation Detail | Purpose |
| :--- | :--- | :--- |
| **STT Interception** | **Override `stt_node(self, audio, model_settings)`** | This method intercepts the real-time transcription stream (`AsyncIterable[stt.SpeechEvent]`) before it reaches the main session processing. It calls `self.interrupt_handler.should_process_transcription()` and **drops the event (`continue`)** if it's determined to be a filler, preventing a false interruption. |
| **Agent State Tracking** | **Added `tts_started` and `tts_ended` event handlers** | These callbacks set the `interrupt_handler`'s internal state (`_is_agent_speaking = True/False`) immediately upon TTS events, providing the real-time context needed for accurate filtering. |
| **Function Tool** | **Added `@function_tool` `update_settings`** | Exposes the `update_ignored_words` method from the handler to the LLM, enabling the **dynamic update** bonus challenge (e.g., the user can command the agent to ignore a new word). |
| **Config Update** | **Updated STT and Audio Options** | Changed STT model to `"deepgram/nova-3:multi"` for multi-language readiness (bonus) and enabled Krisp BVC for noise cancellation. |

-----

## 2\. What Works: Features Verified

The core logic successfully achieved the objective of distinguishing purposeful interruptions from speech fillers, ensuring the agent remains responsive to commands without reacting unnecessarily.

| Scenario | Test Input (Spoken) | Expected Outcome | Actual Result |
| :--- | :--- | :--- | :--- |
| **User Filler (Agent Speaks)** | "uh, umm, haan" | Agent ignores input and continues speaking seamlessly. | **Verified:** TTS continued without interruption. |
| **User Real Interruption (Agent Speaks)** | "wait one second" | Agent immediately stops TTS to process the command. | **Verified:** TTS stopped instantly; agent began generating a response. |
| **Mixed Filler and Command** | "umm okay stop" | Agent stops (contains valid command). | **Verified:** The presence of "okay stop" triggered an immediate stop and new turn. |
| **User Filler (Agent Quiet)** | "umm" | System registers the speech event. | **Verified:** Agent processed the input and began a new turn/response. |

-----

## 3. Known Issues: Any Edge Cases or Instability Observed

The fundamental implementation goals (contextual filler filtering) are robust. However, challenges and an operational bug were identified, primarily related to the bonus features:

* **Dynamic Update Bug (LLM Integration):** When a new word is successfully added to the ignored list via the `update_settings` function tool (the agent confirms the word has been added), the filtering **does not apply immediately and naturally** to subsequent turns. This operational bug persists despite intercepting and modifying both **interim and final STT scripts** in `stt_node`, suggesting a latency or caching issue within the agent session's processing pipeline for dynamic configuration changes.
* **Low-Confidence Threshold Feature:** While a direct, numerical ASR confidence threshold check (as might be desired for the Background murmur scenario) was not available, the **low-confidence filtering feature** works clearly in practice. This is achieved heuristically by **discarding events where transcription text**, after cleaning/stripping non-word characters, is empty, effectively filtering out very low-confidence noise artefacts before they reach the LLM.

* **Multi-Language Complexity:** Due to the configuration of the STT model to handle multi-language input (deepgram/nova-3:multi), the agent can recognise and understand shifts into Hindi (Hinglish), successfully processing mixed-language input even though its TTS is strictly English-only. Pre-configured Hinglish fillers (e.g., 'haan') work correctly as long as they are present in the initial IGNORED_WORDS list. However, dynamic addition of new non-English words is currently impacted by the Dynamic Update Bug described above.

--------

## 4\. Steps to Test: How to Start the Agent and Verify

Follow these steps to set up and verify the intelligent interruption handler.

### Set Environment Variables:

The `IGNORED_WORDS` environment variable is crucial for configuring the filler list.

```bash
# LiveKit Credentials
export LIVEKIT_URL="ws://<livekit-host>.livekit.cloud"
export LIVEKIT_API_KEY="LK_AK_..."
export LIVEKIT_API_SECRET="LK_SK_..."

# LLM/TTS/STT Credentials (e.g., OpenAI)
export OPENAI_API_KEY="sk-..."

# Custom Filler Words (default: uh,umm,hmm,haan)
# Ensure these words are present to test the filtering logic
export IGNORED_WORDS="uh,umm,hmm,haan,accha, theek" 
```

## 5\. Configuration and Setup Instructions

Detailed steps and commands required to set up and run the enhanced LiveKit agent, including environment configuration for the filler word handler.

-----

### a\.  Clone the Repository & Setup Branch

You'll need to clone your forked repository and switch to the development branch.

  * **Clone & Navigate:**
    ```bash
    git clone <your-repo-url>
    cd <repo-name>
    ```
  * **Checkout Feature Branch:**
    ```bash
    git checkout feature/livekit-interrupt-handler-<yourname>
    ```

-----

### b\. Set Environment Variables

Configure the necessary LiveKit credentials and the custom list of words that the agent should ignore during its own speaking turn.

  * **Core Credentials:**
    ```bash
    export LIVEKIT_URL="ws://<your-livekit-server>"
    export LIVEKIT_API_KEY="<your-api-key>"
    export LIVEKIT_API_SECRET="<your-api-secret>"
    export OPENAI_API_KEY="sk-..."  # Or credentials for your chosen LLM/ASR/TTS provider (in this case- Deepgram and Cartesia)
    ```
  * **Custom Filler Configuration:**
    The `IGNORED_WORDS` variable is used by the `SmartInterruptHandler` to identify and filter filler sounds.
    ```bash
    export IGNORED_WORDS='uh, umm, hmm, haan, you know' 
    ```

-----

### c\. Install Dependencies

Install all necessary Python packages and LiveKit plugins.

  * **Installation:**
    ```bash
    pip install -r requirements.txt
    ```

-----

### d\. Run the Agent

Execute the agent worker using the LiveKit CLI, pointing it to the correct entry point (`basic_agent.py` in the modified examples directory).

  * **Run Command:**
    ```bash
    python -m examples.voice_agents.basic_agent start
    ```
    *Note: The entry point function for the agent session is configured within `basic_agent.py` to initialize the `SmartInterruptHandler`.*

### Perform Verification Tests (Spoken Voice Prompts):

1.  **Initialization:** Wait for the agent to greet you. (Agent is now speaking).
2.  **Test Ignore (Filler):** While the agent is speaking: **"uh umm haan"**
      * *Expected Outcome:* The agent **must not stop** and continues its sentence.
3.  **Test Interrupt (Command):** Wait for the agent to start speaking again, then say: **"wait one second"**
      * *Expected Outcome:* The agent **must stop immediately** and wait for or respond to your command.
4.  **Test Mixed (Command Wins):** Wait for the agent to start speaking again, then say: **"umm okay stop"**
      * *Expected Outcome:* The agent **must stop immediately**, recognizing the explicit command despite the preceding filler.
5.  **Test Quiet (Filler is Valid):** Wait until the agent is completely silent, then say: **"umm"**
      * *Expected Outcome:* The agent registers the speech and begins a new turn/response.

-----

## 5\. Environment Details

  * **GitHub Branch URL:** `feature/livekit-interrupt-handler-KabeerSanan`.
  * **Python Version:** Python 3.10+
  * **Core Dependencies:** `livekit-agents`, `livekit-plugins-openai` (or equivalent LLM/STT/TTS plugin).
  * **Config Instructions:** Standard LiveKit environment variables are required for connection, in addition to the optional `IGNORED_WORDS` list.
