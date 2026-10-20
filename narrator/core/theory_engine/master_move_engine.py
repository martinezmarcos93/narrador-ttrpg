# ai-narrator/narrator/core/theory_engine/master_move_engine.py

import random
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from narrator.logger import logger


class MasterMoveEngine:
    """
    Motor de Movimientos del Máster.
    
    Lee el archivo universal_master_moves.yaml y selecciona un movimiento
    basado en el contexto de la partida. La lógica de selección sigue los
    Principios Universales de Narración extraídos del informe de referencia.
    """

    def __init__(self, config_path: Path):
        """
        Args:
            config_path: Ruta a la carpeta que contiene los archivos YAML.
        """
        self.config_path = config_path
        self.moves: List[Dict] = []
        self.move_names: Dict[str, Dict] = {}
        self._load_moves()

    def _load_moves(self) -> None:
        """Carga el YAML de movimientos del máster desde la ruta configurada."""
        yaml_file = self.config_path / "universal_master_moves.yaml"
        if not yaml_file.exists():
            logger.error(f"Archivo de movimientos no encontrado: {yaml_file}")
            # Cargar un conjunto mínimo de movimientos por defecto para no romper el sistema
            self.moves = self._get_default_moves()
            self._build_lookup()
            return

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self.moves = data.get('universal_master_moves', [])
            if not self.moves:
                logger.warning("El YAML no contiene movimientos. Usando movimientos por defecto.")
                self.moves = self._get_default_moves()
            self._build_lookup()
            logger.info(f"Movimientos del Máster cargados: {len(self.moves)}")
        except Exception as e:
            logger.error(f"Error al cargar YAML de movimientos: {e}")
            self.moves = self._get_default_moves()
            self._build_lookup()

    def _build_lookup(self) -> None:
        """Construye un diccionario de búsqueda rápida por nombre."""
        self.move_names = {move['name']: move for move in self.moves if 'name' in move}

    def _get_default_moves(self) -> List[Dict]:
        """Movimientos de emergencia si el archivo YAML no se puede cargar."""
        return [
            {"name": "Controlar el ritmo", "category": "Gestión",
             "trigger": "Por defecto", "instruction": "Avanza el tiempo o introduce un pequeño evento."},
            {"name": "Evento inesperado", "category": "Mundo Activo",
             "trigger": "Por defecto", "instruction": "Algo ocurre en el mundo fuera de la vista de los jugadores."}
        ]

    def select_move(self, context: Dict) -> Dict:
        """
        Selecciona un movimiento basado en el contexto de la partida.
        
        Args:
            context: Diccionario con información relevante. Campos esperados:
                     - tirada_resultado: '10+', '7-9', '6-', o None.
                     - tiempo_sin_accion: segundos (int).
                     - frente_activo: bool.
                     - jugadores_bloqueados: bool.
                     - peligro_inminente: bool.
                     - ultimo_evento: 'combate', 'dialogo', 'exploracion', 'descanso'.
                     - sesion_tiempo_total: minutos (int).
                     - relojes_por_estallar: int (cantidad de frentes en etapa crítica).
                     - pnj_en_escena: bool (si hay un PNJ en la escena actual).

        Returns:
            Un movimiento completo (diccionario con 'name', 'category', 'instruction', etc.)
        """
        # 1. Reacciones a tiradas (Prioridad más alta)
        tirada = context.get('tirada_resultado')
        if tirada == '6-':
            # Fracaso -> aplicar Fallar hacia adelante o Mostrar el costo de una acción
            # Elegir el que mejor encaje según el contexto. Si hay peligro inminente, mejor "Fallar hacia adelante".
            if context.get('peligro_inminente', False):
                move = self._get_move_by_name("Fallar hacia adelante")
            else:
                move = self._get_move_by_name("Mostrar el costo de una acción")
            if move:
                return move

        elif tirada == '7-9':
            # Éxito parcial -> Siempre "Mostrar el costo de una acción"
            move = self._get_move_by_name("Mostrar el costo de una acción")
            if move:
                return move

        elif tirada == '10+':
            # Éxito total -> Opcional: "El aliado en problemas" si el éxito fue demasiado fácil o para crear consecuencias a largo plazo
            # Por ahora, no aplicamos un movimiento automático para un 10+, el flujo normal de la narrativa continúa.
            pass

        # 2. Jugadores bloqueados o estancados (Regla de los 3 indicios se maneja en InvestigationEngine)
        if context.get('jugadores_bloqueados', False):
            # Ofrecer un dilema moral o introducir un PNJ con agenda
            # Preferimos Introducir un PNJ con agenda si no hay un PNJ en escena
            if not context.get('pnj_en_escena', False):
                move = self._get_move_by_name("Introducir un PNJ con agenda")
                if move:
                    return move
            else:
                move = self._get_move_by_name("Ofrecer un dilema moral")
                if move:
                    return move

        # 3. Mundo Activo: Frentes a punto de estallar
        if context.get('relojes_por_estallar', 0) > 0:
            # Activar un frente o mostrar el avance del tiempo
            if context.get('frente_activo', False):
                move = self._get_move_by_name("Activar un Frente")
                if move:
                    return move
            else:
                move = self._get_move_by_name("El tiempo avanza")
                if move:
                    return move

        # 4. Gestión de ritmo
        if context.get('tiempo_sin_accion', 0) > 120:  # Más de 2 minutos sin acción relevante
            # Controlar el ritmo: acelerar o ralentizar
            ultimo_evento = context.get('ultimo_evento', 'Ninguno')
            if ultimo_evento in ['combate', 'persecucion']:
                # Si el último evento fue intenso, ralentizar para dar respiro
                pass # Ralentizar es una instrucción de tono, no un movimiento específico. El ToneManager se encarga.
            else:
                # Si el último evento fue calmado, acelerar
                move = self._get_move_by_name("Controlar el ritmo")
                if move:
                    return move

        # 5. Movimiento por defecto (Mundo Activo)
        # Si nada se activa, seleccionar un movimiento aleatorio de la categoría "Mundo Activo"
        return self._get_random_move_by_category("Mundo Activo")

    def _get_move_by_name(self, name: str) -> Optional[Dict]:
        """Busca un movimiento por nombre exacto."""
        return self.move_names.get(name)

    def _get_random_move_by_category(self, category: str) -> Dict:
        """
        Selecciona un movimiento aleatorio de una categoría específica.
        Si no hay movimientos en esa categoría, devuelve un movimiento por defecto.
        """
        category_moves = [m for m in self.moves if m.get('category') == category]
        if category_moves:
            return random.choice(category_moves)
        logger.warning(f"No se encontraron movimientos en la categoría '{category}'. Usando movimiento por defecto.")
        return {"name": "Evento inesperado", "category": "Por defecto",
                "instruction": "Algo ocurre en el mundo que complica la situación de los personajes."}