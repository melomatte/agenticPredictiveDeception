# Importiamo la classe principale del nostro agente da config.py
from .agent_core import TrafficAgent

# (Opzionale) Definiamo cosa viene esportato se qualcuno fa "from agent import *"
__all__ = ["TrafficAgent"]