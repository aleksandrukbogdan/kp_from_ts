
import os
from dotenv import load_dotenv
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load env
loaded = load_dotenv()
logger.info(f"Dotenv loaded: {loaded}")

doc_chunk_size = os.getenv("DOC_CHUNK_SIZE")
logger.info(f"DOC_CHUNK_SIZE from env: {doc_chunk_size}")

if doc_chunk_size is None:
    logger.warning("DOC_CHUNK_SIZE is None!")
else:
    logger.info(f"DOC_CHUNK_SIZE int: {int(doc_chunk_size)}")

# Simulate split logic
CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", 50000))
logger.info(f"Calculated CHUNK_SIZE: {CHUNK_SIZE}")

# Create dummy file
dummy_file = "dummy_big_file.md"
with open(dummy_file, "wb") as f:
    f.write(b"a" * 60000)

def _split_text_sync(md_file_path: str):
    CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", 50000))
    OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", 2000))
    
    chunks_defs = []
    
    with open(md_file_path, "rb") as f:
        content = f.read()
        
    text_len = len(content)
    start = 0
    
    while start < text_len:
        end = min(start + CHUNK_SIZE, text_len)
        
        # Simplified logic from activities.py (no newline search for this test)
        
        chunks_defs.append({
            "start": start,
            "end": end,
            "len": end - start
        })
        
        if end >= text_len:
            break
            
        start = max(0, end - OVERLAP)
        
    return chunks_defs

chunks = _split_text_sync(dummy_file)
for i, c in enumerate(chunks):
    logger.info(f"Chunk {i}: len={c['len']}")

# Cleanup
if os.path.exists(dummy_file):
    os.remove(dummy_file)
