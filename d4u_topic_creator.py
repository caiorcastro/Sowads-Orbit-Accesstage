
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

RULES_PATH = "regras_geracao/schema_conteudo_latam_v9.json"

def load_rules():
    with open(RULES_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_topics(api_key, count, explicit_theme=None, model_name="gemini-2.5-flash"):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    rules = load_rules()
    
    # Extract high-level context from rules
    persona = rules.get("agent_profile", {}).get("primary_directive")
    compliance = rules.get("legal_and_compliance_mandates", {}).get("claims_and_promises", {})
    
    # Construct the Prompt
    theme_directive = ""
    if explicit_theme:
        theme_directive = f"FOCUS THEME: '{explicit_theme}'"
    else:
        theme_directive = "FOCUS: Analyze the 'knowledge base' implied by an Immigration Firm (EB-2 NIW, Business Visas, Real Estate in US/Dubai) and identify TRENDING, HIGH-INTEREST sub-niches (e.g., Tech Layoffs, Inflation in Latam, Remote Work)."

    prompt = f"""
    ROLE: Editor-in-Chief of a Viral Immigration News Portal.
    OBJECTIVE: Brainstorm {count} unique, high-potential article topics.
    TARGET AUDIENCE: Latin Americans (High Net Worth or Professionals) looking to move to US or Dubai.
    
    {theme_directive}

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
        }},
        ...
    ]
    
    Generate exactly {count} items. Return ONLY the JSON.
    """

    print(f"{Colors.OKCYAN}Thinking... (Brainstorming {count} topics){Colors.ENDC}")
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        print(f"{Colors.FAIL}Error generating topics: {e}{Colors.ENDC}")
        return []

def main():
    print(f"{Colors.HEADER}=== D4U TOPIC CREATOR (AI BRAINSTORM) ==={Colors.ENDC}")
    
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
