import google.generativeai as genai
import os

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Set GEMINI_API_KEY environment variable first.")
    exit(1)

genai.configure(api_key=api_key)

print("Listing models...")
try:
    models = list(genai.list_models())
    if not models:
        print("No models found.")
    for m in models:
        print(f"Model: {m.name}")
except Exception as e:
    print(f"Error: {e}")
