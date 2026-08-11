from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".ENV")

from utils.audio_processor import process_inputs, cleanup_files
from core.transcriber import transcribe_all
from core.meeting_analysis import analyze_transcript
from core.progress import ProgressTracker, format_eta
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


_cli_tracker = ProgressTracker()


def print_progress(progress: dict) -> None:
    reading = _cli_tracker.update(progress)
    if reading is None:
        return

    fraction, label, eta = reading
    detail = _cli_tracker.detail(progress)
    headline = f"{label} · {detail}" if detail else label
    print(f"[{fraction:6.1%}] {headline} · {format_eta(eta)}", flush=True)


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