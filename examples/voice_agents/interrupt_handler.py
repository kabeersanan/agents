# examples/voice_agents/interrupt_handler.py

import logging
import os
import re

# Load default fillers from an environment variable if available, otherwise use a default list
# This makes your handler configurable as required by the assignment 
DEFAULT_FILLERS = os.environ.get("IGNORED_WORDS", "uh,umm,hmm,haan")
DEFAULT_FILLER_WORDS = set(DEFAULT_FILLERS.split(','))

logger = logging.getLogger("interrupt-handler")

class SmartInterruptHandler:
    def __init__(self, ignored_words: set[str] = DEFAULT_FILLER_WORDS):
        self._is_agent_speaking = False
        self._ignored_words = ignored_words
        
        # This regex helps strip punctuation to check words cleanly
        self._punctuation_re = re.compile(r'[^\w\s]') 
        
        logger.info(f"InterruptHandler initialized with fillers: {ignored_words}")

    def set_agent_speaking(self, speaking: bool):
        """
        An event handler will call this to update the agent's speaking state.
        """
        self._is_agent_speaking = speaking
        logger.debug(f"Agent speaking state set to: {speaking}")

    def should_process_transcription(self, transcription: str) -> bool:
        """
        This is the core logic.
        Decides if a transcription should be processed or ignored.
        """
        
        # 1. If the agent is quiet, always process the user's speech [cite: 69]
        if not self._is_agent_speaking:
            logger.debug("Agent is quiet, processing speech.")
            return True

        # 2. If agent is speaking, analyze the transcription
        normalized_text = self._punctuation_re.sub('', transcription.lower().strip())
        if not normalized_text:
            return False # Ignore empty transcriptions

        words = normalized_text.split()
        
        # Check if ALL words in the transcription are filler words
        is_purely_filler = all(word in self._ignored_words for word in words)

        # 3. If it's purely filler, ignore it [cite: 68]
        if is_purely_filler:
            logger.info(f"Ignoring filler interruption: '{transcription}'")
            return False
            
        # 4. If it contains any non-filler words, it's a valid interruption [cite: 70, 80]
        logger.info(f"Valid interruption detected: '{transcription}'")
        return True