"""Zajedničko sučelje za sve strategije.

Svaka strategija je funkcija koja za danu povijest svijeća (do i uključujući trenutni indeks)
vraća odluku: "buy", "sell" ili "hold". Strategije su bez stanja osim onoga što im eksplicitno
proslijedi backtest/paper engine (trenutna pozicija), da bi se identičan kod mogao koristiti i za
backtest i za paper/live trgovanje.
"""
from dataclasses import dataclass
from typing import Callable, Literal

from app.candles import Candle

Decision = Literal["buy", "sell", "hold"]


@dataclass
class StrategyContext:
    candles: list[Candle]  # povijest do trenutnog trenutka (uključivo), kronološki
    index: int  # indeks trenutne (zadnje zatvorene) svijeće u candles
    in_position: bool  # ima li se trenutno otvorena pozicija (kupljeno)
    params: dict


Strategy = Callable[[StrategyContext], Decision]


STRATEGY_REGISTRY: dict[str, dict] = {}


def register(key: str, label: str, default_params: dict, fn: Strategy) -> None:
    STRATEGY_REGISTRY[key] = {"label": label, "default_params": default_params, "fn": fn}
