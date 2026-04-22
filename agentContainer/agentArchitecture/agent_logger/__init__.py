# Importiamo la classe principale del nostro agente da config.py
from .logger_core import LoggerAgent

# (Opzionale) Definiamo cosa viene esportato se qualcuno fa "from agent import *"
__all__ = ["LoggerAgent"]