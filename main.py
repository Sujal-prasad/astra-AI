from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".ENV")

from utils.audio_processor import process_inputs, cleanup_files
from core.transcriber import transcribe_all
from core.summarise import summarize , generate_title
from core.extractor import extract_action_items , extract_key_decisions, extract_questions
from core.rag_engine import build_rag_chain, ask_question

def run_pipeline(source:str, language:str='english')->dict:
    chunks=process_inputs(source)
    try:
        transcript=transcribe_all(chunks,language=language)
    finally:
        cleanup_files(chunks)

    if not transcript.strip():
        raise RuntimeError(
            "No speech was detected in this recording. Check the audio, "
            "or try the other transcription language."
        )

    title=generate_title(transcript)
    summary=summarize(transcript)
    action_item=extract_action_items(transcript)
    key_decision=extract_key_decisions(transcript)
    questions=extract_questions(transcript)
    rag_chain=build_rag_chain(transcript)
    return {
        "title": title,
        "transcript": transcript,
        "summary": summary,
        "action_items": action_item,
        "key_decisions": key_decision,
        "open_questions": questions,
        "rag_chain": rag_chain,
    }


if __name__ == "__main__":
    source = input("Enter YouTube URL or local file path: ").strip()
    language = input("Language (english/hinglish): ").strip() or "english"
    result = run_pipeline(source, language)
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