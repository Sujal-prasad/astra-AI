import os
from pathlib import Path

from faster_whisper import WhisperModel
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".ENV")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
HINGLISH_SOURCE_LANGUAGE = os.getenv("HINGLISH_SOURCE_LANGUAGE", "hi")

_model = None


def load_model():
    global _model

    if _model is None:
        _model = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, (os.cpu_count() or 2) - 2),
        )

    return _model


def transcribe_chunk(chunk_path: str, language: str = "english", on_progress=None) -> str:
    model = load_model()

    if language.lower() == "hinglish":
        segments, info = model.transcribe(
            chunk_path,
            task="translate",
            language=HINGLISH_SOURCE_LANGUAGE,
        )
    else:
        segments, info = model.transcribe(chunk_path, task="transcribe")

    duration = getattr(info, "duration", 0) or 0
    texts = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            texts.append(text)
        if on_progress and duration:
            on_progress(min(1.0, segment.end / duration))

    return " ".join(texts)


def transcribe_all(chunks: list, language: str = "english", progress_callback=None) -> str:
    if not chunks:
        raise RuntimeError("No audio chunks were produced from the input")

    transcripts = []
    for index, chunk in enumerate(chunks, start=1):
        if not os.path.isfile(chunk):
            raise FileNotFoundError(f"Audio chunk {index} was not found: {chunk}")
        def report(position, index=index):
            progress_callback({
                "stage": "transcribing",
                "status": "running",
                "current": index,
                "completed": position,
                "total": len(chunks),
            })

        if progress_callback:
            report(index - 1)
        try:
            transcripts.append(
                transcribe_chunk(
                    chunk,
                    language=language,
                    on_progress=(lambda f, i=index: report(i - 1 + f)) if progress_callback else None,
                )
            )
            if progress_callback:
                report(index)
        except Exception as error:
            raise RuntimeError(f"Transcription failed on audio chunk {index}: {error}") from error

    if progress_callback:
        progress_callback({"stage": "transcribing", "status": "finished", "total": len(chunks)})
    return " ".join(text.strip() for text in transcripts if text.strip())
