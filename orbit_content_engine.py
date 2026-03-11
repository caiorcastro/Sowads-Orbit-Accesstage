
import os
import csv
import json
import time
import re
import argparse
import warnings
from datetime import datetime
import google.generativeai as genai
import pandas as pd

# Suppress warnings
warnings.filterwarnings("ignore")

# --- Configuration ---
CSV_INPUT_PATH = "relatorios/sugestao_temas_20260122_1804.csv"
RULES_PATH = "regras_geracao/schema_orbit_ai_v1.json"
OUTPUT_DIR = "output_csv_batches_v2"
BATCH_SIZE = 20

# ANSI Colors for CLI
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_prompt(topic, rules_json):
    agent_profile = rules_json.get('agent_profile', {})
    loc_settings = rules_json.get('localization_settings', {})
    output_reqs = rules_json.get('output_requirements', {})
    compliance = rules_json.get('legal_and_compliance_mandates', {})
    
    prompt = f"""
    ROLE: {agent_profile.get('agent_name')}
    DIRECTIVE: {agent_profile.get('primary_directive')}
    PHILOSOPHY: {agent_profile.get('core_philosophy')}

    TASK: Generate a WordPress content package for the topic: "{topic}"
    Target Audience: Latin America ({', '.join(loc_settings.get('audience_country_supported', []))})
    Language: {loc_settings.get('force_language')}

    CRITICAL COMPLIANCE RULES:
    1. {compliance.get('fundamental_repositioning', {}).get('rule')}
    2. SUCCESS RATE: {compliance.get('claims_and_promises', {}).get('success_rate')} (MUST USE EXACTLY THIS PHRASE)
    3. MONEY BACK: {compliance.get('claims_and_promises', {}).get('money_back_guarantee')}
    4. NO LEGAL ADVICE: {compliance.get('claims_and_promises', {}).get('no_legal_advice')}
    5. TERMINOLOGY: Replace "Asesoría migratoria" with "Empresa de planificación internacional".

    FORMATTING RULES:
    1. {output_reqs.get('wordpress_compatibility_rule')}
    2. Block 1: Meta Title & Description (Plain text)
    3. Block 2: HTML Content starting with <article lang="es-419"> and ending with </article>.
    4. NO LINKS allowed in the text.
    5. Include a FAQ section with valid JSON-LD schema script at the end.

    TOPIC TO WRITE ABOUT: {topic}
    """
    return prompt

def parse_response(response_text):
    """Extracts Title, Content (HTML), Meta Title, Meta Desc from the raw LLM response."""
    # This is a heuristic parser based on the expected output format
    
    # Defaults
    post_content = ""
    meta_title = ""
    meta_desc = ""
    
    # Extract HTML Content
    match_html = re.search(r'(<article.*?</article>)', response_text, re.DOTALL)
    if match_html:
        post_content = match_html.group(1)
    
    # Extract Meta
    match_meta_t = re.search(r'Meta Title:\s*(.*)', response_text)
    if match_meta_t:
        meta_title = match_meta_t.group(1).strip()
        
    match_meta_d = re.search(r'Meta Description:\s*(.*)', response_text)
    if match_meta_d:
        meta_desc = match_meta_d.group(1).strip()
        
    return post_content, meta_title, meta_desc


def main():
    parser = argparse.ArgumentParser(description="Orbit AI Content Engine (CSV Batch Mode)")
    parser.add_argument("--api_key", help="Google Gemini API Key", required=True)
    parser.add_argument("--model", help="Specific Gemini Model Name", required=True)
    parser.add_argument("--start_batch", type=int, default=1, help="Start processing from this batch number")
    parser.add_argument("--max_batches", type=int, default=None, help="Maximum number of batches to process")
    args = parser.parse_args()

    print(f"{Colors.HEADER}=== ORBIT AI CONTENT ENGINE V2 (CSV BATCH MODE) ==={Colors.ENDC}")
    
    # 1. Setup
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    rules = load_json(RULES_PATH)
    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)
    print(f"{Colors.OKCYAN}[INFO] Using Model: {args.model}{Colors.ENDC}")

    # 2. Read Topics
    df_topics = pd.read_csv(CSV_INPUT_PATH)
    topics = []
    
    # Support both old and new CSV formats
    for index, row in df_topics.iterrows():
        # New format (Topic Creator)
        t_es = row.get('topic_es')
        if pd.notna(t_es) and str(t_es).strip():
             topics.append(str(t_es).strip())
             continue
             
        # Old format fallback
        t_old = row.get('Localized_ES_Draft') or row.get('Original_PT')
        if pd.notna(t_old) and str(t_old).strip():
            topics.append(str(t_old).strip())
            
    print(f"{Colors.OKCYAN}[INFO] Loaded {len(topics)} topics from {CSV_INPUT_PATH}.{Colors.ENDC}")

    # 3. Batch Processing
    total_batches = (len(topics) + BATCH_SIZE - 1) // BATCH_SIZE
    
    batches_processed = 0
    for b in range(args.start_batch - 1, total_batches):
        if args.max_batches and batches_processed >= args.max_batches:
            print(f"{Colors.OKCYAN}[INFO] Reached max batches limit ({args.max_batches}). Stopping.{Colors.ENDC}")
            break
            
        batch_num = b + 1
        start_idx = b * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(topics))
        current_batch_topics = topics[start_idx:end_idx]
        
        print(f"\n{Colors.HEADER}--- PROCESSING BATCH {batch_num}/{total_batches} (Topics {start_idx+1}-{end_idx}) ---{Colors.ENDC}")
        
        batch_data = []
        
        for i, topic in enumerate(current_batch_topics):
            global_idx = start_idx + i + 1
            print(f"{Colors.BOLD}[{global_idx}/{len(topics)}] Generating:{Colors.ENDC} {topic[:50]}...")
            
            try:
                prompt = generate_prompt(topic, rules)
                response = model.generate_content(prompt)
                
                post_content, meta_title, meta_desc = parse_response(response.text)
                
                # Build Row (Matching original structure roughly)
                row = {
                    'unique_import_id': f"Generate_Latam_{global_idx}",
                    'post_title': topic, # Use the localized title as the WP title
                    'post_content': post_content,
                    'post_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'post_author': '17', # Copied from original
                    'post_status': 'draft',
                    'language': 'es',
                    'meta_title': meta_title,
                    'meta_description': meta_desc,
                    'original_theme': topic
                }
                batch_data.append(row)
                print(f"  -> {Colors.OKGREEN}Success{Colors.ENDC}")
                time.sleep(2) # Rate limit safety
                
            except Exception as e:
                print(f"  -> {Colors.FAIL}ERROR: {e}{Colors.ENDC}")
                # Add empty error row? or just skip? 
                # Better to include it so the user knows it failed.
                batch_data.append({
                    'post_title': topic,
                    'post_content': f"ERROR GENERATING: {str(e)}",
                    'post_status': 'error'
                })

        # Save Batch CSV
        batch_filename = f"lote_{batch_num}_artigos_{start_idx+1}_a_{end_idx}.csv"
        batch_path = os.path.join(OUTPUT_DIR, batch_filename)
        
        # Create DataFrame with proper columns (superset of original)
        output_df = pd.DataFrame(batch_data)
        # Ensure columns order if possible, or just dump
        output_df.to_csv(batch_path, index=False, quoting=csv.QUOTE_ALL)
        
        print(f"{Colors.OKBLUE}>> Batch {batch_num} saved to {batch_path}{Colors.ENDC}")
        
        batches_processed += 1
        # Stop for user check? The prompt implied "so I can upload and test". 
        # But automating 5 files is fine.

    print(f"\n{Colors.HEADER}=== ALL BATCHES COMPLETED ==={Colors.ENDC}")

if __name__ == "__main__":
    main()
