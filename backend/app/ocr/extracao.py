"""Extração do texto do comprovante (foto ou PDF), antes da interpretação.

- PDF com texto selecionável: lê a camada de texto (rápido, sem OCR).
- PDF digitalizado e foto: viram imagem e passam pelo motor de OCR.

Recebe o arquivo já validado por `services.arquivos.validar` (tipo pelo
conteúdo, até 10 MB). Aqui entram os limites contra abuso de CPU e memória:
páginas, pixels e tempo total. Tudo em memória; nada é gravado nem logado (LGPD).
"""

from __future__ import annotations

import io
import math
import threading
import time
from dataclasses import dataclass

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

from app.ocr.motor import MotorOcr, TempoEsgotado
from app.services.arquivos import ArquivoValidado
from app.services.erros import RegraNegocio

MAX_PAGINAS = 3  # páginas lidas por PDF; o resto é ignorado (com aviso)
MAX_PIXELS = 40_000_000  # por imagem ou página; acima disso, recusa (ou reduz o PDF)
LADO_MAXIMO = 3500  # px: fotos maiores são reduzidas (mais rápido, mesma leitura)
LADO_MINIMO = 1000  # px: imagens pequenas são ampliadas (o Tesseract lê melhor)
DPI_PDF = 300
TEMPO_LIMITE = 15.0  # segundos para o arquivo inteiro
MIN_CARACTERES_PDF = 30  # menos que isso na camada de texto: PDF digitalizado

ORIGEM_TEXTO_PDF = "texto_pdf"
ORIGEM_OCR = "ocr"

# O pdfium não aguenta duas threads ao mesmo tempo (aviso do pypdfium2): abrir,
# ler e renderizar ficam sob esta trava; o OCR, que é o demorado, fica de fora.
_PDFIUM = threading.Lock()


@dataclass(frozen=True)
class TextoExtraido:
    texto: str
    origem: str  # ORIGEM_TEXTO_PDF ou ORIGEM_OCR
    avisos: tuple[str, ...] = ()


def extrair_texto(
    arquivo: ArquivoValidado, motor: MotorOcr, tempo_limite: float = TEMPO_LIMITE
) -> TextoExtraido:
    """Levanta `RegraNegocio` (arquivo que não abre) ou `FalhaOcr` (motor falhou ou
    passou do tempo). Nos dois casos o colaborador preenche à mão."""
    prazo = time.monotonic() + tempo_limite
    if arquivo.tipo == "application/pdf":
        return _extrair_pdf(arquivo.conteudo, motor, prazo)
    return TextoExtraido(_ocr(motor, _abrir_imagem(arquivo.conteudo), prazo), ORIGEM_OCR)


def _ocr(motor: MotorOcr, imagem: Image.Image, prazo: float) -> str:
    restante = prazo - time.monotonic()
    if restante <= 0:
        raise TempoEsgotado()
    return motor.ler(_preparar(imagem), restante)


# ---------------------------------------------------------------------------
# Imagem (JPG ou PNG)
# ---------------------------------------------------------------------------
def _abrir_imagem(conteudo: bytes) -> Image.Image:
    try:
        # `open` só lê o cabeçalho: dá para recusar o tamanho antes de descompactar.
        imagem = Image.open(io.BytesIO(conteudo))
        if imagem.width * imagem.height > MAX_PIXELS:
            raise RegraNegocio("Imagem grande demais para a leitura automática.")
        imagem.load()
        # Foto de celular "deitada": a orientação vem no EXIF.
        return ImageOps.exif_transpose(imagem)
    except Image.DecompressionBombError:
        raise RegraNegocio("Imagem grande demais para a leitura automática.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise RegraNegocio("Não foi possível abrir a imagem. Tente outra foto.") from None


def _preparar(imagem: Image.Image) -> Image.Image:
    """Tons de cinza, tamanho bom para o Tesseract e contraste esticado."""
    if imagem.mode in ("RGBA", "LA", "PA") or "transparency" in imagem.info:
        # Fundo transparente viraria preto no cinza e esconderia o texto.
        fundo = Image.new("RGBA", imagem.size, "white")
        fundo.alpha_composite(imagem.convert("RGBA"))
        imagem = fundo
    cinza = imagem.convert("L")
    lado = max(cinza.size)
    fator = 1.0
    if lado > LADO_MAXIMO:
        fator = LADO_MAXIMO / lado
    elif lado < LADO_MINIMO:
        fator = min(2.0, LADO_MINIMO / lado)
    if fator != 1.0:
        largura, altura = cinza.size
        tamanho = (max(1, round(largura * fator)), max(1, round(altura * fator)))
        cinza = cinza.resize(tamanho, Image.Resampling.LANCZOS)
    return ImageOps.autocontrast(cinza)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def _extrair_pdf(conteudo: bytes, motor: MotorOcr, prazo: float) -> TextoExtraido:
    avisos: list[str] = []
    imagens: list[Image.Image] = []
    with _PDFIUM:
        try:
            pdf = pdfium.PdfDocument(conteudo)
        except pdfium.PdfiumError:
            raise RegraNegocio(
                "Não foi possível abrir o PDF. Ele pode estar corrompido ou protegido por senha."
            ) from None
        try:
            total = len(pdf)
            if total == 0:
                raise RegraNegocio("O PDF não tem páginas.")
            if total > MAX_PAGINAS:
                avisos.append(f"Só as {MAX_PAGINAS} primeiras páginas do PDF foram lidas.")
            paginas = [pdf[i] for i in range(min(total, MAX_PAGINAS))]
            texto = "\n".join(p.get_textpage().get_text_bounded() for p in paginas)
            if sum(c.isalnum() for c in texto) >= MIN_CARACTERES_PDF:
                return TextoExtraido(texto, ORIGEM_TEXTO_PDF, tuple(avisos))
            for pagina in paginas:
                if time.monotonic() >= prazo:
                    raise TempoEsgotado()
                imagens.append(_renderizar(pagina))
        except pdfium.PdfiumError:
            raise RegraNegocio("Não foi possível ler o PDF.") from None
        finally:
            pdf.close()

    textos = [_ocr(motor, imagem, prazo) for imagem in imagens]
    return TextoExtraido("\n".join(textos), ORIGEM_OCR, tuple(avisos))


def _renderizar(pagina: pdfium.PdfPage) -> Image.Image:
    """Página → imagem em cinza a 300 dpi, reduzida se passar de MAX_PIXELS."""
    largura, altura = pagina.get_size()  # em pontos (1/72 pol.)
    escala = DPI_PDF / 72
    if largura * altura * escala**2 > MAX_PIXELS:
        # 1% de folga: o pdfium arredonda o tamanho da imagem para cima.
        escala = math.sqrt(MAX_PIXELS / (largura * altura)) * 0.99
    bitmap = pagina.render(scale=escala, grayscale=True)
    try:
        # Cópia: a imagem não pode depender da memória do pdfium depois do close.
        return bitmap.to_pil().copy()
    finally:
        bitmap.close()
