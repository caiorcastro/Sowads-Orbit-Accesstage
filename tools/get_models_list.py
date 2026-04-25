import google.generativeai as genai
import os

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Set GEMINI_API_KEY environment variable first.")
    exit(1)

genai.configure(api_key=api_key)

try:
    os.makedirs('modelos', exist_ok=True)
    with open('modelos/modelos_disponiveis.txt', 'w') as f:
        f.write("Modelos Disponíveis para sua Chave:\n")
        f.write("===================================\n")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                f.write(f"- {m.name}\n")
    print("Models listed in modelos/modelos_disponiveis.txt")
except Exception as e:
    print(f"Error: {e}")
