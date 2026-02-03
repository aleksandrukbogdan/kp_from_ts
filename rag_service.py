
import os
import shutil
import logging
from typing import List, Dict, Optional, Any
import numpy as np

try:
    import lancedb
    from sentence_transformers import SentenceTransformer
    HAS_RAG_DEPS = True
except ImportError:
    HAS_RAG_DEPS = False

# Setup Logger
logger = logging.getLogger("rag_service")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Global embedding model cache (to avoid reloading on every activity call if worker persists)
_EMBEDDING_MODEL = None

def get_embedding_model():
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None and HAS_RAG_DEPS:
        logger.info("Loading BGE-M3 model...")
        # BAAI/bge-m3 is robust but large. 
        # Fallback to smaller if needed? The user suggested BGE-M3 explicitly.
        # "kviklet/bge-m3" or "BAAI/bge-m3"
        try:
             _EMBEDDING_MODEL = SentenceTransformer("BAAI/bge-m3")
             # Optimization: Compile if possible?
        except Exception as e:
            logger.error(f"Failed to load BGE-M3: {e}")
            raise
    return _EMBEDDING_MODEL

class RAGService:
    def __init__(self, index_path: str = "./lancedb_data"):
        if not HAS_RAG_DEPS:
            logger.warning("RAG dependencies not installed (lancedb, sentence-transformers). RAG disabled.")
            return

        self.index_path = index_path
        os.makedirs(self.index_path, exist_ok=True)
        self.db = lancedb.connect(self.index_path)
        self.model = get_embedding_model()
        self.table_name = "requirements"

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embeds a list of texts using BGE-M3."""
        if not self.model:
             return []
        
        # BGE-M3 can support passing instructions, but standard usage is fine for dense retrieval
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def create_index(self, chunks: List[Dict[str, Any]], table_name: str = "requirements"):
        """
        Creates (overwrites) the vector index with the given chunks.
        """
        if not HAS_RAG_DEPS: return

        # Prepare data for LanceDB
        texts = [c['text'] for c in chunks]
        logger.info(f"Embedding {len(texts)} chunks for table {table_name}...")
        vectors = self.embed_texts(texts)
        
        data = []
        for i, chunk in enumerate(chunks):
            data.append({
                "vector": vectors[i],
                "text": chunk['text'],
                "page_number": chunk.get('page_number', 0),
                "bbox": str(chunk.get('bbox', [])),
                "source_file": chunk.get('source_file', "")
            })

        logger.info(f"Saving to LanceDB table: {table_name}...")
        try:
            self.db.create_table(table_name, data, mode="overwrite")
            logger.info("Index created successfully.")
        except Exception as e:
            logger.error(f"Failed to create LanceDB table: {e}")
            raise

    def search(self, query: str, table_name: str = "requirements", top_k: int = 1) -> List[Dict[str, Any]]:
        """
        Searches the index for the query.
        """
        if not HAS_RAG_DEPS: return []

        try:
            table = self.db.open_table(table_name)
        except Exception:
            logger.warning(f"Table {table_name} not found.")
            return []

        # Embed query
        query_vec = self.embed_texts([query])[0]
        
        # Search
        results = table.search(query_vec).limit(top_k).to_list()
        return results

    def clear(self):
        """Removes the index directory."""
        if os.path.exists(self.index_path):
            shutil.rmtree(self.index_path)
