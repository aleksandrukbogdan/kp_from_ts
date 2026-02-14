
import lancedb
import logging
from sentence_transformers import SentenceTransformer
import sys

# Setup basics
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag_debug")

DB_PATH = "./lancedb_data"

def debug_rag():
    print(f"Opening DB at {DB_PATH}...")
    try:
        db = lancedb.connect(DB_PATH)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    tables = db.table_names()
    print(f"Tables found: {tables}")
    
    if not tables:
        print("No tables found. Cannot debug.")
        return

    # Load model for manual embedding check
    print("Loading model for comparison...")
    model = SentenceTransformer("BAAI/bge-m3", device="cpu") # Use CPU for safety in script
    
    query_text = "Интеграцию в удостоверяющими центрами республики"
    bad_match_text = "интеграцию с платежными системами"
    
    # Calculate direct similarity
    emb_q = model.encode([query_text], normalize_embeddings=True)[0]
    emb_b = model.encode([bad_match_text], normalize_embeddings=True)[0]
    
    # Cosine Similarity = dot product of normalized vectors
    similarity = emb_q @ emb_b
    distance = 1.0 - similarity
    print(f"\nDirect Comparison:")
    print(f"Query: '{query_text}'")
    print(f"Bad Match: '{bad_match_text}'")
    print(f"Cosine Similarity: {similarity:.4f}")
    print(f"Distance (1-Sim): {distance:.4f}")
    
    # Search in tables
    for t_name in tables:
        print(f"\n--- Table: {t_name} ---")
        tbl = db.open_table(t_name)
        print(f"Rows: {tbl.count_rows()}")
        
        # Search
        try:
            results = tbl.search(emb_q).limit(3).to_list()
            for i, r in enumerate(results):
                dist = r.get('_distance', -1)
                txt = r.get('text', '')[:100]
                print(f"Result {i+1}: Dist={dist:.4f} | Text='{txt}...'")
        except Exception as e:
            print(f"Search failed: {e}")

if __name__ == "__main__":
    debug_rag()
