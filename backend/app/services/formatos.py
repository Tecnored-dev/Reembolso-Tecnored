"""Formatação e leitura de valores em reais."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.services.erros import RegraNegocio

VALOR_MAXIMO = Decimal("99999.99")


def moeda(valor: Decimal, codigo: str = "BRL") -> str:
    prefixo = "R$" if codigo == "BRL" else codigo
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{prefixo} {texto}"


def ler_valor(texto: str) -> Decimal:
    """Aceita "45,90", "45.90" e "1.234,56". Positivo, até 2 casas."""
    bruto = (texto or "").strip().replace("R$", "").replace(" ", "")
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(bruto)
    except InvalidOperation:
        raise RegraNegocio("Valor inválido.") from None
    if not valor.is_finite() or valor <= 0:
        raise RegraNegocio("O valor precisa ser maior que zero.")
    if valor.as_tuple().exponent < -2:  # type: ignore[operator]
        raise RegraNegocio("Use no máximo 2 casas decimais.")
    if valor > VALOR_MAXIMO:
        raise RegraNegocio("Valor acima do máximo aceito.")
    return valor.quantize(Decimal("0.01"))
