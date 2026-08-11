import os
from pathlib import Path

import whisper
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".ENV")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
HINGLISH_SOURCE_LANGUAGE = os.getenv("HINGLISH_SOURCE_LANGUAGE", "hi")

_model = None


def load_model():
    global _model

    if _model is None:
        _model = whisper.load_model(WHISPER_MODEL)

    return _model


def transcribe_chunk(chunk_path: str, language: str = "english") -> str:
    model = load_model()

    if language.lower() == "hinglish":
        result = model.transcribe(
            chunk_path,
            task="translate",
            language=HINGLISH_SOURCE_LANGUAGE,
        )
    else:
        result = model.transcribe(chunk_path, task="transcribe")

    return result["text"]


def transcribe_all(chunks: list, language: str = "english") -> str:
    if not chunks:
        raise RuntimeError("No audio chunks were produced from the input")

    transcripts = []
    for index, chunk in enumerate(chunks, start=1):
        if not os.path.isfile(chunk):
            raise FileNotFoundError(f"Audio chunk {index} was not found: {chunk}")
        try:
            transcripts.append(transcribe_chunk(chunk, language=language))
        except Exception as error:
            raise RuntimeError(f"Transcription failed on audio chunk {index}: {error}") from error

    return " ".join(text.strip() for text in transcripts if text.strip())
