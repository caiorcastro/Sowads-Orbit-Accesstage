
import os
import csv
import json
import argparse
import google.generativeai as genai
import pandas as pd
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

RULES_PATH = "regras_geracao/schema_orbit_ai_v1.json"

def load_rules():
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_topics(api_key, count, explicit_theme=None, model_name="gemini-2.5-flash"):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    rules = load_rules()
    
    # Internal helper to call the API
    def call_api(qty, focus_context):
        prompt = f"""
        ROLE: Editor-in-Chief of a Viral Immigration News Portal.
        OBJECTIVE: Brainstorm {qty} unique, high-potential article topics.
        TARGET AUDIENCE: Latin Americans (High Net Worth or Professionals).
        
        CONTEXT/FOCUS: {focus_context}

        CRITERIA FOR "HIGH POTENTIAL":
        1.  **Click-Worthy:** Use emotional hooks (Curiosity, Fear of missing out, Authority).
        2.  **SEO/AIO Friendly:** Answer specific questions users ask Google/ChatGPT.
        3.  **Compliance:** DO NOT promise visas. Use terms like "Planejamento", "Possibilidades", "Carreira Internacional".
        
        OUTPUT FORMAT (JSON List):
        [
            {{
                "topic_pt": "Title in Portuguese (Brazil)",
                "topic_es": "Title in Spanish (Latam)",
                "potential_score": 9.5,
                "category": "Career/Investment/Family"
            }}
        ]
        
        Generate exactly {qty} items. Return ONLY the JSON.
        """
        try:
            print(f"{Colors.OKCYAN}   -> Brainstorming {qty} topics for: {focus_context[:40]}...{Colors.ENDC}")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            return json.loads(response.text)
        except Exception as e:
            print(f"{Colors.FAIL}Error generating topics: {e}{Colors.ENDC}")
            return []

    if explicit_theme:
        # Manual theme -> Single batch
        return call_api(count, f"Theme: '{explicit_theme}'")
    else:
        # Automated Strategy -> 75% US / 25% Dubai
        count_us = int(count * 0.75)
        count_uae = count - count_us
        
        print(f"{Colors.HEADER}Strategy: {count_us} US Topics | {count_uae} Dubai Topics{Colors.ENDC}")
        
        topics_us = call_api(count_us, "FOCUS: USA Immigration (EB-2 NIW, Green Card, Real Estate in Florida, Business Visas). Trends: Tech layoffs, healthcare shortage, aviation.")
        topics_uae = call_api(count_uae, "FOCUS: Dubai/UAE Immigration (Golden Visa, Tax-Free Living, Real Estate Investment, Freelance Visas). Trends: Remote work, crypto, safety.")
        
        return topics_us + topics_uae

def main():
    print(f"{Colors.HEADER}=== ORBIT AI TOPIC CREATOR (AI BRAINSTORM) ==={Colors.ENDC}")
    
    # Interactive or Args
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--theme", type=str, default="")
    parser.add_argument("--auto_save", action="store_true")
    args = parser.parse_args()

    # Interactive Mode
    count = args.count
    if count == 0:
        try:
            c_input = input(f"{Colors.BOLD}Quantos temas você quer gerar? (Default: 10): {Colors.ENDC}")
            count = int(c_input) if c_input.strip() else 10
        except:
            count = 10
            
    theme = args.theme
    if not theme and not args.auto_save:
        theme = input(f"{Colors.BOLD}Algum assunto específico? (Deixe em branco para usar a Base de Conhecimento): {Colors.ENDC}")

    # Generate
    topics_list = generate_topics(args.api_key, count, theme)
    
    if not topics_list:
        print("No topics generated.")
        return

    # Create DataFrame
    df = pd.DataFrame(topics_list)
    
    # Display Preview
    print(f"\n{Colors.OKGREEN}Generated {len(df)} themes:{Colors.ENDC}")
    print(df[['topic_pt', 'category']].head(5).to_string(index=False))
    print("...")

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"sugestao_temas_{timestamp}.csv"
    output_path = os.path.join("relatorios", filename)
    
    if not os.path.exists("relatorios"):
        os.makedirs("relatorios")
        
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    print(f"\n{Colors.OKBLUE}Arquivo salvo em: {output_path}{Colors.ENDC}")
    print(f"Abra este arquivo, selecione os melhores e coloque na lista de produção!")

if __name__ == "__main__":
    main()
