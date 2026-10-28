"""Motor de OCR: imagem → texto.

O resto do código só fala com o contrato `MotorOcr` (mesmo padrão do
`Armazenamento`): os testes usam um motor falso, e dá para trocar o Tesseract
por outro motor (ex.: PaddleOCR) sem mexer na extração nem na interpretação.

O Tesseract roda num SUBPROCESSO com tempo limite: se travar, o processo é
encerrado e a API segue respondendo. Tudo local, nada sai do servidor.
"""

from __future__ import annotations

from typing import Protocol

import pytesseract
from PIL import Image


class FalhaOcr(Exception):
    """O motor não conseguiu ler (binário ausente, erro interno). Nunca vai para o usuário
    como está: a tela só diz que a leitura falhou e o colaborador preenche à mão."""


class TempoEsgotado(FalhaOcr):
    """A leitura passou do tempo limite e foi interrompida."""


class MotorOcr(Protocol):
    def ler(self, imagem: Image.Image, tempo_limite: float) -> str: ...

    def disponivel(self) -> bool: ...


class MotorTesseract:
    # --oem 1: só a rede LSTM (a mais precisa). --psm 4: uma coluna de texto com
    # linhas de tamanhos variados, o formato do cupom e da NFC-e.
    def __init__(self, idioma: str = "por", config: str = "--oem 1 --psm 4") -> None:
        self.idioma = idioma
        self.config = config
        self._disponivel: bool | None = None

    def ler(self, imagem: Image.Image, tempo_limite: float) -> str:
        if tempo_limite <= 0:
            raise TempoEsgotado()
        try:
            return pytesseract.image_to_string(
                imagem, lang=self.idioma, config=self.config, timeout=tempo_limite
            )
        except RuntimeError as erro:
            # O pytesseract avisa o tempo esgotado com RuntimeError (já matou o processo).
            if "timeout" in str(erro).lower():
                raise TempoEsgotado() from None
            raise FalhaOcr("Erro no Tesseract.") from None
        except (pytesseract.TesseractError, OSError):
            # OSError inclui o TesseractNotFoundError (binário ausente).
            raise FalhaOcr("Erro no Tesseract.") from None

    def disponivel(self) -> bool:
        """Liga o recurso na tela só onde o binário existe. Consultado uma vez (o
        binário não muda com o container rodando)."""
        if self._disponivel is None:
            try:
                self._disponivel = self.idioma in pytesseract.get_languages()
            except (pytesseract.TesseractError, OSError, RuntimeError):
                self._disponivel = False
        return self._disponivel
