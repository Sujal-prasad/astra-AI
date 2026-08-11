import json

from core.llm import build_chain, invoke_with_retry, split_transcript

TEMPERATURE = 0.2

ANALYSIS_MAP_PROMPT = """
Analyze this portion of a meeting transcript. Return ONLY valid JSON with exactly these keys:
{
  "title": "short title, max 8 words",
  "summary": ["concise bullet", "concise bullet"],
  "action_items": ["task, owner, deadline if present"],
  "key_decisions": ["decision"],
  "open_questions": ["unresolved question or follow-up"]
}
Use empty arrays when a category is not present. Do not invent information.

Transcript portion:
{text}
"""

ANALYSIS_REDUCE_PROMPT = """
Combine the following JSON analyses from consecutive portions of one meeting.
Return ONLY valid JSON with exactly these keys:
{
  "title": "short professional title, max 8 words",
  "summary": ["final concise bullet points"],
  "action_items": ["task, owner, deadline if present"],
  "key_decisions": ["final decisions"],
  "open_questions": ["unresolved questions and follow-ups"]
}
Remove duplicates, preserve important details, and do not invent information.

Partial analyses:
{text}
"""

DEFAULT_RESULT = {
    "title": "Untitled meeting",
    "summary": [],
    "action_items": [],
    "key_decisions": [],
    "open_questions": [],
}


def _parse_result(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    parsed = json.loads(text)
    result = DEFAULT_RESULT.copy()
    for key in result:
        value = parsed.get(key, result[key])
        if key == "title":
            result[key] = str(value).strip() or result[key]
        elif isinstance(value, list):
            result[key] = [str(item).strip() for item in value if str(item).strip()]
    return result


def _as_text(result: dict, key: str, empty_message: str) -> str:
    values = result.get(key, [])
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1)) or empty_message


def analyze_transcript(transcript: str, progress_callback=None) -> dict:
    chunks = split_transcript(transcript)
    if not chunks:
        return DEFAULT_RESULT.copy()

    map_chain = build_chain(ANALYSIS_MAP_PROMPT, TEMPERATURE)
    partials = []
    for index, chunk in enumerate(chunks, start=1):
        if progress_callback:
            progress_callback({
                "stage": "analyzing",
                "status": "running",
                "fraction": (index - 1) / (len(chunks) + 1),
                "message": f"Analyzing transcript section {index} of {len(chunks)}...",
            })
        raw = invoke_with_retry(
            map_chain,
            {"text": chunk},
            progress_callback=progress_callback,
        )
        try:
            partials.append(_parse_result(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            partials.append(DEFAULT_RESULT.copy())

    if len(partials) == 1:
        result = partials[0]
    else:
        reduce_chain = build_chain(ANALYSIS_REDUCE_PROMPT, TEMPERATURE)
        raw = invoke_with_retry(
            reduce_chain,
            {"text": json.dumps(partials, ensure_ascii=True)},
            progress_callback=progress_callback,
        )
        try:
            result = _parse_result(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            result = partials[0]

    return {
        "title": result["title"],
        "summary": _as_text(result, "summary", "No summary was produced."),
        "action_items": _as_text(result, "action_items", "No action items found."),
        "key_decisions": _as_text(result, "key_decisions", "No key decisions found."),
        "open_questions": _as_text(result, "open_questions", "No open questions found."),
    }
