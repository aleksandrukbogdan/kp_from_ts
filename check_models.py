
import logging
import time
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("model_check")

def check_models():
    print("--- Checking Embedding Models ---")
    
    try:
        import torch
        print(f"Torch Version: {torch.__version__}")
        print(f"CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"CUDA Device: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("Torch not installed.")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("SentenceTransformer not installed.")
        return

    # 1. Try BGE-M3
    print("\nAttempting to load BAAI/bge-m3...")
    start = time.time()
    try:
        model = SentenceTransformer("BAAI/bge-m3", device="cpu", model_kwargs={"use_safetensors": True})
        print(f"SUCCESS: BGE-M3 loaded in {time.time() - start:.2f}s")
        
        # Test encoding
        emb = model.encode("Test query")
        print(f"Embedding shape: {emb.shape}") # Should be 1024
        
    except Exception as e:
        print(f"FAILURE: BGE-M3 failed to load. Error: {e}")

    # 2. Try Fallback
    print("\nAttempting to load intfloat/multilingual-e5-base...")
    start = time.time()
    try:
        model = SentenceTransformer("intfloat/multilingual-e5-base", device="cpu")
        print(f"SUCCESS: e5-base loaded in {time.time() - start:.2f}s")
        
        # Test encoding
        emb = model.encode("Test query")
        print(f"Embedding shape: {emb.shape}") # Should be 768
        
    except Exception as e:
        print(f"FAILURE: e5-base failed to load. Error: {e}")

if __name__ == "__main__":
    check_models()
