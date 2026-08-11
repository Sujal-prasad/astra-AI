from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".ENV")

from utils.audio_processor import process_inputs, cleanup_files
from core.transcriber import transcribe_all
from core.meeting_analysis import analyze_transcript
from core.rag_engine import build_rag_chain, ask_question

def run_pipeline(source:str, language:str='english', progress_callback=None)->dict:
    chunks=process_inputs(source, progress_callback=progress_callback)
    try:
        transcript=transcribe_all(chunks,language=language, progress_callback=progress_callback)
    finally:
        cleanup_files(chunks)

    if not transcript.strip():
        raise RuntimeError(
            "No speech was detected in this recording. Check the audio, "
            "or try the other transcription language."
        )

    if progress_callback:
        progress_callback({"stage": "analyzing", "status": "running", "fraction": 0.0, "message": "Analyzing the meeting in one pass..."})
    analysis = analyze_transcript(transcript, progress_callback=progress_callback)
    rag_chain=build_rag_chain(transcript)
    if progress_callback:
        progress_callback({"stage": "analyzing", "status": "finished", "fraction": 1.0, "message": "Meeting record ready"})
    return {
        "title": analysis["title"],
        "transcript": transcript,
        "summary": analysis["summary"],
        "action_items": analysis["action_items"],
        "key_decisions": analysis["key_decisions"],
        "open_questions": analysis["open_questions"],
        "rag_chain": rag_chain,
    }


def print_progress(progress: dict) -> None:
    stage_key = progress.get("stage", "")
    stage = stage_key.capitalize()
    event_status = progress.get("status", "")
    message = progress.get("message")
    stage_ranges = {
        "downloading": (0.0, 0.25, "Downloading audio"),
        "converting": (0.25, 0.35, "Converting audio to WAV"),
        "chunking": (0.35, 0.45, "Splitting audio into chunks"),
        "transcribing": (0.45, 0.75, "Transcribing with Whisper"),
        "analyzing": (0.75, 1.0, "Analyzing the meeting"),
    }
    start, end, label = stage_ranges.get(stage_key, (0.0, 0.0, stage))
    if stage == "Downloading" and event_status == "downloading":
        total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
        downloaded = progress.get("downloaded_bytes", 0)
        if total:
            fraction = min(1.0, downloaded / total)
            overall = start + (end - start) * fraction
            print(f"\r[{overall:6.1%}] {label}... {fraction:.0%}", end="", flush=True)
        return
    if stage == "Transcribing" and progress.get("current"):
        current = progress["current"]
        total = progress.get("total", current)
        completed = progress.get("completed", max(0, current - 1))
        overall = start + (end - start) * min(1.0, completed / total)
        print(
            f"[{overall:6.1%}] {label}... chunk {current} of {total}",
            flush=True,
        )
        return
    if "fraction" in progress:
        overall = start + (end - start) * progress["fraction"]
        clean_message = (message or label).rstrip(". ")
        print(f"[{overall:6.1%}] {clean_message}...", flush=True)
        return
    if stage == "Analyzing" and progress.get("tokens"):
        token_fraction = min(0.9, progress["tokens"] / 256)
        overall = start + (end - start) * token_fraction
        clean_message = (message or label).rstrip(". ")
        print(f"[{overall:6.1%}] {clean_message}...", flush=True)
        return
    if event_status == "finished":
        print(f"[{end:6.1%}] {message or label}", flush=True)
        return
    if message:
        print(f"[{start:6.1%}] {message}", flush=True)
    elif event_status == "running":
        print(f"[{start:6.1%}] {label}...", flush=True)


if __name__ == "__main__":
    source = input("Enter YouTube URL or local file path: ").strip()
    language = input("Language (english/hinglish): ").strip() or "english"
    result = run_pipeline(source, language, progress_callback=print_progress)
    print("\n" + "=" * 60)
    print(f" Title: {result['title']}")
    print(f"\n Summary:\n{result['summary']}")
    print(f"\n Action Items:\n{result['action_items']}")
    print(f"\n Key Decisions:\n{result['key_decisions']}")
    print(f"\n Open Questions:\n{result['open_questions']}")
    print("=" * 60)

    print("\n Chat with your meeting (type 'exit' to quit)\n")
    rag_chain = result["rag_chain"]
    while True:
        question = input("You: ").strip()
        if question.lower() in ["exit", "quit", "q"]:
            print(" Goodbye!")
            break
        if not question:
            continue
        answer = ask_question(rag_chain, question)
        print(f"\n Assistant: {answer}\n")