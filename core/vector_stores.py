import os
from pathlib import Path
from uuid import uuid4

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHROMA_DIR = str(Path(__file__).resolve().parents[1] / "vector_db")
COLLECTION_NAME = "meeting_transcripts"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 1400
CHUNK_OVERLAP = 200

def get_embeddings():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL, model_kwargs={"device": "cpu"})

def build_vector_store(transcripts:str)->Chroma:
    if not transcripts or not transcripts.strip():
        raise ValueError("Cannot build a vector store from an empty transcript")

    splitter=RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE,chunk_overlap=CHUNK_OVERLAP)
    chunks=splitter.split_text(transcripts)
    docs=[Document(page_content=chunk, metadata={"chunk_index": i}) for i, chunk in enumerate(chunks)]
    embeddings=get_embeddings()
    vector_store=Chroma.from_documents(
        docs,
        embedding=embeddings,
        persist_directory=CHROMA_DIR,
        collection_name=f"{COLLECTION_NAME}_{uuid4().hex}",
    )
    return vector_store

def load_vector_store(collection_name:str=COLLECTION_NAME)->Chroma:
    embeddings=get_embeddings()
    vector_store=Chroma(persist_directory=CHROMA_DIR,collection_name=collection_name,embedding_function=embeddings)
    return vector_store

def get_retriever(vector_store:Chroma=None,k:int=4):
    return vector_store.as_retriever(search_kwargs={"k": k}, search_type="similarity") if vector_store else None
