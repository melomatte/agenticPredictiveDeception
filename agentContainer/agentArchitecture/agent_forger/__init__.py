# Importiamo la classe principale del nostro agente da config.py
from .forger_core import ForgerAgent

# (Opzionale) Definiamo cosa viene esportato se qualcuno fa "from agent import *"
__all__ = ["ForgerAgent"]