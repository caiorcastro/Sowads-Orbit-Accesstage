
import os
import csv
import json
import time
import argparse
import glob
import pandas as pd
import google.generativeai as genai
from datetime import datetime

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

# Goals:
# 1. Remove JSON-LD, convert to HTML FAQ.
# 2. Score 1-10 on SEO/AIO.
# 3. Optimize if score < 9.5.

def optimize_content_with_gemini(model, content, title):
    prompt = f"""
    ROLE: Senior SEO & AIO (Artificial Intelligence Optimization) Specialist.
    TASK: Audit and Optimize the following WordPress Article HTML.

    INPUT TITLE: {title}
    INPUT HTML:
    {content}

    STRICT INSTRUCTIONS:
    1. **FAQ FIX:** Identify the FAQ section. If it uses `<script type="application/ld+json">`, DELETE the script and convert the Q&A into standard HTML format (Use `<h3>Question</h3>` and `<p>Answer</p>`).
    2. **AIO SCORING:** Grade the content (1-10) on "Generative Engine Optimization". Criteria: Entity density, clear structure, direct answers, NLP-friendly phrasing.
    3. **OPTIMIZATION:** 
       - If the Score is below 9.5, REWRITE sections to improve it.
       - Ensure the "99% Success Rate" rule is followed (it must be ">91%").
       - **CRITICAL:** DO NOT INCLUDE ANY "<script>" TAGS. NO JSON-LD. NO JS. PURE HTML ONLY.
       - Ensure NO LINKS are present.
       - Ensure Language is strict ES-419 (Latam).
    
    OUTPUT FORMAT (JSON ONLY):
    {{
        "aio_score": 8.5,
        "critique": "Brief explanation of gaps.",
        "optimized_html": "Full HTML content here..."
    }}
    """
    
    try:
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        print(f"{Colors.FAIL}Error optimizing: {e}{Colors.ENDC}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Orbit AI Content Optimizer")
    parser.add_argument("--api_key", required=True)
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()

    genai.configure(api_key=args.api_key)
    model = genai.GenerativeModel(args.model)

    csv_files = glob.glob("output_csv_batches/*.csv")
    report_data = []

    print(f"{Colors.HEADER}=== STARTING MASSIVE AUDIT & OPTIMIZATION ==={Colors.ENDC}")

    for file_path in csv_files:
        print(f"\nProcessing File: {file_path}")
        df = pd.read_csv(file_path)
        
        # Check if 'post_content' exists
        if 'post_content' not in df.columns:
            print("Skipping (no post_content column)")
            continue

        updated_contents = []
        
        for index, row in df.iterrows():
            title = row.get('post_title', 'Unknown Title')
            content = row.get('post_content', '')
            
            # Skip if empty or error
            if not isinstance(content, str) or len(content) < 100:
                updated_contents.append(content)
                continue

            print(f" -> Auditing: {title[:40]}...")
            
            result = optimize_content_with_gemini(model, content, title)
            
            if result:
                score = result.get('aio_score')
                critique = result.get('critique')
                new_html = result.get('optimized_html')
                
                print(f"    {Colors.OKGREEN}Score: {score}/10{Colors.ENDC} | Fix: {critique[:60]}...")
                
                updated_contents.append(new_html)
                report_data.append({
                    "Batch_File": os.path.basename(file_path),
                    "Title": title,
                    "Original_Score": score,
                    "Status": "Optimized",
                    "Critique": critique
                })
            else:
                updated_contents.append(content) # Keep original if fail
                report_data.append({"Batch_File": os.path.basename(file_path), "Title": title, "Status": "Failed API"})
            
            time.sleep(1.5) # Rate limit

        # Update DataFrame
        df['post_content'] = updated_contents
        df.to_csv(file_path, index=False, quoting=csv.QUOTE_ALL)
        print(f"{Colors.OKGREEN}>> Saved Optimized File: {file_path}{Colors.ENDC}")

    # Generate Report
    report_df = pd.DataFrame(report_data)
    report_path = "relatorios/relatorio_otimizacao_seo_aio.md"
    with open(report_path, 'w') as f:
        f.write("# Relatório de Auditoria e Otimização SEO/AIO\n\n")
        f.write(report_df.to_markdown(index=False))
    
    print(f"\nFull Report saved to {report_path}")

if __name__ == "__main__":
    main()
