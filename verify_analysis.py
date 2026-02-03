
import asyncio
import os
import sys
import json
from unittest.mock import MagicMock

# 1. Mock temporalio BEFORE importing activities
# We need to simulate the decorators so that @activity.defn doesn't break
mock_temporal = MagicMock()
mock_activity = MagicMock()

def mock_defn(fn):
    return fn

mock_activity.defn = mock_defn
mock_activity.logger = MagicMock()
mock_activity.logger.info = print
mock_activity.logger.error = print
mock_activity.logger.warning = print

# CRITICAL FIX: Ensure importing 'temporalio' allows access to 'activity'
mock_temporal.activity = mock_activity

sys.modules["temporalio"] = mock_temporal
sys.modules["temporalio.activity"] = mock_activity

# 2. Import the activity
# This will import LLMService, which imports OpenAI and Pydantic (which must be installed)
try:
    from activities import analyze_requirements_chunk_activity
except ImportError as e:
    print(f"Import Error: {e}")
    print("Ensure requirements are installed: pip install openai pydantic python-dotenv")
    sys.exit(1)

async def main():
    print("Starting verification...")
    
    # 3. Create a dummy TZ file
    sample_text = """
    === ФРАГМЕНТ ТЗ ===
    1. Система должна позволять пользователям регистрироваться через Google и Яндекс.
    2. Время отклика API не должно превышать 200мс.
    3. Данные должны храниться в зашифрованном виде (AES-256).
    4. Бюджет на инфраструктуру ограничен 50 000 руб/мес.
    """
    
    filename = "test_tz_chunk.txt"
    try:
        with open(filename, "wb") as f:
            f.write(sample_text.encode("utf-8"))
            
        chunk_def = {
            "file_path": os.path.abspath(filename),
            "start": 0,
            "end": len(sample_text.encode("utf-8"))
        }
        
        # 4. Run the activity
        # Note: This will try to call the REAL LLMService.
        # Ensure QWEN_API_KEY and QWEN_BASE_URL are set in .env
        print("Running analyze_requirements_chunk_activity...")
        
        print(f"DEBUG: Type of activity function: {type(analyze_requirements_chunk_activity)}")
        print(f"DEBUG: Activity function: {analyze_requirements_chunk_activity}")
        
        coro = analyze_requirements_chunk_activity(chunk_def)
        print(f"DEBUG: Type of result (should be coroutine): {type(coro)}")
        
        results = await coro
        
        print("\n=== RAW RESULTS ===")
        print(json.dumps(results, indent=2, ensure_ascii=False))
        
        # Validation
        if len(results) > 0:
            print("\nSUCCESS: Extracted data found!")
            first = results[0]
            if "search_query" in first and first["search_query"]:
                print(f"[OK] Search Query generated: {first['search_query']}")
            else:
                print("[FAIL] 'search_query' is missing or empty")
                
            if "category" in first:
                 print(f"[OK] Category: {first['category']}")
        else:
            print("\nWARNING: No results returned. Check LLM logs above.")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if os.path.exists(filename):
            os.remove(filename)

if __name__ == "__main__":
    # Check enviroment
    from dotenv import load_dotenv
    load_dotenv()
    
    if not os.getenv("QWEN_API_KEY"):
         print("WARNING: QWEN_API_KEY not found in environment. LLM calls will fail.")
         
    asyncio.run(main())
