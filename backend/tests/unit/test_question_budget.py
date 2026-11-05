from app.ideator.engine import LATE_ROUND, MAX_NEW_QUESTIONS, max_new_questions
from app.ideator.prompts import product_user_prompt
from app.ideator.schemas import ProductBrief
from app.ideator import fake


def test_presupuesto_de_preguntas_baja_desde_la_tercera_ronda():
    assert max_new_questions(1) == MAX_NEW_QUESTIONS
    assert max_new_questions(2) == MAX_NEW_QUESTIONS
    assert max_new_questions(3) == 2
    assert max_new_questions(LATE_ROUND) == 2


def _prompt(round_number: int) -> str:
    return product_user_prompt(
        project_name="Asado",
        idea="Dividir gastos de un asado",
        brief=ProductBrief.model_validate(fake.BRIEF_ROUND_1),
        open_questions=[],
        answered=[],
        messages=[],
        checklist=[],
        round_number=round_number,
    )


def test_el_prompt_pide_cerrar_en_rondas_tardias():
    assert "primera ronda" in _prompt(1)
    assert "máximo 2 preguntas" in _prompt(3)
    assert "cierra la definición" in _prompt(LATE_ROUND)
