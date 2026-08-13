"""
services/rag_service.py — builds and queries a per-user FAISS index over their
resume text, using LangChain's text splitter + a Sentence-Transformers embedding
model. This is what lets Gemini ask questions grounded in the candidate's actual
projects/skills instead of a generic question bank.
"""
import os
from typing import List

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.docstore.document import Document

from config import settings

_embeddings = None


def get_embeddings():
    """Lazily load the Sentence-Transformers model (expensive, so load once)."""
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
    return _embeddings


def _index_path(namespace: str) -> str:
    return os.path.join(settings.VECTOR_DB_DIR, namespace)


def build_index(namespace: str, raw_text: str) -> str:
    """
    Chunk resume text and persist a FAISS index for it under `namespace`
    (typically f"user_{user_id}_resume_{resume_id}").
    Returns the on-disk path of the saved index.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)
    chunks = splitter.split_text(raw_text)
    documents = [Document(page_content=chunk, metadata={"namespace": namespace}) for chunk in chunks]

    vectorstore = FAISS.from_documents(documents, get_embeddings())
    path = _index_path(namespace)
    os.makedirs(settings.VECTOR_DB_DIR, exist_ok=True)
    vectorstore.save_local(path)
    return path


def load_index(namespace: str) -> FAISS:
    path = _index_path(namespace)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No FAISS index found for namespace '{namespace}'")
    return FAISS.load_local(path, get_embeddings(), allow_dangerous_deserialization=True)


def retrieve_relevant_context(namespace: str, query: str, k: int = 4) -> List[str]:
    """Return the top-k resume chunks most relevant to `query` (e.g. the job role
    or interview type), to feed into the Gemini question-generation prompt."""
    try:
        vectorstore = load_index(namespace)
    except FileNotFoundError:
        return []
    results = vectorstore.similarity_search(query, k=k)
    return [doc.page_content for doc in results]
