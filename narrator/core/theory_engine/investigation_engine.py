# ai-narrator/narrator/core/theory_engine/investigation_engine.py

import json
import random
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from narrator.logger import logger


class InvestigationEngine:
    """
    Motor de Investigación y Desbloqueo Narrativo.
    
    Implementa la Regla de los 3 indicios para garantizar que los jugadores
    nunca queden bloqueados en una historia (Principio Universal #5).
    Detecta cuándo una pista ha sido ignorada o perdida, y coloca automáticamente
    pistas alternativas en lugares accesibles.
    
    Principios aplicados:
    - Principio #5: Evitar bloqueos narrativos (Regla de los 3 indicios).
    - Principio #8: Permitir decisiones reales (múltiples caminos hacia la verdad).
    """

    def __init__(self, config_path: Path, vault_path: Path):
        """
        Args:
            config_path: Ruta a la carpeta que contiene universal_narrative_tools.yaml.
            vault_path: Ruta a la carpeta del Vault (para leer/guardar estado persistente).
        """
        self.config_path = config_path
        self.vault_path = vault_path
        
        # Estado de pistas y nodos de investigación
        self.investigation_state = self._load_or_initialize_state()
        
        # Cargar configuración desde YAML
        self.tools_config = self._load_tools_config()
        
        # Tabla de búsqueda de pistas activas
        self.active_clues = {}  # {pista_id: {data}}
        self._build_active_clues()

    def _load_tools_config(self) -> Dict:
        """Carga la configuración de herramientas narrativas."""
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
        """Configuración por defecto de la Regla de los 3 indicios."""
        return {
            'investigation_rules': {
                'clue_redundancy': 3,  # Número de rutas alternativas (Regla de los 3 indicios)
                'clue_timeout_seconds': 1200,  # 20 minutos sin interactuar con una pista la vuelve obsoleta
                'auto_generate_alt_clues': True,  # Generar pistas alternativas automáticamente
                'max_alt_clues': 5  # Máximo de pistas alternativas por evento
            }
        }

    def _load_or_initialize_state(self) -> Dict:
        """Carga el estado de la investigación desde un archivo JSON en el Vault."""
        state_file = self.vault_path / "investigation_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error al leer investigation_state.json: {e}")
                return self._initialize_new_state()
        else:
            return self._initialize_new_state()

    def _initialize_new_state(self) -> Dict:
        """Crea un nuevo estado de investigación."""
        return {
            'mysteries': {},  # {mystery_id: {'clues_found': [], 'all_clues': [], 'status': 'active'}}
            'clues_by_location': {},  # {location_id: [clue_id, clue_id...]}
            'global_clues': []  # Pistas que no están en una ubicación fija (ej. un NPC con información)
        }

    def _build_active_clues(self) -> None:
        """Construye una tabla de búsqueda rápida para pistas activas."""
        for mystery_id, mystery_data in self.investigation_state.get('mysteries', {}).items():
            for clue_id in mystery_data.get('all_clues', []):
                if clue_id not in mystery_data.get('clues_found', []):
                    self.active_clues[clue_id] = {
                        'mystery_id': mystery_id,
                        'data': self._get_clue_data(clue_id)
                    }

    def _get_clue_data(self, clue_id: str) -> Dict:
        """Recupera los datos de una pista específica desde el estado."""
        for mystery_id, mystery_data in self.investigation_state.get('mysteries', {}).items():
            for clue in mystery_data.get('all_clues', []):
                if clue.get('id') == clue_id:
                    return clue
        return {}

    # --- Registro de Misterios ---

    def register_mystery(self, mystery_id: str, description: str, initial_clues: List[Dict]) -> None:
        """
        Registra un nuevo misterio con sus pistas iniciales.
        
        Args:
            mystery_id: Identificador único del misterio.
            description: Descripción del misterio (ej. '¿Quién es el asesino del alcalde?').
            initial_clues: Lista de pistas iniciales. Cada pista es un dict con:
                           - id: str (único)
                           - description: str
                           - location: str (ID de ubicación o 'NPC:NOMBRE')
                           - lead_to: str (ID del siguiente paso, opcional)
                           - alternative_clues: List[str] (IDs de pistas alternativas, opcional)
        """
        if mystery_id in self.investigation_state['mysteries']:
            logger.warning(f"El misterio '{mystery_id}' ya está registrado. No se ha vuelto a crear.")
            return

        # Configurar las pistas
        for clue in initial_clues:
            clue['active'] = True
            clue['found'] = False
            
            # Registrar en el mapa de ubicaciones
            location = clue.get('location', 'global')
            if location not in self.investigation_state['clues_by_location']:
                self.investigation_state['clues_by_location'][location] = []
            self.investigation_state['clues_by_location'][location].append(clue['id'])

        self.investigation_state['mysteries'][mystery_id] = {
            'description': description,
            'all_clues': initial_clues,
            'clues_found': [],
            'status': 'active',
            'dead_ends': []  # Pistas que llevaron a un callejón sin salida
        }
        self._build_active_clues()
        self._save_state()
        logger.info(f"Misterio registrado: {mystery_id} con {len(initial_clues)} pistas iniciales.")

    def _save_state(self) -> None:
        """Guarda el estado de la investigación en el Vault."""
        state_file = self.vault_path / "investigation_state.json"
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(self.investigation_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error al guardar investigation_state.json: {e}")

    # --- Gestión de Pistas ---

    def clue_found(self, clue_id: str, mystery_id: str = None) -> None:
        """
        Marca una pista como encontrada por los jugadores.
        
        Args:
            clue_id: ID de la pista encontrada.
            mystery_id: ID del misterio al que pertenece (opcional, si no se especifica se buscará).
        """
        # Si no se especifica el misterio, buscar en todos
        if not mystery_id:
            for mid, m_data in self.investigation_state['mysteries'].items():
                if any(clue.get('id') == clue_id for clue in m_data['all_clues']):
                    mystery_id = mid
                    break
        
        if not mystery_id:
            logger.warning(f"Pista '{clue_id}' no encontrada en ningún misterio.")
            return

        mystery = self.investigation_state['mysteries'].get(mystery_id)
        if not mystery:
            logger.warning(f"Misterio '{mystery_id}' no encontrado.")
            return

        # Marcar la pista como encontrada
        for clue in mystery['all_clues']:
            if clue.get('id') == clue_id:
                clue['found'] = True
                clue['active'] = False
                mystery['clues_found'].append(clue_id)
                
                # Eliminar de la lista de pistas activas
                if clue_id in self.active_clues:
                    del self.active_clues[clue_id]
                
                # Eliminar del mapa de ubicaciones
                location = clue.get('location', 'global')
                if location in self.investigation_state['clues_by_location']:
                    if clue_id in self.investigation_state['clues_by_location'][location]:
                        self.investigation_state['clues_by_location'][location].remove(clue_id)
                
                self._save_state()
                logger.info(f"Pista '{clue_id}' encontrada en misterio '{mystery_id}'.")
                return

        logger.warning(f"Pista '{clue_id}' no encontrada en misterio '{mystery_id}'.")

    def get_next_clues(self, mystery_id: str) -> List[Dict]:
        """
        Obtiene las pistas activas disponibles para un misterio.
        Aplica la Regla de los 3 indicios: si una pista ha sido ignorada demasiado tiempo,
        se activa una alternativa.
        
        Args:
            mystery_id: ID del misterio.
            
        Returns:
            Lista de pistas activas (diccionarios completos).
        """
        mystery = self.investigation_state['mysteries'].get(mystery_id)
        if not mystery:
            return []

        available_clues = []
        for clue in mystery['all_clues']:
            # Una pista es disponible si:
            # 1) Está activa (no encontrada)
            # 2) Su ubicación es accesible (no ha sido destruida o bloqueada)
            # 3) O es una pista alternativa (si la regla de 3 indicios se activa)
            if clue.get('active', False) and not clue.get('found', False):
                available_clues.append(clue)

        # Si hay menos de 3 pistas disponibles, activar alternativas
        # (Regla de los 3 indicios)
        if len(available_clues) < self.tools_config.get('investigation_rules', {}).get('clue_redundancy', 3):
            # Activar pistas alternativas
            self._activate_alternative_clues(mystery_id)
            # Re-evaluar
            available_clues = []
            for clue in mystery['all_clues']:
                if clue.get('active', False) and not clue.get('found', False):
                    available_clues.append(clue)

        return available_clues

    def _activate_alternative_clues(self, mystery_id: str) -> None:
        """
        Activa pistas alternativas para un misterio (Regla de los 3 indicios).
        """
        mystery = self.investigation_state['mysteries'].get(mystery_id)
        if not mystery:
            return

        # Buscar pistas que tengan alternativas definidas
        for clue in mystery['all_clues']:
            if clue.get('found', False):
                continue  # Ya encontrada, no activar alternativas
            
            # Si la pista tiene alternativas definidas, activarlas
            alternative_ids = clue.get('alternative_clues', [])
            for alt_id in alternative_ids:
                # Buscar la pista alternativa en todas las pistas del misterio
                for alt_clue in mystery['all_clues']:
                    if alt_clue.get('id') == alt_id:
                        alt_clue['active'] = True
                        logger.info(f"Pista alternativa '{alt_id}' activada para el misterio '{mystery_id}'.")
                        break
        
        self._build_active_clues()
        self._save_state()

    # --- Detección de Bloqueos ---

    def check_for_blockade(self, context: Dict) -> Optional[Dict]:
        """
        Detecta si los jugadores están en un punto muerto narrativo.

        context esperado:
          - quiet_turns: int — turnos consecutivos sin acción de investigación relevante
        """
        if not self.investigation_state.get('mysteries'):
            return None

        quiet_turns = context.get('quiet_turns', 0)
        timeout_turns = self.tools_config.get('investigation_rules', {}).get('clue_timeout_turns', 4)

        if quiet_turns < timeout_turns:
            return None

        mystery_id = self._get_most_stalled_mystery()
        if mystery_id:
            return {
                'mystery_id': mystery_id,
                'issue': 'stalled',
                'suggestion': self._generate_blockade_solution(mystery_id),
            }
        return None

    def _get_most_stalled_mystery(self) -> Optional[str]:
        """Encuentra el misterio que más tiempo lleva sin avanzar."""
        # Esta función necesitaría analizar el historial de pistas encontradas.
        # Por ahora, retorna el primer misterio activo.
        for mystery_id, data in self.investigation_state['mysteries'].items():
            if data['status'] == 'active' and len(data['clues_found']) < len(data['all_clues']):
                return mystery_id
        return None

    def _generate_blockade_solution(self, mystery_id: str) -> str:
        """
        Genera una solución narrativa para desbloquear un misterio.
        
        La solución puede ser:
        - Una pista alternativa (Regla de los 3 indicios).
        - Un NPC que ofrece información adicional.
        - Un evento inesperado que revela una nueva dirección.
        """
        solutions = [
            f"Un PNJ amigable se acerca y menciona un rumor sobre el misterio '{mystery_id}'.",
            "Un encuentro casual revela una pista que habían pasado por alto.",
            "Alguien deja caer un objeto que contiene información clave.",
            "Una visión o sueño proporciona una pista críptica pero útil."
        ]
        return random.choice(solutions)

    # --- Interfaz para el Orquestador ---

    def resolve_stall(self, mystery_id: str) -> Dict:
        """
        Resuelve un bloqueo narrativo generando una nueva pista en una ubicación accesible.
        Aplica la Regla de los 3 indicios.
        
        Args:
            mystery_id: ID del misterio bloqueado.
            
        Returns:
            Una instrucción para el narrador: qué pista, dónde y cómo presentarla.
        """
        mystery = self.investigation_state['mysteries'].get(mystery_id)
        if not mystery:
            return {'error': f"Misterio '{mystery_id}' no encontrado."}

        # Buscar pistas activas no encontradas
        available_clues = self.get_next_clues(mystery_id)
        if available_clues:
            # Si hay pistas disponibles, fuerz la activación de una
            chosen_clue = random.choice(available_clues)
            return {
                'action': 'present_clue',
                'clue_id': chosen_clue['id'],
                'location': chosen_clue.get('location', 'global'),
                'description': chosen_clue.get('description', 'Una pista misteriosa.'),
                'instruction': "El narrador debe presentar esta pista de manera natural en la escena actual."
            }

        # Si no hay pistas activas, el misterio no se puede resolver con lo actual
        # Crear una nueva pista de emergencia
        new_clue = self._create_emergency_clue(mystery_id)
        return {
            'action': 'emergency_clue',
            'clue_id': new_clue['id'],
            'location': 'current_scene',
            'description': new_clue['description'],
            'instruction': "El narrador debe crear un evento o un objeto en la escena actual que revele esta pista."
        }

    def get_active_mysteries_summary(self) -> str:
        """Resumen de misterios activos para inyectar en el system prompt."""
        mysteries = self.investigation_state.get('mysteries', {})
        if not mysteries:
            return ""
        lines = []
        for mid, data in mysteries.items():
            if data.get('status') != 'active':
                continue
            found = len(data.get('clues_found', []))
            total = len(data.get('all_clues', []))
            lines.append(f"- {data.get('description', mid)} ({found}/{total} pistas encontradas)")
        return "\n".join(lines)

    def _create_emergency_clue(self, mystery_id: str) -> Dict:
        """Crea una pista de emergencia para un misterio bloqueado."""
        mystery = self.investigation_state['mysteries'].get(mystery_id)
        clue_id = f"emergency_{mystery_id}_{len(mystery['all_clues'])}"
        new_clue = {
            'id': clue_id,
            'description': f"Una pista inesperada que revela información crucial sobre {mystery['description']}.",
            'location': 'current_scene',
            'active': True,
            'found': False,
            'emergency': True
        }
        mystery['all_clues'].append(new_clue)
        self._build_active_clues()
        self._save_state()
        logger.info(f"Pista de emergencia '{clue_id}' creada para el misterio '{mystery_id}'.")
        return new_clue