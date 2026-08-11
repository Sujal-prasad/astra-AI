from core.llm import build_chain, invoke_with_retry, map_reduce

TEMPERATURE = 0.3
TITLE_INPUT_LIMIT = 2000

SUMMARY_MAP_PROMPT = "Summarize this portion of a meeting transcript concisely."

SUMMARY_REDUCE_PROMPT = (
    "You are an expert meeting summarizer. Combine these partial summaries "
    "into one final professional meeting summary in bullet points."
)

TITLE_PROMPT = (
    "Based on the meeting transcript, generate a short professional meeting title "
    "(max 8 words). Only return the title, nothing else."
)


def summarize(transcript: str, progress_callback=None) -> str:
    return map_reduce(
        transcript,
        SUMMARY_MAP_PROMPT,
        SUMMARY_REDUCE_PROMPT,
        TEMPERATURE,
        progress_callback=progress_callback,
    )


def generate_title(transcript: str, progress_callback=None) -> str:
    chain = build_chain(TITLE_PROMPT, TEMPERATURE)
    title = invoke_with_retry(
        chain,
        {"text": transcript[:TITLE_INPUT_LIMIT]},
        progress_callback=progress_callback,
    )
    return title.strip().strip('"').strip()
