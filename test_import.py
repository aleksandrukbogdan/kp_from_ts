
import sys
import os

print("--- DIAGNOSTIC START ---")
print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")

try:
    print("\n1. Importing rag_service...")
    import rag_service
    print("SUCCESS: rag_service imported.")
except Exception as e:
    print(f"FAILURE: rag_service import failed: {e}")
    sys.exit(1)

try:
    print("\n2. Importing activities...")
    import activities
    print("SUCCESS: activities imported.")
except Exception as e:
    print(f"FAILURE: activities import failed: {e}")
    sys.exit(1)

try:
    print("\n3. Testing RAGService instantiation (should fail gracefully or succeed)...")
    rag = rag_service.RAGService()
    print(f"SUCCESS: RAGService instantiated. Hash: {hash(rag)}")
except Exception as e:
    print(f"WARNING/FAILURE: RAGService init failed: {e}")

print("\n--- DIAGNOSTIC END ---")
