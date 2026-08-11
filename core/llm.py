import os
import random
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv(Path(__file__).resolve().parents[1] / ".ENV")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:latest")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

CHUNK_SIZE = 3000
CHUNK_OVERLAP = 200
MAX_ATTEMPTS = 4
BASE_DELAY = 2.0

RETRYABLE_TEXT = ("timeout", "timed out", "connection reset", "temporarily unavailable", "503", "502")


class OllamaUnavailable(RuntimeError):
    pass


def ollama_available() -> bool:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        return response.ok
    except requests.RequestException:
        return False


def installed_models() -> list:
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
    except requests.RequestException:
        return []
    return [model.get("name", "") for model in response.json().get("models", [])]


def get_llm(temperature: float = 0.3):
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        num_ctx=NUM_CTX,
    )


def split_transcript(transcript: str) -> list:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    return splitter.split_text(transcript)


def is_connection_error(error: Exception) -> bool:
    message = str(error).lower()
    return "connection" in message and "refused" in message or "failed to connect" in message


def is_retryable(error: Exception) -> bool:
    message = str(error).lower()
    return any(fragment in message for fragment in RETRYABLE_TEXT)


def invoke_with_retry(chain, payload):
    for attempt in range(MAX_ATTEMPTS):
        try:
            return chain.invoke(payload)
        except Exception as error:
            if is_connection_error(error):
                raise OllamaUnavailable(
                    f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Start it with 'ollama serve' "
                    f"and make sure '{OLLAMA_MODEL}' is pulled."
                ) from error
            if attempt == MAX_ATTEMPTS - 1 or not is_retryable(error):
                raise
            time.sleep(BASE_DELAY * (2**attempt) + random.uniform(0, 1))


def build_chain(system_prompt: str, temperature: float = 0.3):
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("human", "{text}")]
    )
    return prompt | get_llm(temperature) | StrOutputParser()


def map_reduce(transcript: str, map_prompt: str, reduce_prompt: str, temperature: float = 0.3) -> str:
    chunks = split_transcript(transcript)
    if not chunks:
        return ""

    map_chain = build_chain(map_prompt, temperature)
    partials = [invoke_with_retry(map_chain, {"text": chunk}) for chunk in chunks]

    if len(partials) == 1:
        return partials[0]

    reduce_chain = build_chain(reduce_prompt, temperature)
    return invoke_with_retry(reduce_chain, {"text": "\n\n".join(partials)})
