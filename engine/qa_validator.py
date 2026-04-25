
import pandas as pd
import argparse
import os
import re
import glob
from colorama import Fore, Style, init

init(autoreset=True)

class OrbitValidator:
    def __init__(self):
        self.rules = {
            "has_html_article": r'<article lang="pt-BR">',
            "has_h1": r'<h1>',
            "no_links": r'<a href=',
            "has_faq_section": r'<section[^>]+class=["\']faq-section["\']',
            "has_json_ld_faq": r'<script type="application/ld\+json">[\s\S]*?"@type"\s*:\s*"FAQPage"',
            "has_table": r'<table[\s>]',
            "has_lists": r'<[uo]l[\s>]',
            "min_length": 800  # chars
        }

    def _extract_text(self, html):
        """Strip HTML tags and return plain text."""
        return re.sub(r'<[^>]+>', ' ', html)

    def _count_words(self, text):
        """Count words in plain text."""
        return len(text.split())

    def _keyword_density(self, content):
        """Extract H1 text as primary keyword, calculate density."""
        h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.DOTALL)
        if not h1_match:
            return 0, ""

        h1_text = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip().lower()
        # Use top 3 significant words from H1 (3+ chars, skip stopwords)
        stopwords_pt = {'como', 'para', 'com', 'que', 'seu', 'sua', 'dos', 'das',
                        'uma', 'por', 'mais', 'não', 'são', 'pode', 'podem', 'ser',
                        'está', 'isso', 'este', 'esta', 'esse', 'essa', 'nos', 'nas',
                        'aos', 'entre', 'sobre', 'após', 'até', 'sem', 'sob', 'desde',
                        'pmes', 'empresas', 'brasileiras', 'estratégia', 'guia', '2026',
                        'alto', 'impacto', 'vencedoras', 'resultados', 'escalada'}
        keywords = [w for w in h1_text.split() if len(w) >= 3 and w not in stopwords_pt]
        # Keep only top 3 most specific keywords
        keywords = keywords[:3]

        if not keywords:
            return 0, h1_text

        plain_text = self._extract_text(content).lower()
        total_words = self._count_words(plain_text)
        if total_words == 0:
            return 0, h1_text

        # Count occurrences of each significant keyword
        keyword_count = sum(plain_text.count(kw) for kw in keywords)
        density = (keyword_count / total_words) * 100

        return round(density, 2), " ".join(keywords)

    def grade_article_raw(self, content):
        """Returns (score, issues_list) with plain text issues -- no ANSI colors.
        Used by content engine for self-healing loop."""
        score = 100
        issues = []

        # 1. Critical: article wrapper
        if not re.search(self.rules["has_html_article"], content):
            score -= 20
            issues.append("[CRITICAL] Tag <article lang='pt-BR'> ausente.")

        # 2. Hyperlinks (proibidos)
        if re.search(self.rules["no_links"], content):
            score -= 15
            issues.append("[WARN] Hyperlinks detectados (deve ser texto simples).")

        # 3. H1 — não verificado: WordPress renderiza o título do post como H1 automaticamente

        # 4. FAQ HTML section
        if not re.search(self.rules["has_faq_section"], content):
            score -= 10
            issues.append("[WARN] Seção FAQ HTML ausente (<section class='faq-section'>).")

        # 5. JSON-LD — não verificado: removido do pipeline por decisão editorial

        # 6. Content length
        if len(content) < self.rules["min_length"]:
            score -= 10
            issues.append(f"[WARN] Conteúdo muito curto ({len(content)} chars).")

        # 7. Word count
        plain_text = self._extract_text(content)
        word_count = self._count_words(plain_text)
        if word_count < 700:
            score -= 15
            issues.append(f"[WARN] Word count baixo ({word_count} palavras, mín. 700). Desenvolva mais os tópicos e expanda o FAQ.")
        elif word_count > 2000:
            score -= 25
            issues.append(f"[REPROVADO] Word count excessivo ({word_count} palavras, máx. 2000). Converta parágrafos corridos em listas <ul><li>. Nunca corte o FAQ nem a conclusão. Nenhuma frase incompleta. MÁXIMO 2.000 palavras.")
        elif word_count > 1800:
            score -= 12
            issues.append(f"[WARN] Word count alto ({word_count} palavras, alvo máx. 1800). Converta parágrafos em bullets onde possível.")
        elif word_count > 1500:
            score -= 5
            issues.append(f"[WARN] Word count acima do ideal ({word_count} palavras, alvo máx. 1500).")

        # 8. Keyword density
        density, keywords = self._keyword_density(content)
        if density > 0:
            if density < 0.5:
                score -= 10
                issues.append(f"[WARN] Densidade de keyword muito baixa ({density}%, mín. 0.5%). Keywords: '{keywords}'.")
            elif density > 4.0:
                score -= 10
                issues.append(f"[WARN] Densidade de keyword muito alta ({density}%, máx. 4.0%). Possível stuffing.")

        return max(0, score), issues

    def grade_article(self, content):
        """Grade with colorama formatting for CLI output."""
        score, raw_issues = self.grade_article_raw(content)
        colored_issues = []
        for issue in raw_issues:
            if "[CRITICAL]" in issue:
                colored_issues.append(f"{Fore.RED}{issue}")
            else:
                colored_issues.append(f"{Fore.YELLOW}{issue}")
        return score, colored_issues

    def run(self, input_path):
        print(f"{Fore.CYAN}{Style.BRIGHT}=== ORBIT AI QUALITY VALIDATOR v2.0 ==={Style.RESET_ALL}")

        files = glob.glob(input_path)
        if not files:
            print(f"Nenhum arquivo encontrado em {input_path}")
            return

        total_score = 0
        total_articles = 0

        for file in files:
            print(f"\n{Fore.BLUE}Inspecionando Batch: {os.path.basename(file)}{Style.RESET_ALL}")
            try:
                df = pd.read_csv(file)
            except Exception as e:
                print(f"Erro lendo CSV: {e}")
                continue

            for idx, row in df.iterrows():
                title = row.get('post_title', 'Unknown')
                content = str(row.get('post_content', ''))

                score, issues = self.grade_article(content)
                total_score += score
                total_articles += 1

                if score == 100:
                    grade_color = Fore.GREEN
                    verdict = "PERFEITO"
                elif score >= 80:
                    grade_color = Fore.CYAN
                    verdict = "BOM"
                else:
                    grade_color = Fore.RED
                    verdict = "FALHOU"

                print(f"  Artigo {idx+1}: {title[:45]}... -> {grade_color}[{score}/100] {verdict}{Style.RESET_ALL}")
                for issue in issues:
                    print(f"    {issue}")

        if total_articles > 0:
            avg = total_score / total_articles
            print(f"\n{Style.BRIGHT}=== VEREDICTO FINAL ==={Style.RESET_ALL}")
            print(f"Artigos auditados: {total_articles}")
            print(f"Score global de qualidade: {avg:.1f}/100")
            if avg >= 80:
                print(f"{Fore.GREEN}STATUS: PRONTO PARA PRODUCAO{Style.RESET_ALL}")
            else:
                print(f"{Fore.RED}STATUS: PRECISA OTIMIZACAO{Style.RESET_ALL}")

def main():
    parser = argparse.ArgumentParser(description="Orbit AI Content Quality Validator v2.0")
    parser.add_argument("--path", default="output_csv_batches*/*.csv", help="Path glob to CSV input files")
    args = parser.parse_args()

    validator = OrbitValidator()
    validator.run(args.path)

if __name__ == "__main__":
    main()
