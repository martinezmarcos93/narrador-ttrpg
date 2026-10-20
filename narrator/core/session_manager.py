import json
from datetime import datetime
from pathlib import Path

from narrator.logger import logger

SAVE_DIR = Path.home() / ".ai_narrator"

class SessionManager:
    def __init__(self, save_dir: Path = SAVE_DIR):
        self.save_dir = save_dir
        self.save_dir.mkdir(exist_ok=True)
        self.session_file = self.save_dir / "session.json"

    def save_session(self, state: dict) -> str:
        data = {
            "character": state.get("character", {}),
            "messages": state.get("messages", [])[-40:],
            "system_name": state.get("system_name", ""),
            "system_slug": state.get("system_slug", "generic"),
            "manual_name": state.get("manual_name", ""),
            "session_log": state.get("session_log", []),
            "phase": state.get("phase", "idle"),
            "session_number": state.get("session_number", 1),
            "memoria_episodica": state.get("memoria_episodica", {}),
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(self.session_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return str(self.session_file)
        except Exception as e:
            logger.error(f"Error saving session: {e}", exc_info=True)
            return ""

    def load_session(self, state: dict) -> bool:
        if self.session_file.exists():
            try:
                with open(self.session_file, encoding="utf-8") as f:
                    data = json.load(f)
                state.update({
                    "character": data.get("character", {}),
                    "messages": data.get("messages", []),
                    "system_name": data.get("system_name", ""),
                    "system_slug": data.get("system_slug", "generic"),
                    "manual_name": data.get("manual_name", ""),
                    "session_log": data.get("session_log", []),
                    "phase": data.get("phase", "idle"),
                    "session_number": data.get("session_number", 1),
                    "memoria_episodica": data.get("memoria_episodica", {}),
                })
                return True
            except Exception as e:
                logger.error(f"Error loading session: {e}", exc_info=True)
        return False
