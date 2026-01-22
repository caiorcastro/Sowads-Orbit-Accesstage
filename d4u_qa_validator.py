
import pandas as pd
import argparse
import os
import re
import glob
from colorama import Fore, Style, init

init(autoreset=True)

class D4UValidator:
    def __init__(self):
        self.rules = {
            "no_json_ld": r'<script type="application/ld\+json">',
            "has_html_article": r'<article lang="es-419">',
            "has_h1": r'<h1>',
            "no_links": r'<a href=',
            "has_faq_section": r'<section class="faq-section">',
            "min_length": 800  # chars
        }
    
    def grade_article(self, content):
        score = 100
        issues = []
        
        # 1. Critical Technical Checks
        if re.search(self.rules["no_json_ld"], content):
            score -= 30
            issues.append(f"{Fore.RED}[CRITICAL] JSON-LD Script detected (Prohibited).")
            
        if not re.search(self.rules["has_html_article"], content):
            score -= 20
            issues.append(f"{Fore.RED}[CRITICAL] Missing <article lang='es-419'> tag.")
            
        if re.search(self.rules["no_links"], content):
            score -= 15
            issues.append(f"{Fore.YELLOW}[WARN] Hyperlinks detected (Should be plain text).")

        # 2. Structural Checks
        if not re.search(self.rules["has_h1"], content):
            score -= 10
            issues.append(f"{Fore.YELLOW}[WARN] Missing <h1> tag.")
            
        if not re.search(self.rules["has_faq_section"], content):
            score -= 10
            issues.append(f"{Fore.YELLOW}[WARN] Missing FAQ section (<section class='faq-section'>).")

        # 3. Content Length Check
        if len(content) < self.rules["min_length"]:
            score -= 10
            issues.append(f"{Fore.YELLOW}[WARN] Content too short ({len(content)} chars).")

        # 4. Success Rate Compliance
        # Check if the exact phrase is present if retention/success is mentioned
        # This is harder to regex perfectly without NLP, but we can check the mandate
        if "91%" not in content and "91 %" not in content:
             # Soft warning
             pass 

        return max(0, score), issues

    def run(self, input_path):
        print(f"{Fore.CYAN}{Style.BRIGHT}=== D4U QUALITY VALIDATOR v1.0 ==={Style.RESET_ALL}")
        
        files = glob.glob(input_path)
        if not files:
            print(f"No files found at {input_path}")
            return

        total_score = 0
        total_articles = 0
        
        for file in files:
            print(f"\n{Fore.BLUE}Inspecting Batch: {os.path.basename(file)}{Style.RESET_ALL}")
            try:
                df = pd.read_csv(file)
            except Exception as e:
                print(f"Error reading CSV: {e}")
                continue
                
            for idx, row in df.iterrows():
                title = row.get('post_title', 'Unknown')
                content = str(row.get('post_content', ''))
                
                score, issues = self.grade_article(content)
                total_score += score
                total_articles += 1
                
                # Visual Verdict
                if score == 100:
                    grade_color = Fore.GREEN
                    verdict = "PERFECT"
                elif score >= 80:
                    grade_color = Fore.CYAN
                    verdict = "GOOD"
                else:
                    grade_color = Fore.RED
                    verdict = "FAIL"
                
                print(f"  Article {idx+1}: {title[:40]}... -> {grade_color}[{score}/100] {verdict}{Style.RESET_ALL}")
                for issue in issues:
                    print(f"    {issue}")
        
        if total_articles > 0:
            avg = total_score / total_articles
            print(f"\n{Style.BRIGHT}=== FINAL VERDICT ==={Style.RESET_ALL}")
            print(f"Articles Audited: {total_articles}")
            print(f"Global Quality Score: {avg:.1f}/100")
            if avg > 90:
                print(f"{Fore.GREEN}STATUS: READY FOR PRODUCTION 🚀{Style.RESET_ALL}")
            else:
                 print(f"{Fore.RED}STATUS: NEEDS OPTIMIZATION ⚠️{Style.RESET_ALL}")

def main():
    parser = argparse.ArgumentParser(description="D4U Content Quality Validator")
    parser.add_argument("--path", default="output_csv_batches*/*.csv", help="Path glob to CSV input files")
    args = parser.parse_args()
    
    validator = D4UValidator()
    validator.run(args.path)

if __name__ == "__main__":
    main()
