from core.llm import map_reduce

TEMPERATURE = 0.2

ACTION_MAP_PROMPT = (
    "You are an expert meeting analyst. From this portion of a meeting transcript, "
    "extract every action item. For each provide:\n"
    "- Task description\n"
    "- Owner (who is responsible)\n"
    "- Deadline (if mentioned, else write 'Not specified')\n\n"
    "Format as a numbered list. If none are found in this portion, reply with nothing."
)

ACTION_REDUCE_PROMPT = (
    "You are an expert meeting analyst. These are action items extracted from "
    "consecutive portions of one meeting. Merge them into a single numbered list, "
    "removing duplicates and keeping the owner and deadline for each. "
    "If the list is empty say 'No action items found.'"
)

DECISION_MAP_PROMPT = (
    "You are an expert meeting analyst. From this portion of a meeting transcript, "
    "extract every key decision that was made. Format as a numbered list. "
    "If none are found in this portion, reply with nothing."
)

DECISION_REDUCE_PROMPT = (
    "You are an expert meeting analyst. These are decisions extracted from "
    "consecutive portions of one meeting. Merge them into a single numbered list, "
    "removing duplicates. If the list is empty say 'No key decisions found.'"
)

QUESTION_MAP_PROMPT = (
    "From this portion of a meeting transcript, extract every unresolved question "
    "or topic needing follow-up. Format as a numbered list. "
    "If none are found in this portion, reply with nothing."
)

QUESTION_REDUCE_PROMPT = (
    "These are open questions extracted from consecutive portions of one meeting. "
    "Merge them into a single numbered list, removing duplicates and dropping any "
    "that were answered later. If the list is empty say 'No open questions found.'"
)


def extract_action_items(transcript: str, progress_callback=None) -> str:
    return map_reduce(transcript, ACTION_MAP_PROMPT, ACTION_REDUCE_PROMPT, TEMPERATURE, progress_callback)


def extract_key_decisions(transcript: str, progress_callback=None) -> str:
    return map_reduce(transcript, DECISION_MAP_PROMPT, DECISION_REDUCE_PROMPT, TEMPERATURE, progress_callback)


def extract_questions(transcript: str, progress_callback=None) -> str:
    return map_reduce(transcript, QUESTION_MAP_PROMPT, QUESTION_REDUCE_PROMPT, TEMPERATURE, progress_callback)
