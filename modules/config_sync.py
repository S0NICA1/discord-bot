from config import TONY_PERSONA, GEMINI_TEMPERATURE

# Global state to easily get/set variables without circular imports
_current_persona = TONY_PERSONA
_current_temperature = GEMINI_TEMPERATURE

def get_persona():
    return _current_persona

def set_persona(new_persona):
    global _current_persona
    _current_persona = new_persona

def get_temperature():
    return _current_temperature

def set_temperature(new_temp):
    global _current_temperature
    _current_temperature = new_temp
