# ai-narrator/narrator/core/theory_engine/world_simulation_engine.py

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from narrator.logger import logger


class WorldSimulationEngine:
    """
    Motor de Simulación del Mundo.
    
    Gestiona los Frentes (amenazas activas) y la Reputación de Facciones.
    Avanza el mundo independientemente de si los jugadores interactúan o no,
    creando una sensación de "mundo vivo" (Principio Universal #7).
    """

    def __init__(self, config_path: Path, vault_path: Path):
        """
        Args:
            config_path: Ruta a la carpeta que contiene el archivo universal_world_tools.yaml.
            vault_path: Ruta a la carpeta del Vault (donde se guarda el estado persistente).
        """
        self.config_path = config_path
        self.vault_path = vault_path
        self.state_file = vault_path / "world_state.json"
        
        # Cargar configuración de herramientas del mundo
        self.tools_config = self._load_tools_config()
        
        # Cargar o inicializar estado del mundo (frentes y reputaciones)
        self.state = self._load_or_initialize_state()

    def _load_tools_config(self) -> Dict:
        """Carga el archivo universal_world_tools.yaml."""
        yaml_file = self.config_path / "universal_world_tools.yaml"
        if not yaml_file.exists():
            logger.warning("Archivo universal_world_tools.yaml no encontrado. Usando configuración por defecto.")
            return self._get_default_tools_config()
        
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error al cargar universal_world_tools.yaml: {e}")
            return self._get_default_tools_config()

    def _get_default_tools_config(self) -> Dict:
        """Configuración por defecto si el YAML no está disponible."""
        return {
            'world_tools': [
                {
                    'type': 'Reloj de Frente',
                    'description': 'Cuenta regresiva de amenaza.',
                    'default_stages': ['1: Rumores', '2: Amenaza visible', '3: Crisis']
                },
                {
                    'type': 'Tabla de Consecuencias Sociales',
                    'description': 'Reputación por facción.',
                    'mechanics': [
                        {'accion': 'Hacer favor', 'efecto': '+1 Reputación'},
                        {'accion': 'Traicionar', 'efecto': '-2 Reputación'},
                        {'accion': 'Ignorar petición', 'efecto': '-1 Reputación'}
                    ]
                }
            ]
        }

    def _load_or_initialize_state(self) -> Dict:
        """
        Carga el estado del mundo desde world_state.json o inicializa uno nuevo.
        """
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error al leer world_state.json: {e}. Reinicializando estado.")
                return self._initialize_new_state()
        else:
            return self._initialize_new_state()

    def _initialize_new_state(self) -> Dict:
        """Crea un estado inicial vacío para los frentes y reputaciones."""
        return {
            'fronts': {},      # {nombre: {'stage': int, 'name': str, 'max_stage': int, 'last_advanced': str}}
            'reputation': {},  # {nombre_faccion: int}
            'global_events': [] # Lista de eventos recientes que han ocurrido en el mundo
        }

    def _save_state(self) -> None:
        """Guarda el estado actual del mundo en el archivo JSON."""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error al guardar world_state.json: {e}")

    # --- Gestión de Frentes ---

    def initialize_front(self, name: str, description: str, initial_stage: int = 1, max_stage: int = 3) -> None:
        """
        Crea un nuevo frente en el mundo.
        
        Args:
            name: Nombre único del frente (ej. 'El Culto del Vacío').
            description: Descripción breve del frente.
            initial_stage: Etapa inicial (1-3, por defecto 1).
            max_stage: Etapa máxima (por defecto 3).
        """
        if name in self.state['fronts']:
            logger.warning(f"El frente '{name}' ya existe. No se ha vuelto a crear.")
            return

        self.state['fronts'][name] = {
            'description': description,
            'stage': initial_stage,
            'max_stage': max_stage,
            'last_advanced': datetime.now().isoformat()
        }
        self._save_state()
        logger.info(f"Nuevo frente creado: {name} (Etapa {initial_stage}/{max_stage})")

    def advance_front(self, name: str, steps: int = 1) -> Optional[int]:
        """
        Avanza el reloj de un frente específico.
        
        Args:
            name: Nombre del frente.
            steps: Número de etapas a avanzar (por defecto 1).
            
        Returns:
            La nueva etapa del frente, o None si el frente no existe o ya está en etapa máxima.
        """
        front = self.state['fronts'].get(name)
        if not front:
            logger.warning(f"Frente '{name}' no encontrado.")
            return None

        new_stage = front['stage'] + steps
        if new_stage > front['max_stage']:
            new_stage = front['max_stage']
        
        if new_stage != front['stage']:
            front['stage'] = new_stage
            front['last_advanced'] = datetime.now().isoformat()
            self._save_state()
            logger.info(f"Frente '{name}' avanzó a etapa {new_stage}")
            
            # Registrar evento global si se alcanza la etapa 2 o 3
            if new_stage >= 2:
                self._add_global_event(f"El frente '{name}' ha alcanzado la etapa {new_stage}.")
        
        return new_stage

    def advance_all_fronts(self, steps: int = 1) -> Dict[str, int]:
        """
        Avanza todos los frentes activos.
        
        Args:
            steps: Número de etapas a avanzar para cada frente.
            
        Returns:
            Diccionario {nombre_frente: nueva_etapa} con los frentes que avanzaron.
        """
        advanced = {}
        for name in list(self.state['fronts'].keys()):
            new_stage = self.advance_front(name, steps)
            if new_stage is not None and new_stage > 0:
                advanced[name] = new_stage
        return advanced

    def get_front_stage(self, name: str) -> Optional[int]:
        """Obtiene la etapa actual de un frente."""
        front = self.state['fronts'].get(name)
        return front['stage'] if front else None

    def get_active_fronts(self, min_stage: int = 1) -> Dict[str, int]:
        """Obtiene todos los frentes con etapa >= min_stage."""
        return {name: data['stage'] for name, data in self.state['fronts'].items() if data['stage'] >= min_stage}

    # --- Gestión de Reputación de Facciones ---

    def adjust_reputation(self, faction: str, delta: int) -> int:
        """
        Ajusta la reputación de una facción basado en las acciones de los jugadores.
        
        Args:
            faction: Nombre de la facción (ej. 'La Guardia Real', 'El Culto').
            delta: Cambio en la reputación (+1, -2, etc.).
            
        Returns:
            La nueva reputación de la facción.
        """
        current = self.state['reputation'].get(faction, 0)
        new_value = current + delta
        self.state['reputation'][faction] = new_value
        self._save_state()
        
        # Registrar efecto automático según la tabla de consecuencias
        if new_value <= -5:
            self._add_global_event(f"La facción '{faction}' ahora te considera un enemigo mortal.")
        elif new_value >= 10:
            self._add_global_event(f"La facción '{faction}' confía plenamente en ti y te ofrece una alianza estratégica.")
        
        logger.info(f"Reputación con '{faction}': {current} -> {new_value}")
        return new_value

    def get_reputation(self, faction: str) -> int:
        """Obtiene la reputación actual de una facción."""
        return self.state['reputation'].get(faction, 0)

    def get_all_reputations(self) -> Dict[str, int]:
        """Obtiene todas las reputaciones."""
        return self.state['reputation']

    # --- Eventos Globales ---

    def _add_global_event(self, message: str) -> None:
        """Añade un evento a la lista de eventos globales."""
        self.state['global_events'].append({
            'timestamp': datetime.now().isoformat(),
            'message': message
        })
        # Mantener solo los últimos 20 eventos para no sobrecargar el estado
        if len(self.state['global_events']) > 20:
            self.state['global_events'] = self.state['global_events'][-20:]
        self._save_state()

    def get_recent_events(self, limit: int = 5) -> List[str]:
        """Obtiene los últimos eventos globales."""
        recent = self.state['global_events'][-limit:]
        return [event['message'] for event in recent]

    # --- Informe de estado del mundo ---

    def get_world_status(self) -> Dict:
        """
        Devuelve un resumen completo del estado actual del mundo para el orquestador.
        """
        return {
            'active_fronts': self.get_active_fronts(min_stage=1),
            'critical_fronts': self.get_active_fronts(min_stage=3),
            'reputation': self.state['reputation'],
            'recent_events': self.get_recent_events(limit=5)
        }

    # --- Mantenimiento y ciclo de vida ---

    def tick_all_fronts(self, session_minutes: int = 0, scenes_passed: int = 0) -> Dict[str, int]:
        """
        Método principal para simular el paso del tiempo en el mundo.
        Se llama al final de cada sesión o escena para avanzar los frentes automáticamente.
        
        Args:
            session_minutes: Minutos narrativos que han pasado en la sesión.
            scenes_passed: Cantidad de escenas que han pasado.
            
        Returns:
            Diccionario con los frentes que avanzaron.
        """
        # Lógica: Avanzar al menos 1 etapa por sesión, más 1 extra por cada 60 min narrativos o 3 escenas
        steps = 1
        if session_minutes >= 60:
            steps += 1
        if scenes_passed >= 3:
            steps += 1
        
        advanced = self.advance_all_fronts(steps)
        logger.info(f"Ciclo de mundo ejecutado. Frentes avanzados: {len(advanced)}")
        return advanced