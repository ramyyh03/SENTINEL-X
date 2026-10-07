"""BRIQUE 6.5 — Vérifie qu'Ollama tourne en local (localhost:11434)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api.server import _ollama_status  # noqa: E402

if __name__ == "__main__":
    s = _ollama_status()
    if s.get("online"):
        print(f"🟢 Ollama EN LIGNE — modèles : {', '.join(s.get('models') or []) or '(aucun, fais: ollama pull mistral)'}")
        sys.exit(0)
    print("🔴 Ollama HORS LIGNE.")
    print("   → Installe-le sur https://ollama.ai, puis : ollama serve  et  ollama pull mistral")
    sys.exit(1)
