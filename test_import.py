import sys
import os

try:
    print("Importing schemas...")
    import schemas
    print("Schemas imported.")

    print("Importing llm_service...")
    import llm_service
    print("LLMService imported.")

    print("Importing activities...")
    import activities
    print("Activities imported.")
    
    print("Check complete. Syntax looks OK.")

except Exception as e:
    print(f"Import Error: {e}")
    sys.exit(1)
