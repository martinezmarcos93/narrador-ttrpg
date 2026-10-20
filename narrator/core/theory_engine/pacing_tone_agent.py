# ai-narrator/narrator/core/theory_engine/pacing_tone_agent.py

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml

from narrator.logger import logger


class PacingToneAgent:
    """
    Agente de Pacing y Tono Narrativo.
    
    Analiza el ritmo de la partida y decide si es momento de acelerar (tensión)
    o ralentizar (calma). También selecciona un tono narrativo adecuado para
    la escena actual basado en el contexto y el estado de los personajes.
    
    Principios aplicados:
    - Principio #6: Usar el ritmo conscientemente.
    - Principio #4: Mantener tensión constante.
    - Principio #11: La narración es 90% descripción sensorial.
    - Principio #12: El director debe reaccionar, no dominar.
    """

    def __init__(self, config_path: Path):
        """
        Args:
            config_path: Ruta a la carpeta que contiene universal_narrative_tools.yaml.
        """
        self.config_path = config_path
        self.tools_config = self._load_tools_config()
        
        # Historial de eventos de la sesión
        self.event_history = deque(maxlen=20)  # Guarda los últimos 20 eventos
        
        # Métricas de tensión
        self.tension_score = 0.0
        self.last_tension_update = datetime.now()
        
        # Estado actual
        self.current_pacing = "neutral"  # 'acelerado', 'ralentizado', 'neutral'
        self.current_tone = "neutral"    # 'epico', 'pesadillesco', 'misterioso', 'desesperado', 'heroico', 'neutral'
        self.pacing_duration = 0.0       # Tiempo en minutos que lleva el pacing actual

    def _load_tools_config(self) -> Dict:
        """Carga las herramientas narrativas y define los tonos disponibles."""
        yaml_file = self.config_path / "universal_narrative_tools.yaml"
        if not yaml_file.exists():
            logger.warning("universal_narrative_tools.yaml no encontrado. Usando configuración por defecto.")
            return self._get_default_config()
        
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error al cargar universal_narrative_tools.yaml: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Configuración por defecto de tonos y reglas de pacing."""
        return {
            'tone_states': [
                {'name': 'epico', 'description': 'Escenas de combate, acción, heroísmo.'},
                {'name': 'pesadillesco', 'description': 'Horror, tensión, atmósfera opresiva.'},
                {'name': 'misterioso', 'description': 'Exploración, investigación, descubrimientos.'},
                {'name': 'desesperado', 'description': 'Fracaso, pérdida, desesperanza.'},
                {'name': 'heroico', 'description': 'Victoria, alianza, esperanza.'},
                {'name': 'neutral', 'description': 'Diálogo, preparación, transición.'}
            ],
            'pacing_rules': {
                'max_tension_minutes': 15,
                'min_tension_minutes': 3,
                'rest_threshold': 5  # Minutos de diálogo/descanso para considerar una pausa
            }
        }

    # --- Gestión del Historial de Eventos ---

    def update_event_history(self, event_type: str, intensity: int = 1) -> None:
        """
        Añade un evento al historial de la sesión.
        
        Args:
            event_type: Tipo de evento ('combate', 'dialogo', 'exploracion', 'descanso', 'persecucion', 'horror').
            intensity: Intensidad del evento (1-5, por defecto 1).
        """
        event = {
            'type': event_type,
            'intensity': intensity,
            'timestamp': datetime.now().isoformat()
        }
        self.event_history.append(event)
        self._update_tension_score()
        self._update_pacing_duration()

    def _update_tension_score(self) -> None:
        """Actualiza el puntaje de tensión basado en los eventos recientes."""
        if not self.event_history:
            self.tension_score = 0.0
            return

        # Calcular peso de los últimos 10 eventos
        recent_events = list(self.event_history)[-10:]
        weights = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        
        tension_scores = []
        for event, weight in zip(reversed(recent_events), weights):
            base_score = 0.0
            if event['type'] in ['combate', 'persecucion', 'horror']:
                base_score = 3.0 * event['intensity']
            elif event['type'] == 'exploracion':
                base_score = 1.0 * event['intensity']
            elif event['type'] == 'dialogo':
                base_score = 0.5 * event['intensity']
            elif event['type'] == 'descanso':
                base_score = -1.0 * event['intensity']
            tension_scores.append(base_score * weight)

        self.tension_score = sum(tension_scores) / max(0.1, len(tension_scores))
        self.last_tension_update = datetime.now()

    def _update_pacing_duration(self) -> None:
        """Actualiza el tiempo que lleva el pacing actual."""
        # Esto se manejará en el método tick() que se llama periódicamente
        pass

    # --- TICK: Ejecutar el ciclo de análisis ---

    def tick(self, minutes_since_last_tick: float = 1.0) -> Dict:
        """
        Ejecuta un ciclo de análisis de pacing y tono.
        Se debe llamar periódicamente (ej. cada minuto de juego).
        
        Args:
            minutes_since_last_tick: Minutos narrativos transcurridos desde el último tick.
            
        Returns:
            Instrucción de pacing y tono para el orquestador.
        """
        self.pacing_duration += minutes_since_last_tick
        
        # 1. Decidir Pacing
        pacing_decision = self._decide_pacing()
        
        # 2. Decidir Tono
        tone_decision = self._decide_tone()
        
        # 3. Generar instrucciones narrativas
        instruction = self._generate_instruction(pacing_decision, tone_decision)
        
        # Resetear duración si ha cambiado el pacing
        if pacing_decision != self.current_pacing:
            self.pacing_duration = 0.0
            self.current_pacing = pacing_decision
        
        self.current_tone = tone_decision
        
        return {
            'pacing': pacing_decision,
            'tone': tone_decision,
            'instruction': instruction,
            'tension_score': self.tension_score
        }

    def _decide_pacing(self) -> str:
        """
        Decide si acelerar, ralentizar o mantener el ritmo.
        Reglas basadas en el Principio #6 (Pacing inteligente).
        """
        # Regla 1: Si hay combate o persecución en los últimos 3 eventos -> ralentizar después de un tiempo
        recent_types = [e['type'] for e in list(self.event_history)[-3:]]
        if any(t in ['combate', 'persecucion', 'horror'] for t in recent_types):
            if self.pacing_duration > self.tools_config.get('pacing_rules', {}).get('max_tension_minutes', 15):
                return "ralentizado"
            else:
                return "acelerado"

        # Regla 2: Si los últimos eventos son diálogo/descanso -> acelerar después de un tiempo
        if all(t in ['dialogo', 'descanso', 'exploracion'] for t in recent_types):
            rest_duration = self.pacing_duration
            if rest_duration > self.tools_config.get('pacing_rules', {}).get('rest_threshold', 5):
                return "acelerado"
            else:
                return "neutral"

        # Regla 3: Si el puntaje de tensión es bajo y hay tiempo sin acción -> acelerar
        if self.tension_score < 0.5 and self.pacing_duration > 10:
            return "acelerado"

        # Regla 4: Por defecto, mantener el ritmo actual
        return self.current_pacing or "neutral"

    def _decide_tone(self) -> str:
        """
        Decide el tono narrativo basado en el contexto y el pacing.
        """
        # Si el pacing es acelerado -> tonos de acción
        if self.current_pacing == "acelerado":
            if self.tension_score > 5.0:
                return "pesadillesco"
            elif self.tension_score > 3.0:
                return "epico"
            else:
                return "misterioso"

        # Si el pacing es ralentizado -> tonos de reflexión
        if self.current_pacing == "ralentizado":
            if self.tension_score > 4.0:
                return "desesperado"
            else:
                return "heroico"

        # Si el pacing es neutral -> tonos de exploración o diálogo
        if self.tension_score < 2.0:
            return "misterioso"
        elif self.tension_score > 4.0:
            return "desesperado"
        else:
            return "neutral"

    def _generate_instruction(self, pacing: str, tone: str) -> str:
        """
        Genera una instrucción narrativa basada en el pacing y tono decididos.
        Aplica el Principio #11 (Narración sensorial).
        """
        instructions = []

        # Instrucciones de Pacing
        if pacing == "acelerado":
            instructions.append("- ACELERACIÓN: Usa frases cortas y cortantes. Acelera el ritmo de la acción. Aumenta la urgencia.")
            instructions.append("- No des tiempo para pensamientos profundos. La escena se mueve rápido.")
        elif pacing == "ralentizado":
            instructions.append("- RALENTIZACIÓN: Reduce el ritmo. Da tiempo para la reflexión y la descripción detallada.")
            instructions.append("- Usa pausas largas en la narración (silencios). Deja que el ambiente respire.")
        else:
            instructions.append("- RITMO NEUTRAL: Mantén un flujo narrativo constante. Alterna entre acción y diálogo.")

        # Instrucciones de Tono (basadas en los tonos definidos en el YAML)
        tone_instructions = {
            'epico': "- TONO ÉPICO: Usa vocabulario grandioso. Describe la magnitud de las acciones. Enfatiza las hazañas heroicas.",
            'pesadillesco': "- TONO PESADILLESCO: Enfócate en la oscuridad y el horror. Usa sonidos y olores extraños. Describe el miedo y la desesperación.",
            'misterioso': "- TONO MISTERIOSO: Describe lo que no se ve. Sugiere, no muestres. Crea suspense. Usa preguntas retóricas en la descripción.",
            'desesperado': "- TONO DESESPERADO: Enfatiza el cansancio, la pérdida y el costo de las acciones. Describe la fatiga física y mental.",
            'heroico': "- TONO HEROICO: Resalta la luz, la esperanza y la valentía. Usa un lenguaje inspirador. Celebra los pequeños triunfos.",
            'neutral': "- TONO NEUTRAL: Describe la escena de manera objetiva. No añadas un sesgo emocional excesivo. Deja que los jugadores sientan el ambiente."
        }
        instructions.append(tone_instructions.get(tone, "- TONO NEUTRAL: Narra de manera objetiva."))

        # Instrucciones sensoriales (Principio #11)
        sensory_instruction = "- DESCRIPCIÓN SENSORIAL: Incluye al menos 2 de los siguientes sentidos en tu descripción: vista, sonido, olfato, tacto. No uses solo la vista."
        instructions.append(sensory_instruction)

        # Instrucción de ritmo específica (Alternar tensión y descanso)
        if self.tension_score > 5.0:
            instructions.append("- ALERTA DE TENSIÓN: La tensión es muy alta. Considera dar un momento de calma pronto.")
        elif self.tension_score < 1.0:
            instructions.append("- ALERTA DE CALMA: La tensión es baja. Considera introducir un evento inesperado.")

        return "\n".join(instructions)

    # --- Métodos auxiliares ---

    def reset_session(self) -> None:
        """Reinicia el estado del agente para una nueva sesión."""
        self.event_history.clear()
        self.tension_score = 0.0
        self.current_pacing = "neutral"
        self.current_tone = "neutral"
        self.pacing_duration = 0.0
        self.last_tension_update = datetime.now()
        logger.info("PacingToneAgent reiniciado para nueva sesión.")

    def get_status(self) -> Dict:
        """Devuelve el estado actual del agente para depuración."""
        return {
            'current_pacing': self.current_pacing,
            'current_tone': self.current_tone,
            'tension_score': round(self.tension_score, 2),
            'event_history': [e['type'] for e in self.event_history],
            'pacing_duration': round(self.pacing_duration, 1)
        }