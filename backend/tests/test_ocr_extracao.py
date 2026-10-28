"""OCR, etapa 2: extração do texto (foto ou PDF) e motor de OCR.

Os testes usam um motor falso; os marcados com `tesseract` usam o de verdade e
só rodam onde o binário existe (na imagem Docker). Imagens e PDFs são gerados
aqui mesmo, com textos fictícios (nenhuma nota real: LGPD).
"""

from __future__ import annotations

import io
import shutil
from datetime import date

import pytesseract
import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.ocr import extracao
from app.ocr.extracao import ORIGEM_OCR, ORIGEM_TEXTO_PDF, extrair_texto
from app.ocr.interpretacao import IDENTIFICADO, LIDO, Campo, interpretar
from app.ocr.motor import FalhaOcr, MotorTesseract, TempoEsgotado
from app.services.arquivos import validar
from app.services.erros import RegraNegocio

LINHAS = [
    "RESTAURANTE SABOR DO VALE LTDA",
    "CNPJ: 11.222.333/0001-81",
    "Emissao 18/10/2026 12:41",
    "VALOR A PAGAR R$ 48,90",
]

tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="sem o Tesseract")


class MotorFalso:
    def __init__(self, texto: str = "TOTAL 10,00", erro: Exception | None = None) -> None:
        self.texto = texto
        self.erro = erro
        self.chamadas: list[tuple[tuple[int, int], str, float]] = []
        self.imagens: list[Image.Image] = []

    def ler(self, imagem: Image.Image, tempo_limite: float) -> str:
        self.chamadas.append((imagem.size, imagem.mode, tempo_limite))
        self.imagens.append(imagem)
        if self.erro:
            raise self.erro
        return self.texto

    def disponivel(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Geradores de arquivos de teste
# ---------------------------------------------------------------------------
def imagem_nota(tamanho=(1200, 360), fonte=40) -> Image.Image:
    imagem = Image.new("RGB", tamanho, "white")
    desenho = ImageDraw.Draw(imagem)
    letra = ImageFont.load_default(size=fonte)
    for i, linha in enumerate(LINHAS):
        desenho.text((40, 30 + i * (fonte + 40)), linha, fill="black", font=letra)
    return imagem


def salvar(imagem: Image.Image, formato: str, **opcoes) -> bytes:
    saida = io.BytesIO()
    imagem.save(saida, formato, **opcoes)
    return saida.getvalue()


def arquivo(conteudo: bytes, nome: str):
    return validar(conteudo, nome)


def pdf_com_texto(linhas: list[str]) -> bytes:
    """PDF mínimo com camada de texto (Helvetica), montado à mão."""
    textos = " ".join(f"({linha}) '" for linha in linhas)
    stream = f"BT /F1 12 Tf 50 780 Td 16 TL {textos} ET".encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for n, objeto in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % n + objeto + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    saida += b"".join(b"%010d 00000 n \n" % p for p in posicoes)
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1,
        xref,
    )
    return bytes(saida)


def pdf_digitalizado(paginas: int = 1, tamanho=(600, 800)) -> bytes:
    imagens = [imagem_nota(tamanho, fonte=24) for _ in range(paginas)]
    return salvar(imagens[0], "PDF", save_all=True, append_images=imagens[1:])


# ---------------------------------------------------------------------------
# Imagens
# ---------------------------------------------------------------------------
def test_jpg_valido():
    motor = MotorFalso()
    resultado = extrair_texto(arquivo(salvar(imagem_nota(), "JPEG"), "nota.jpg"), motor)
    assert resultado.texto == "TOTAL 10,00" and resultado.origem == ORIGEM_OCR
    [(tamanho, modo, tempo)] = motor.chamadas
    assert tamanho == (1200, 360) and modo == "L"
    assert 0 < tempo <= extracao.TEMPO_LIMITE


def test_png_valido_com_fundo_transparente_vira_branco():
    imagem = Image.new("RGBA", (1200, 360), (0, 0, 0, 0))
    ImageDraw.Draw(imagem).text((40, 40), "TOTAL 10,00", fill="black")
    motor = MotorFalso()
    extrair_texto(arquivo(salvar(imagem, "PNG"), "nota.png"), motor)
    assert motor.imagens[0].getpixel((0, 0)) == 255  # branco, não preto


def test_foto_deitada_e_girada_pelo_exif():
    imagem = imagem_nota((400, 200))
    exif = Image.Exif()
    exif[0x0112] = 6  # orientação: girar 90°
    motor = MotorFalso()
    extrair_texto(arquivo(salvar(imagem, "JPEG", exif=exif), "nota.jpg"), motor)
    # Girada (200x400) e ampliada 2x por ser pequena.
    assert motor.chamadas[0][0] == (400, 800)


def test_foto_grande_e_reduzida():
    motor = MotorFalso()
    extrair_texto(arquivo(salvar(imagem_nota((5000, 1000)), "PNG"), "nota.png"), motor)
    assert motor.chamadas[0][0] == (3500, 700)


def test_imagem_com_pixels_demais_e_recusada(monkeypatch):
    monkeypatch.setattr(extracao, "MAX_PIXELS", 1000)
    motor = MotorFalso()
    with pytest.raises(RegraNegocio, match="grande demais"):
        extrair_texto(arquivo(salvar(imagem_nota((100, 100)), "PNG"), "nota.png"), motor)
    assert motor.chamadas == []


def test_imagem_corrompida():
    with pytest.raises(RegraNegocio, match="Não foi possível abrir a imagem"):
        extrair_texto(arquivo(b"\xff\xd8\xff" + b"lixo" * 100, "nota.jpg"), MotorFalso())
    truncada = salvar(imagem_nota(), "PNG")[:300]
    with pytest.raises(RegraNegocio, match="Não foi possível abrir a imagem"):
        extrair_texto(arquivo(truncada, "nota.png"), MotorFalso())


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def test_pdf_com_texto_nao_passa_pelo_ocr():
    motor = MotorFalso()
    resultado = extrair_texto(arquivo(pdf_com_texto(LINHAS), "nota.pdf"), motor)
    assert resultado.origem == ORIGEM_TEXTO_PDF
    assert "VALOR A PAGAR R$ 48,90" in resultado.texto
    assert motor.chamadas == []


def test_pdf_com_texto_ate_a_interpretacao():
    resultado = extrair_texto(arquivo(pdf_com_texto(LINHAS), "nota.pdf"), MotorFalso())
    leitura = interpretar(resultado.texto, hoje=date(2026, 10, 20))
    assert leitura.status == LIDO
    assert leitura.valor_total.valor == "48.90"
    assert leitura.cnpj.valor == "11222333000181"


def test_pdf_digitalizado_passa_pelo_ocr():
    motor = MotorFalso()
    resultado = extrair_texto(arquivo(pdf_digitalizado(), "nota.pdf"), motor)
    assert resultado.origem == ORIGEM_OCR and resultado.texto == "TOTAL 10,00"
    [(tamanho, modo, _)] = motor.chamadas
    assert modo == "L"
    assert tamanho in {(2500, 3333), (2500, 3334)}  # 600x800 pt a 300 dpi


def test_pdf_com_paginas_demais_le_so_as_primeiras():
    motor = MotorFalso()
    resultado = extrair_texto(arquivo(pdf_digitalizado(paginas=5), "nota.pdf"), motor)
    assert len(motor.chamadas) == extracao.MAX_PAGINAS
    assert resultado.avisos == ("Só as 3 primeiras páginas do PDF foram lidas.",)


def test_pagina_enorme_e_renderizada_dentro_do_limite(monkeypatch):
    monkeypatch.setattr(extracao, "MAX_PIXELS", 1_000_000)
    motor = MotorFalso()
    extrair_texto(arquivo(pdf_digitalizado(), "nota.pdf"), motor)
    largura, altura = motor.chamadas[0][0]
    assert largura * altura <= 1_000_000


def test_pdf_corrompido():
    with pytest.raises(RegraNegocio, match="Não foi possível abrir o PDF"):
        extrair_texto(arquivo(b"%PDF-1.4\nlixo" * 50, "nota.pdf"), MotorFalso())


# ---------------------------------------------------------------------------
# Tempo e falhas do motor
# ---------------------------------------------------------------------------
def test_tempo_esgotado_nao_chama_o_motor():
    motor = MotorFalso()
    with pytest.raises(TempoEsgotado):
        extrair_texto(arquivo(salvar(imagem_nota(), "PNG"), "nota.png"), motor, tempo_limite=0)
    with pytest.raises(TempoEsgotado):
        extrair_texto(arquivo(pdf_digitalizado(2), "nota.pdf"), motor, tempo_limite=0)
    assert motor.chamadas == []


def test_tempo_restante_diminui_entre_paginas():
    motor = MotorFalso()
    extrair_texto(arquivo(pdf_digitalizado(2), "nota.pdf"), motor, tempo_limite=5)
    primeira, segunda = (tempo for _, _, tempo in motor.chamadas)
    assert 5 >= primeira >= segunda > 0


def test_falha_do_motor_chega_a_quem_chamou():
    motor = MotorFalso(erro=FalhaOcr("Erro no Tesseract."))
    with pytest.raises(FalhaOcr):
        extrair_texto(arquivo(salvar(imagem_nota(), "PNG"), "nota.png"), motor)


@pytest.mark.parametrize(
    ("erro", "esperado"),
    [
        (RuntimeError("Tesseract process timeout"), TempoEsgotado),
        (pytesseract.TesseractNotFoundError(), FalhaOcr),
        (pytesseract.TesseractError(1, "Failed loading language 'por'"), FalhaOcr),
        (RuntimeError("outro erro"), FalhaOcr),
    ],
)
def test_motor_tesseract_traduz_os_erros(monkeypatch, erro, esperado):
    def falhar(*args, **kwargs):
        raise erro

    monkeypatch.setattr(pytesseract, "image_to_string", falhar)
    with pytest.raises(esperado):
        MotorTesseract().ler(Image.new("L", (10, 10)), tempo_limite=5)


def test_motor_tesseract_sem_tempo_nem_chama_o_binario(monkeypatch):
    monkeypatch.setattr(pytesseract, "image_to_string", pytest.fail)
    with pytest.raises(TempoEsgotado):
        MotorTesseract().ler(Image.new("L", (10, 10)), tempo_limite=0)


def test_motor_tesseract_indisponivel(monkeypatch):
    def sem_binario():
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "get_languages", sem_binario)
    assert MotorTesseract().disponivel() is False
    monkeypatch.setattr(pytesseract, "get_languages", lambda: ["eng"])
    assert MotorTesseract().disponivel() is False  # sem o português
    monkeypatch.setattr(pytesseract, "get_languages", lambda: ["eng", "por"])
    motor = MotorTesseract()
    assert motor.disponivel() is True
    # Consultado uma vez só: não chama o binário a cada /api/config.
    monkeypatch.setattr(pytesseract, "get_languages", sem_binario)
    assert motor.disponivel() is True


# ---------------------------------------------------------------------------
# Tesseract de verdade (só na imagem Docker)
# ---------------------------------------------------------------------------
def ler_de_verdade(conteudo: bytes, nome: str):
    resultado = extrair_texto(arquivo(conteudo, nome), MotorTesseract())
    return resultado, interpretar(resultado.texto, hoje=date(2026, 10, 20))


@tesseract
def test_tesseract_le_foto_nitida():
    assert MotorTesseract().disponivel()
    resultado, leitura = ler_de_verdade(salvar(imagem_nota(), "JPEG"), "nota.jpg")
    assert resultado.origem == ORIGEM_OCR
    assert leitura.status == LIDO
    assert leitura.valor_total.valor == "48.90"
    assert leitura.data.valor == "2026-10-18"
    assert leitura.cnpj.valor == "11222333000181"


@tesseract
def test_tesseract_le_pdf_digitalizado():
    _, leitura = ler_de_verdade(pdf_digitalizado(), "nota.pdf")
    assert leitura.valor_total == Campo("48.90", IDENTIFICADO)


@tesseract
def test_tesseract_com_foto_ruim_nao_quebra():
    # Desfocada, apagada e pequena: o que importa é não travar nem dar erro;
    # o que não for lido, o colaborador preenche à mão.
    ruim = imagem_nota((600, 180), fonte=20).filter(ImageFilter.GaussianBlur(1.5))
    ruim = Image.eval(ruim, lambda p: 150 + p * 80 // 255)
    resultado, leitura = ler_de_verdade(salvar(ruim, "JPEG", quality=30), "nota.jpg")
    assert isinstance(resultado.texto, str)
    assert leitura.status in {"lido", "parcial", "ilegivel"}
