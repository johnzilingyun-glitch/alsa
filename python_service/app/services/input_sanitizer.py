"""Input Sanitizer — protects against Prompt Injection attacks.

Sanitizes user-controlled inputs (stock names, search results) before
they are injected into LLM prompts.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Known prompt injection patterns
INJECTION_PATTERNS = [
    # English injection patterns
    r'ignore\s+(?:all\s+)?(?:previous|prior|above|earlier|all)\s+(?:instructions?|prompts?|rules?|directives?)',
    r'you\s+are\s+now\s+',
    r'system\s*:\s*',
    r'<\|im_start\|>',
    r'<\|im_end\|>',
    r'<<SYS>>',
    r'\[/INST\]',
    r'###\s*(?:System|Instruction|Human|Assistant)\s*:',
    r'```(?:system|instruction)',
    # Chinese injection patterns
    r'忽略(?:前面|之前|以上|之前)?的(?:所有)?(?:指令|提示|规则|指示)',
    r'你现在是',
    r'系统(?:提示|指令)\s*[:：]',
    # Common LLM delimiter injection
    r'---+\s*(?:END|STOP|RESET)',
    r'HUMAN\s*:',
    r'ASSISTANT\s*:',
    r'<<HUMAN>>',
    r'<<ASSISTANT>>',
]

# Characters that should never appear in stock names
FORBIDDEN_CHARS = re.compile(r'[<>{}|\\^~\[\]`]')

# Maximum length for stock names
MAX_NAME_LENGTH = 50


class InputSanitizer:
    """Sanitizes inputs before they are injected into LLM prompts."""

    def __init__(self):
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    def sanitize_stock_name(self, name: str) -> str:
        """
        Sanitize a stock name for safe injection into prompts.
        
        - Removes potential injection payloads
        - Strips special characters
        - Enforces length limit
        """
        if not name:
            return name

        # Remove potential injection patterns
        sanitized = name
        for pattern in self._compiled_patterns:
            sanitized = pattern.sub('[FILTERED]', sanitized)

        # Remove forbidden characters
        sanitized = FORBIDDEN_CHARS.sub('', sanitized)

        # Truncate to max length
        if len(sanitized) > MAX_NAME_LENGTH:
            sanitized = sanitized[:MAX_NAME_LENGTH]

        return sanitized.strip()

    def sanitize_search_result(self, text: str) -> str:
        """
        Sanitize search results before injection into prompts.
        
        Search results from external sources may contain injection payloads.
        """
        if not text:
            return text

        sanitized = text
        for pattern in self._compiled_patterns:
            sanitized = pattern.sub('[FILTERED]', sanitized)

        # Remove potential HTML/script tags
        sanitized = re.sub(r'<[^>]+>', '', sanitized)

        # Truncate very long results
        max_result_length = 2000
        if len(sanitized) > max_result_length:
            sanitized = sanitized[:max_result_length] + '...[truncated]'

        return sanitized

    def sanitize_query(self, query: str) -> str:
        """
        Sanitize user search queries.
        
        Allows most characters but removes injection patterns.
        """
        if not query:
            return query

        sanitized = query
        for pattern in self._compiled_patterns:
            sanitized = pattern.sub('[FILTERED]', sanitized)

        # Enforce reasonable length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]

        return sanitized.strip()

    def has_injection_risk(self, text: str) -> bool:
        """
        Check if text contains potential injection patterns.
        Returns True if suspicious patterns are detected.
        """
        if not text:
            return False
        for pattern in self._compiled_patterns:
            if pattern.search(text):
                return True
        return False


# Singleton
input_sanitizer = InputSanitizer()
