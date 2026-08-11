import json

from core.llm import build_chain, invoke_with_retry, split_transcript

TEMPERATURE = 0.2
REDUCE_BATCH = 6
STREAM_TOKEN_TARGET = 400

ANALYSIS_MAP_PROMPT = """Analyze the portion of a meeting transcript given by the user.
Return ONLY valid JSON with exactly these keys:
{{
  "title": "short title, max 8 words",
  "summary": ["concise bullet", "concise bullet"],
  "action_items": ["task, owner, deadline if present"],
  "key_decisions": ["decision"],
  "open_questions": ["unresolved question or follow-up"]
}}
Use empty arrays when a category is not present. Do not invent information."""

ANALYSIS_REDUCE_PROMPT = """Combine the JSON analyses given by the user. They come from
consecutive portions of one meeting.
Return ONLY valid JSON with exactly these keys:
{{
  "title": "short professional title, max 8 words",
  "summary": ["final concise bullet points"],
  "action_items": ["task, owner, deadline if present"],
  "key_decisions": ["final decisions"],
  "open_questions": ["unresolved questions and follow-ups"]
}}
Remove duplicates, preserve important details, and do not invent information."""

DEFAULT_RESULT = {
    "title": "Untitled meeting",
    "summary": [],
    "action_items": [],
    "key_decisions": [],
    "open_questions": [],
}


def _flatten(value) -> str:
    if isinstance(value, dict):
        parts = [_flatten(item) for item in value.values()]
    elif isinstance(value, (list, tuple)):
        parts = [_flatten(item) for item in value]
    else:
        return str(value).strip()
    return " — ".join(part for part in parts if part)


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
            result[key] = _flatten(value) or result[key]
        elif isinstance(value, list):
            items = []
            for item in value:
                text = _flatten(item)
                if text:
                    items.append(text)
            result[key] = items
    return result


def _merge_partials(partials: list) -> dict:
    merged = DEFAULT_RESULT.copy()
    merged["title"] = next(
        (p["title"] for p in partials if p.get("title") and p["title"] != DEFAULT_RESULT["title"]),
        DEFAULT_RESULT["title"],
    )
    for key in ("summary", "action_items", "key_decisions", "open_questions"):
        collected = []
        for partial in partials:
            for item in partial.get(key, []):
                if item not in collected:
                    collected.append(item)
        merged[key] = collected
    return merged


def _section_callback(progress_callback, index: int, total: int):
    if not progress_callback:
        return None

    start = (index - 1) / (total + 1)
    end = index / (total + 1)

    def wrapped(event):
        if event.get("stage") == "analyzing" and event.get("tokens"):
            within = min(0.95, event["tokens"] / STREAM_TOKEN_TARGET)
            event = dict(event, fraction=start + (end - start) * within)
        progress_callback(event)

    return wrapped


def _reduce_batch(reduce_chain, batch: list, progress_callback) -> dict:
    raw = invoke_with_retry(
        reduce_chain,
        {"text": json.dumps(batch, ensure_ascii=True)},
        progress_callback=progress_callback,
    )
    try:
        return _parse_result(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _merge_partials(batch)


def _reduce_all(partials: list, progress_callback=None) -> dict:
    if len(partials) == 1:
        return partials[0]

    reduce_chain = build_chain(ANALYSIS_REDUCE_PROMPT, TEMPERATURE)
    level = partials

    while len(level) > 1:
        if progress_callback:
            progress_callback({
                "stage": "analyzing",
                "status": "running",
                "message": f"Merging {len(level)} analysed sections",
            })
        batches = [level[i:i + REDUCE_BATCH] for i in range(0, len(level), REDUCE_BATCH)]
        level = [
            batch[0] if len(batch) == 1 else _reduce_batch(reduce_chain, batch, progress_callback)
            for batch in batches
        ]

    return level[0]


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
            progress_callback=_section_callback(progress_callback, index, len(chunks)),
        )
        try:
            partials.append(_parse_result(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            partials.append(DEFAULT_RESULT.copy())
        if progress_callback:
            progress_callback({
                "stage": "analyzing",
                "status": "running",
                "fraction": index / (len(chunks) + 1),
                "message": f"Analyzed transcript section {index} of {len(chunks)}",
            })

    result = _reduce_all(partials, progress_callback)

    return {
        "title": result["title"],
        "summary": _as_text(result, "summary", "No summary was produced."),
        "action_items": _as_text(result, "action_items", "No action items found."),
        "key_decisions": _as_text(result, "key_decisions", "No key decisions found."),
        "open_questions": _as_text(result, "open_questions", "No open questions found."),
    }
