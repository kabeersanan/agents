import logging
import os
import re
from typing import Set

logger = logging.getLogger(__name__)

class SmartInterruptHandler:
    """
    An extension layer for LiveKit Agents to intelligently filter filler words 
    and reliably detect genuine user interruptions.

    Fulfills the objective to:
    1. Ignore filler words (e.g., 'uh', 'umm') only when the agent is speaking.
    2. Register all user speech as valid when the agent is quiet.
    """
    
    # 1. Use a class-level attribute for configuration via environment variable
    DEFAULT_FILLERS_STR = os.environ.get("IGNORED_WORDS", "uh,umm,hmm,haan")
    DEFAULT_FILLERS: Set[str] = {
        word.strip().lower() 
        for word in DEFAULT_FILLERS_STR.split(',') 
        if word.strip() # Filter out empty strings from splitting e.g. "a,b,"
    }
    
    # 2. Compile regex once at the class level for efficiency
    _PUNCTUATION_RE = re.compile(r'[^\w\s]') 

    def __init__(self, ignored_words: Set[str] = None):
        """
        Initializes the interrupt handler with an initial set of ignored words.
        """
        self._is_agent_speaking: bool = False
        # Use provided set or the class default
        self._ignored_words: Set[str] = ignored_words if ignored_words is not None else self.DEFAULT_FILLERS.copy()
        
        logger.info(f"InterruptHandler initialized with fillers: {self._ignored_words}")


    def set_agent_speaking(self, speaking: bool) -> None:
        """
        Updates the agent's current speaking state (called by a LiveKit event handler).
        """
        self._is_agent_speaking = speaking
        logger.debug(f"Agent speaking state set to: {speaking}")

    def should_process_transcription(self, transcription: str) -> bool:
        """
        Core logic to decide if a transcription should be processed (interruption) or ignored.
        
        Returns:
            True if the speech is a valid event/interruption, False if it is a filler 
            while the agent is speaking.
        """
        
        # Scenario: User filler while agent quiet -> System registers speech event
        if not self._is_agent_speaking:
            logger.debug("Agent is quiet, processing speech.")
            return True

        # Scenario: Agent is speaking, analyze the transcription for filler-only content
        normalized_text = self._PUNCTUATION_RE.sub('', transcription.lower().strip())
        
        if not normalized_text:
            return False # Ignore empty or purely punctuation transcriptions

        words = normalized_text.split()
        
        # Check if ALL extracted words are classified as filler words
        is_purely_filler = all(word in self._ignored_words for word in words)

        if is_purely_filler:
            # Scenario: User filler while agent speaks -> Agent ignores [cite: 74]
            logger.info(f"Ignoring filler interruption: '{transcription}'")
            return False
            
        # Scenario: User real interruption/Mixed filler and command -> Agent stops [cite: 76, 79]
        logger.info(f"Valid interruption detected: '{transcription}'")
        return True
    
    #Bonus Change: Dynamic Addition of Ignored Words.
    def update_ignored_words(self, word: str, action: str) -> str:
        """
        [Bonus Challenge] Dynamically adds or removes a word from the set of ignored filler words.
        
        Args:
            word: The filler word to act on (e.g., 'uh').
            action: "add" or "remove".
        """
        word = word.lower().strip()
        if not word:
             return "Cannot process an empty word."
             
        if action == "add":
            if word not in self._ignored_words:
                self._ignored_words.add(word)
                logger.info(f"Dynamically added '{word}'.")
                return f"Added '{word}' to the ignored list."
            return f"Word '{word}' is already in the ignored list."
        
        elif action == "remove":
            if word in self._ignored_words:
                self._ignored_words.remove(word)
                logger.info(f"Dynamically removed '{word}'.")
                return f"Removed '{word}' from the ignored list."
            return f"Word '{word}' not found in the ignored list."
            
        return f"Invalid action: '{action}'. Must be 'add' or 'remove'."