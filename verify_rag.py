
import asyncio
import os
import sys
import shutil
import json
from unittest.mock import MagicMock

# --- Mock Temporal ---
mock_temporal = MagicMock()
mock_activity = MagicMock()

def mock_defn(fn):
    return fn

mock_activity.defn = mock_defn
mock_activity.logger = MagicMock()
mock_activity.logger.info = print
mock_activity.logger.error = print
mock_activity.logger.warning = print

mock_temporal.activity = mock_activity
sys.modules["temporalio"] = mock_temporal
sys.modules["temporalio.activity"] = mock_activity

# --- Import Activities ---
try:
    from activities import index_document_activity, refine_requirements_activity
    from rag_service import RAGService
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

async def main():
    print("Starting RAG verification...")
    
    # 1. Cleanup Previous Index
    if os.path.exists("./lancedb_data"):
        shutil.rmtree("./lancedb_data")

    # 2. Setup Dummy Data
    test_dir = "./rag_test_data"
    os.makedirs(test_dir, exist_ok=True)
    
    md_file = os.path.join(test_dir, "test.md")
    json_file = os.path.join(test_dir, "test_parsed.json")
    
    # Dummy Markdown - Make completely distinct
    with open(md_file, "w", encoding="utf-8") as f:
        f.write("# Test Document\n\nSecurity: The system uses AES-256 for all data.\n\nFinance: The total budget allocated is 50,000 USD.")
    
    # Dummy Docling JSON
    docling_data = {
        "pages": [{"page_no": 1}],
        "texts": [
            {
                "text": "Security: The system uses AES-256 for all data.", 
                "prov": [{"page_no": 1, "bbox": [10, 10, 100, 20]}]
            },
            {
                "text": "Finance: The total budget allocated is 50,000 USD.", 
                "prov": [{"page_no": 1, "bbox": [10, 30, 100, 40]}]
            }
        ]
    }
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(docling_data, f)
        
    try:
        # 2. Test Indexing
        print("\n--- 1. Testing Indexing ---")
        # Overwrite RAG index path for test to avoid messing real data
        # We can't change it easily on valid functions without patching, 
        # so we rely on default "./lancedb_data" but we will clean it up.
        
        await index_document_activity(md_file)
        print("Indexing completed.")
        
        # 3. Test Retrieval (Refinement)
        print("\n--- 2. Testing Refinement ---")
        dummy_reqs = [
            {
                "category": "Security",
                "summary": "Encryption",
                "search_query": "support AES-256", 
                "importance": "Высокая"
            },
            {
                 "category": "Budget",
                 "summary": "Limit",
                 "search_query": "budget is 50k",
                 "importance": "Высокая"
            }
        ]
        
        refined = await refine_requirements_activity(dummy_reqs)
        
        print("\n--- Refinement Results ---")
        print(json.dumps(refined, indent=2, ensure_ascii=False))
        
        # Validations
        success = True
        if refined[0].get('source_text') != "Security: The system uses AES-256 for all data.":
            print(f"[FAIL] Match 1 incorrect: {refined[0].get('source_text')}")
            success = False
        else:
             print("[PASS] Match 1 correct")

        if refined[1].get('source_text') != "Finance: The total budget allocated is 50,000 USD.":
             print(f"[FAIL] Match 2 incorrect: {refined[1].get('source_text')}")
             success = False
        else:
             print("[PASS] Match 2 correct")
             
        if success:
            print("\n✅ RAG PIPELINE VERIFIED SUCCESSFULLY")
        else:
            print("\n❌ VERIFICATION FAILED")

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if os.path.exists(test_dir):
            try:
                shutil.rmtree(test_dir)
            except: pass

if __name__ == "__main__":
    asyncio.run(main())
