from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.llm import get_llm, invoke_with_retry
from core.vector_stores import build_vector_store, load_vector_store, get_retriever

WHOLE_TRANSCRIPT_LIMIT = 12000
RETRIEVED_CHUNKS = 8

SYSTEM_PROMPT = """You are an expert meeting assistant. Answer the user's question
based ONLY on the meeting transcript context provided below.

If the answer is not found in the context, say:
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcript:
{context}"""


def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])


def build_prompt():
    return ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", "{question}")]
    )


def build_direct_chain(transcript: str):
    return (
        {
            "context": RunnableLambda(lambda _: transcript),
            "question": RunnablePassthrough(),
        }
        | build_prompt()
        | get_llm()
        | StrOutputParser()
    )


def build_retrieval_chain(retriever):
    return (
        {
            "context": retriever | RunnableLambda(format_docs),
            "question": RunnablePassthrough(),
        }
        | build_prompt()
        | get_llm()
        | StrOutputParser()
    )


def build_rag_chain(transcript: str):
    if len(transcript) <= WHOLE_TRANSCRIPT_LIMIT:
        return build_direct_chain(transcript)

    vector_store = build_vector_store(transcript)
    retriever = get_retriever(vector_store, k=RETRIEVED_CHUNKS)
    return build_retrieval_chain(retriever)


def load_rag_chain(collection_name: str):
    vector_store = load_vector_store(collection_name)
    retriever = get_retriever(vector_store, k=RETRIEVED_CHUNKS)
    return build_retrieval_chain(retriever)


def ask_question(rag_chain, question: str) -> str:
    print(f"Question : {question}")
    answer = invoke_with_retry(rag_chain, question)
    print(f"answer :{answer}")
    return answer
