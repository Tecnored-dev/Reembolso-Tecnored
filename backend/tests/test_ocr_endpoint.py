"""OCR, etapa 3: POST /api/comprovantes/analisar.

Motor de OCR falso (o Tesseract de verdade está em test_ocr_extracao.py).
Arquivos gerados no teste, com dados fictícios.
"""

from __future__ import annotations

import logging
import threading

import pytest
from sqlalchemy import func, select

from app.api.routes import comprovantes
from app.api.routes.comprovantes import MENSAGEM_INDISPONIVEL, MENSAGEM_TEMPO, get_motor
from app.main import app
from app.models import Solicitacao
from app.ocr.motor import FalhaOcr, TempoEsgotado
from tests.test_alimentacao import COLAB, entrar, enviar
from tests.test_alimentacao import cenario as cenario  # fixture reaproveitada
from tests.test_ocr_extracao import (
    LINHAS,
    MotorFalso,
    imagem_nota,
    pdf_com_texto,
    pdf_digitalizado,
    salvar,
)

ROTA = "/api/comprovantes/analisar"
TEXTO_NOTA = "\n".join(LINHAS)


@pytest.fixture
def motor():
    falso = MotorFalso(texto=TEXTO_NOTA)
    app.dependency_overrides[get_motor] = lambda: falso
    return falso


@pytest.fixture
def leitor(cliente, motor):
    entrar(cliente, COLAB)
    return cliente


def analisar(cliente, conteudo: bytes, nome="nota.jpg", tipo="image/jpeg"):
    return cliente.post(ROTA, files={"arquivo": (nome, conteudo, tipo)})


def test_sem_login(cliente, motor):
    r = analisar(cliente, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 401
    assert motor.chamadas == []


def test_jpg_valido(leitor, motor, db):
    r = analisar(leitor, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "lido" and corpo["origem"] == "ocr"
    campos = corpo["campos"]
    assert campos["valor_total"] == {"valor": "48.90", "estado": "identificado", "alternativas": []}
    assert campos["data"]["valor"] == "2026-10-18"
    assert campos["cnpj"]["valor"] == "11222333000181"
    assert campos["estabelecimento"]["valor"] == "RESTAURANTE SABOR DO VALE LTDA"
    assert campos["categoria_sugerida"]["valor"] == "refeicao"
    assert set(campos) == {
        "data",
        "valor_total",
        "estabelecimento",
        "cnpj",
        "numero_documento",
        "categoria_sugerida",
    }
    assert len(motor.chamadas) == 1
    # Só lê: nada de solicitação nem de arquivo gravado.
    assert db.scalar(select(func.count()).select_from(Solicitacao)) == 0
    assert not leitor.storage.raiz.exists() or not any(leitor.storage.raiz.rglob("*"))


def test_png_valido(leitor):
    r = analisar(leitor, salvar(imagem_nota(), "PNG"), "nota.png", "image/png")
    assert r.status_code == 200 and r.json()["status"] == "lido"


def test_pdf_com_texto_nao_usa_o_ocr(leitor, motor):
    r = analisar(leitor, pdf_com_texto(LINHAS), "nota.pdf", "application/pdf")
    assert r.status_code == 200
    assert r.json()["origem"] == "texto_pdf" and r.json()["status"] == "lido"
    assert motor.chamadas == []


def test_pdf_digitalizado(leitor, motor):
    r = analisar(leitor, pdf_digitalizado(paginas=4), "nota.pdf", "application/pdf")
    assert r.status_code == 200
    assert r.json()["origem"] == "ocr"
    assert "Só as 3 primeiras páginas do PDF foram lidas." in r.json()["avisos"]
    assert len(motor.chamadas) == 3


def test_arquivo_invalido(leitor, motor):
    # Extensão de imagem, conteúdo de texto: vale o conteúdo.
    r = analisar(leitor, b"isto nao e uma imagem", "nota.jpg")
    assert r.status_code == 400
    assert r.json()["detail"] == "Formato não aceito. Envie JPG, PNG ou PDF."
    assert motor.chamadas == []


def test_arquivo_vazio(leitor):
    r = analisar(leitor, b"", "nota.jpg")
    assert r.status_code == 400
    assert r.json()["detail"] == "Anexe a foto ou o PDF da nota."


def test_arquivo_acima_do_limite(leitor, motor):
    r = analisar(leitor, b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024))
    assert r.status_code == 400
    assert r.json()["detail"] == "Arquivo maior que 10 MB."
    assert motor.chamadas == []


def test_arquivo_corrompido(leitor):
    r = analisar(leitor, b"\xff\xd8\xff" + b"lixo" * 100)
    assert r.status_code == 400
    assert "Não foi possível abrir a imagem" in r.json()["detail"]


def test_comprovante_ilegivel(leitor, motor):
    motor.texto = "~~ ;; .."
    r = analisar(leitor, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "ilegivel"
    assert all(c["estado"] == "nao_identificado" for c in corpo["campos"].values())
    assert corpo["avisos"] == ["Não conseguimos ler o comprovante. Preencha os dados à mão."]


def test_falha_do_motor(leitor, motor):
    motor.erro = FalhaOcr("Erro no Tesseract.")
    r = analisar(leitor, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 503
    assert r.json() == {"detail": MENSAGEM_INDISPONIVEL}


def test_tempo_esgotado(leitor, motor):
    motor.erro = TempoEsgotado()
    r = analisar(leitor, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 200
    assert r.json()["status"] == "ilegivel" and r.json()["avisos"] == [MENSAGEM_TEMPO]


def test_ocupado_responde_503_sem_esperar_muito(leitor, motor, monkeypatch):
    vagas = threading.BoundedSemaphore(1)
    monkeypatch.setattr(comprovantes, "_VAGAS", vagas)
    monkeypatch.setattr(comprovantes, "OCR_ESPERA_VAGA_SEGUNDOS", 0.05)
    vagas.acquire()  # outra leitura em andamento
    r = analisar(leitor, salvar(imagem_nota(), "JPEG"))
    assert r.status_code == 503 and r.json() == {"detail": MENSAGEM_INDISPONIVEL}
    assert motor.chamadas == []
    vagas.release()
    assert analisar(leitor, salvar(imagem_nota(), "JPEG")).status_code == 200


def test_vaga_volta_depois_de_falha(leitor, motor, monkeypatch):
    monkeypatch.setattr(comprovantes, "_VAGAS", threading.BoundedSemaphore(1))
    monkeypatch.setattr(comprovantes, "OCR_ESPERA_VAGA_SEGUNDOS", 0.05)
    motor.erro = FalhaOcr("Erro no Tesseract.")
    assert analisar(leitor, salvar(imagem_nota(), "JPEG")).status_code == 503
    assert analisar(leitor, b"\xff\xd8\xff" + b"lixo" * 100).status_code == 400
    motor.erro = None
    assert analisar(leitor, salvar(imagem_nota(), "JPEG")).status_code == 200


def test_log_nao_tem_dados_da_nota(leitor, caplog):
    with caplog.at_level(logging.INFO, logger="app.api.routes.comprovantes"):
        assert analisar(leitor, salvar(imagem_nota(), "JPEG")).status_code == 200
    registro = caplog.text
    assert "Leitura de comprovante: image/jpeg, ocr, lido" in registro
    for dado in ("48", "11222333000181", "11.222.333", "RESTAURANTE", "2026-10-18", "nota.jpg"):
        assert dado not in registro


def test_contrato_no_openapi():
    esquema = app.openapi()
    operacao = esquema["paths"][ROTA]["post"]
    assert {"200", "400", "401", "503"} <= set(operacao["responses"])
    campos = esquema["components"]["schemas"]["CampoLido"]["properties"]
    assert campos["estado"]["enum"] == ["identificado", "ambiguo", "nao_identificado"]


def test_config_avisa_se_a_leitura_esta_disponivel(cliente, motor):
    assert cliente.get("/api/config").json()["leitura_comprovante"] is True


def test_fluxo_atual_continua_igual(cenario, motor):
    """Ler o comprovante não muda nada no envio: o mesmo arquivo segue pela rota de sempre."""
    entrar(cenario, COLAB)
    foto = salvar(imagem_nota(), "JPEG")
    assert analisar(cenario, foto).status_code == 200
    r = enviar(cenario, valor="48,90", arquivo=("nota.jpg", foto, "image/jpeg"))
    assert r.status_code == 201, r.text
    assert r.json()["valor_total"] == "48.90"
