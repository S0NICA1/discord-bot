"""
dossier.py - سجل السوابق والفضائح (Criminal Dossier) لأعضاء السيرفر
Backward compatibility facade delegating directly to atomic StateManager.
"""
from modules.state_manager import StateManager, state_mgr

# Backward compatibility aliases
DossierManager = StateManager
dossier_mgr = state_mgr
