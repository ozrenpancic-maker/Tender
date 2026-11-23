"""AI Prediction Engine (KriptoMVP 4.4, faza 3) - LightGBM + logistička regresija, kalibrirane
vjerojatnosti P(up)/P(down)/P(sideways) po horizontu (1h/4h/24h/7d).

Ovo je ODVOJENO od `app/signals.py` (jednostavni rule-based sma_crossover signal iz ranije faze) -
oba ostaju u kodu, dashboard ih prikazuje kao dvije različite stvari. Vidi README "AI Prediction
Engine" za metodologiju i POŠTENE rezultate (uključujući horizonte gdje model ne pokazuje stvarnu
prednost - ti horizonti vraćaju WAIT/NEMA DOVOLJNO PODATAKA, ne izmišljenu sigurnost).
"""
