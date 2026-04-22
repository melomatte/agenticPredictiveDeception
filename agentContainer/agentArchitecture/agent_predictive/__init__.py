# Importiamo la classe principale del nostro agente da config.py
from .predictive_core import PredictiveAgent

# (Opzionale) Definiamo cosa viene esportato se qualcuno fa "from agent import *"
__all__ = ["PredictiveAgent"]