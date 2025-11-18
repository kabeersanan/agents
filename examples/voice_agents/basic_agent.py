import logging
import os
from typing import AsyncIterable
from dotenv import load_dotenv

from livekit.agents import (
    Agent,                 
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RunContext,
    cli,
    metrics,
    room_io,
    stt,             
    ModelSettings,
    WorkerOptions,
)
#Change-1: Imported rtc from livekit specifically to handle audio data types.
from livekit import rtc
from livekit.agents.llm import function_tool
from livekit.plugins import silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from .interrupt_handler import SmartInterruptHandler

# Change-2: enable Krisp background voice/noise cancellation
from livekit.plugins import noise_cancellation

logger = logging.getLogger("basic-agent")

load_dotenv()


class MyAgent(Agent):
    #Change-3: Storing Interrupt Handler
    def __init__(self, interrupt_handler: SmartInterruptHandler) -> None:
        super().__init__(
            instructions="Your name is Kelly. You would interact with users via voice."
            "with that in mind keep your responses concise and to the point."
            "do not use emojis, asterisks, markdown, or other special characters in your responses."
            "You are curious and friendly, and have a sense of humor."
            "you will speak english to the user",
        )
        self.interrupt_handler = interrupt_handler

    async def on_enter(self):
        # when the agent is added to the session, it'll generate a reply
        # according to its instructions
        self.session.generate_reply()

    # all functions annotated with @function_tool will be passed to the LLM when this
    # agent is active
    
    #Change-4: This is the function that is responsible for handling speech-to-text problems.
    async def stt_node(
        self,
        audio: AsyncIterable[rtc.AudioFrame],
        model_settings: ModelSettings,
    ) -> AsyncIterable[stt.SpeechEvent]:
        """
        Custom Speech-to-Text (STT) interceptor node.
        
        This function sits between the STT provider (Deepgram) and the agent's logic.
        It filters out "filler" words (e.g., "umm", "uh") only when the agent is speaking,
        preventing false interruptions while allowing valid commands (e.g., "stop") to pass through.
        """

        # 1. Consume the original stream of speech events from the STT provider
        async for event in super().stt_node(audio, model_settings):

            # SAFETY CHECK: Defensive programming to prevent crashes.
            # Some control events (like RECOGNITION_USAGE or START_OF_SPEECH) do not 
            # have a 'transcript' attribute. We must check for existence before accessing.
            if not hasattr(event, 'transcript') or not event.transcript:
                yield event
                continue

            # 2. Process only FINAL transcripts
            # We only filter finalized text to avoid chopping up sentences during interim results.
            if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                
                text = event.transcript.text

                # 3. Delegate decision logic to the SmartInterruptHandler
                # If the handler determines this is just filler noise while the agent is talking,
                # we return False and DROP this event (do not yield it-or not consider it).
                if not self.interrupt_handler.should_process_transcription(text):
                    logger.info(f"Interruption suppressed: User said '{text}' while agent was speaking.")
                    continue  # Logic: Explicitly drop the event to ignore the interruption.
            
            # 4. Pass through valid events
            # If we are here, the event is either:
            #   a) A valid interruption (e.g., "Stop!")
            #   b) Speech while the agent was listening (not speaking)
            #   c) An interim transcript update
            yield event


    @function_tool
    async def lookup_weather(
        self, context: RunContext, location: str, latitude: str, longitude: str
    ):
        """Called when the user asks for weather related information.
        Ensure the user's location (city or region) is provided.
        When given a location, please estimate the latitude and longitude of the location and
        do not ask the user for them.

        Args:
            location: The location they are asking for
            latitude: The latitude of the location, do not ask user for it
            longitude: The longitude of the location, do not ask user for it
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm

#Change-5: Entry point for the voice agent: configures the session, 
# initializes AI models (STT, LLM, TTS), and sets up the interrupt handler.
@server.rtc_session()
async def entrypoint(ctx: JobContext):
    # each log entry will include these fields
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }
    ignored_words_list = os.environ.get("IGNORED_WORDS", "uh,umm,hmm,haan").split(',')
    ignored_words_set = set(word.strip().lower() for word in ignored_words_list)
    interrupt_handler = SmartInterruptHandler(ignored_words=ignored_words_set)
    
    session = AgentSession(
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # See all available models at https://docs.livekit.io/agents/models/stt/
        stt="deepgram/nova-3",
        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
        # See all available models at https://docs.livekit.io/agents/models/llm/
        llm="openai/gpt-4.1-mini",
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/
        tts="cartesia/sonic-2:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond
        # See more at https://docs.livekit.io/agents/build/turns
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # allow the LLM to generate a response while waiting for the end of turn
        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
        preemptive_generation=True,
        # sometimes background noise could interrupt the agent session, these are considered false positive interruptions
        # when it's detected, you may resume the agent's speech
        resume_false_interruption=True,
        false_interruption_timeout=1.0,
    )

    # log metrics as they are emitted, and total usage after session is over-helpful to see any problems; beneficial for debugging
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)
    @session.on("tts_started")
    def on_tts_started(event):
        logger.debug("Event: TTS started")
        interrupt_handler.set_agent_speaking(True)

    @session.on("tts_ended")
    def on_tts_ended(event):
        logger.debug("Event: TTS ended")
        interrupt_handler.set_agent_speaking(False)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    # shutdown callbacks are triggered when the session is over
    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=MyAgent(interrupt_handler=interrupt_handler),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                #to enable the Krisp BVC noise cancellation
                noise_cancellation=noise_cancellation.BVC(),
            ),
        ),
    )

# Change -6: Main execution block: configures and runs the agent worker with 
# the defined entrypoint and prewarm functions.
if __name__ == "__main__":
    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        prewarm_fnc=prewarm,
    )
    cli.run_app(opts)