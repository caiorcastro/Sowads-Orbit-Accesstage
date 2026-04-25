
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

def generate_topics(api_key, count, explicit_theme=None, vertical=None, model_name="gemini-2.5-flash"):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    rules = load_rules()

    brand = rules.get('sowads_brand', {})
    products = brand.get('products', {})
    orbit_desc = products.get('orbit_ai', {}).get('description', '')
    ads_desc = products.get('meta_ads_automation', {}).get('description', '')
    compliance = rules.get('compliance_rules', {})
    independence_rule = compliance.get('product_independence', {}).get('rule', '')

    def call_api(qty, focus_context):
        prompt = f"""
        ROLE: Editor-chefe de um portal de marketing digital e tecnologia para negócios.
        OBJECTIVE: Criar {qty} temas únicos e de alto potencial para artigos de blog.
        TARGET AUDIENCE: Empresários e gestores brasileiros buscando crescimento digital.

        CONTEXT/FOCUS: {focus_context}

        SOBRE A SOWADS:
        - Orbit AI: {orbit_desc}
        - Automação Meta Ads: {ads_desc}

        REGRA CRÍTICA: {independence_rule}

        CRITERIA FOR "HIGH POTENTIAL":
        1. **Atrativo:** Use ganchos emocionais (Curiosidade, Urgência, Autoridade, Dados).
        2. **SEO/AIO Friendly:** Responda perguntas específicas que usuários fazem no Google/ChatGPT.
        3. **Prático:** Foque em resolver problemas reais de negócios com soluções de marketing digital.

        OUTPUT FORMAT (JSON List):
        [
            {{
                "topic_pt": "Título em Português (Brasil)",
                "potential_score": 9.5,
                "category": "SEO/AIO/Meta Ads/Estratégia Digital/Automação",
                "vertical": "Vertical de negócio alvo (ex: e-commerce, saúde, PME geral)"
            }}
        ]

        Generate exactly {qty} items. Return ONLY the JSON.
        """
        try:
            print(f"{Colors.OKCYAN}   -> Brainstorming {qty} temas para: {focus_context[:60]}...{Colors.ENDC}")
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            return json.loads(response.text)
        except Exception as e:
            print(f"{Colors.FAIL}Erro gerando temas: {e}{Colors.ENDC}")
            return []

    if explicit_theme:
        context = f"Tema: '{explicit_theme}'"
        if vertical:
            context += f" | Vertical: {vertical}"
        return call_api(count, context)
    else:
        # Default: 60% SEO/AIO + 40% Meta Ads
        count_seo = max(1, int(count * 0.6))
        count_ads = count - count_seo

        vertical_ctx = f" para a vertical: {vertical}" if vertical else " para PMEs e empresas de médio porte"

        print(f"{Colors.HEADER}Estratégia: {count_seo} temas SEO/AIO | {count_ads} temas Meta Ads{Colors.ENDC}")

        topics_seo = call_api(count_seo, f"FOCO: SEO, AIO (Artificial Intelligence Optimization), conteúdo estratégico, autoridade digital, posicionamento orgânico{vertical_ctx}. Tendências: IA generativa, GEO, E-E-A-T, conteúdo para LLMs.")
        topics_ads = call_api(count_ads, f"FOCO: Automação de campanhas Meta Ads, gestão de mídia paga, escala operacional{vertical_ctx}. Tendências: automação, conexão com bancos de dados, campanhas com poucos cliques.")

        return topics_seo + topics_ads

def main():
    print(f"{Colors.HEADER}=== ORBIT AI TOPIC CREATOR (AI BRAINSTORM) ==={Colors.ENDC}")

    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--theme", type=str, default="")
    parser.add_argument("--vertical", type=str, default="", help="Vertical de negócio (ex: e-commerce, saúde, PME)")
    parser.add_argument("--auto_save", action="store_true")
    args = parser.parse_args()

    count = args.count
    if count == 0:
        try:
            c_input = input(f"{Colors.BOLD}Quantos temas você quer gerar? (Default: 10): {Colors.ENDC}")
            count = int(c_input) if c_input.strip() else 10
        except:
            count = 10

    theme = args.theme
    if not theme and not args.auto_save:
        theme = input(f"{Colors.BOLD}Algum assunto específico? (Deixe em branco para usar estratégia automática): {Colors.ENDC}")

    topics_list = generate_topics(args.api_key, count, theme, args.vertical)

    if not topics_list:
        print("Nenhum tema gerado.")
        return

    df = pd.DataFrame(topics_list)

    print(f"\n{Colors.OKGREEN}Gerados {len(df)} temas:{Colors.ENDC}")
    print(df[['topic_pt', 'category']].head(5).to_string(index=False))
    if len(df) > 5:
        print("...")

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
