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


def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    model = load_model()

    if language.lower() == "hinglish":
        segments, _ = model.transcribe(
            chunk_path,
            task="translate",
            language=HINGLISH_SOURCE_LANGUAGE,
        )
    else:
        segments, _ = model.transcribe(chunk_path, task="transcribe")

    return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


def transcribe_all(chunks: list, language: str = "english", progress_callback=None) -> str:
    if not chunks:
        raise RuntimeError("No audio chunks were produced from the input")

    transcripts = []
    for index, chunk in enumerate(chunks, start=1):
        if not os.path.isfile(chunk):
            raise FileNotFoundError(f"Audio chunk {index} was not found: {chunk}")
        if progress_callback:
            progress_callback({
                "stage": "transcribing",
                "status": "running",
                "current": index,
                "completed": max(0, index - 1),
                "total": len(chunks),
            })
        try:
            transcripts.append(transcribe_chunk(chunk, language=language))
            if progress_callback:
                progress_callback({
                    "stage": "transcribing",
                    "status": "running",
                    "current": index,
                    "completed": index,
                    "total": len(chunks),
                })
        except Exception as error:
            raise RuntimeError(f"Transcription failed on audio chunk {index}: {error}") from error

    if progress_callback:
        progress_callback({"stage": "transcribing", "status": "finished", "total": len(chunks)})
    return " ".join(text.strip() for text in transcripts if text.strip())
