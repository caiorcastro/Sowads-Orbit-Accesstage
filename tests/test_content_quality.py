from engine.content_engine import (
    clamp_meta_text,
    remove_unsupported_claims,
    sanitize_accesstage_compliance,
)
from engine.qa_validator import OrbitValidator


def article_with(extra_text=""):
    paragraphs = " ".join(["gestão financeira integrada"] * 240)
    return (
        '<article lang="pt-BR">'
        f"<p>{paragraphs} {extra_text}</p>"
        "<h2>Como organizar a operação</h2><p>Contexto executivo.</p>"
        "<h2>Como controlar os riscos</h2><p>Controles aplicáveis.</p>"
        "<h2>Como medir os resultados</h2><p>Indicadores objetivos.</p>"
        '<section class="faq-section"><h2>Perguntas frequentes</h2>'
        "<h3>Como começar?</h3><p>Mapeie processos e responsáveis.</p>"
        "</section></article>"
    )


def test_accesstage_blacklist_forces_article_below_publish_threshold():
    score, issues = OrbitValidator().grade_article_raw(
        article_with("O controle não deve depender de planilhas.")
    )
    assert score < 80
    assert any("termos proibidos" in issue and "planilhas" in issue for issue in issues)


def test_word_boundaries_do_not_block_bancaria():
    score, issues = OrbitValidator().grade_article_raw(
        article_with("A integração bancária conecta instituições.")
    )
    assert score >= 80
    assert not any("termos proibidos" in issue for issue in issues)


def test_meta_text_is_clamped_at_a_complete_word():
    value = "Integração financeira corporativa para operações de alto volume e segurança"
    result = clamp_meta_text(value, 60)
    assert len(result) <= 60
    assert result == "Integração financeira corporativa para operações de alto"


def test_compliance_sanitizer_removes_forbidden_terms():
    source = (
        "<p>Planilhas e banco de dados exigem download. "
        "Entenda o que é financiamento pessoal.</p>"
    )
    result = sanitize_accesstage_compliance(source)
    score, issues = OrbitValidator().grade_article_raw(article_with(result))
    assert "controles manuais" in result.lower()
    assert "base de dados" in result.lower()
    assert "exportação" in result.lower()
    assert not any("termos proibidos" in issue for issue in issues)


def test_unsupported_claims_are_removed_and_promises_softened():
    source = (
        '<article lang="pt-BR"><p>Segundo dados internos da Accesstage, '
        'empresas reduzem custos em até 30%. A plataforma garante que o fluxo '
        'funcione sem interrupções.</p></article>'
    )
    result = remove_unsupported_claims(source)
    assert "30%" not in result
    assert "dados internos" not in result.lower()
    assert "garante que" not in result.lower()
    assert "sem interrupções" not in result.lower()
