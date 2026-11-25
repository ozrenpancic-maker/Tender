"""Zajedničko sučelje za sve strategije.

Svaka strategija je funkcija koja za danu povijest svijeća (do i uključujući trenutni indeks)
vraća odluku: "buy", "sell" ili "hold". Strategije su bez stanja osim onoga što im eksplicitno
proslijedi backtest/paper engine (trenutna pozicija), da bi se identičan kod mogao koristiti i za
backtest i za paper/live trgovanje.
"""
from dataclasses import dataclass, field
from typing import Callable, Literal

from app.candles import Candle

Decision = Literal["buy", "sell", "hold"]


@dataclass
class StrategyContext:
    candles: list[Candle]  # povijest do trenutnog trenutka (uključivo), kronološki
    index: int  # indeks trenutne (zadnje zatvorene) svijeće u candles
    in_position: bool  # ima li se trenutno otvorena pozicija (kupljeno)
    params: dict
    aux: dict[str, list[Candle]] = field(default_factory=dict)  # npr. {"SPX": [...]} - vidi app.aux_candles
    series: dict[str, list[tuple[int, float]]] = field(default_factory=dict)  # npr. {"FEDFUNDS": [...]} - ne-OHLC serije


Strategy = Callable[[StrategyContext], Decision]
