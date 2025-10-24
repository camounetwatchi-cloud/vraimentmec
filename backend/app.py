from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import queue
from chess_generator import generate_fen_position

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin

# Queue pour gérer les résultats des threads
result_queue = queue.Queue()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "message": "Chess FEN Generator API",
        "endpoints": {
            "/api/generate": "POST - Generate a chess position"
        }
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    """Endpoint pour générer une position d'échecs"""
    try:
        # Récupérer les paramètres optionnels
        data = request.get_json() if request.is_json else {}
        
        target_min = data.get('target_min', 25)
        target_max = data.get('target_max', 100)
        max_attempts = data.get('max_attempts', 20000)
        
        # Lancer la génération dans un thread
        def run_generation():
            try:
                result = generate_fen_position(
                    target_min=target_min,
                    target_max=target_max,
                    max_attempts=max_attempts
                )
                result_queue.put(result)
            except Exception as e:
                result_queue.put({"error": str(e)})
        
        thread = threading.Thread(target=run_generation)
        thread.start()
        thread.join(timeout=120)  # Timeout de 2 minutes
        
        if thread.is_alive():
            return jsonify({
                "success": False,
                "error": "Timeout: La génération a pris trop de temps"
            }), 408
        
        result = result_queue.get()
        
        if "error" in result:
            return jsonify({
                "success": False,
                "error": result["error"]
            }), 500
        
        return jsonify({
            "success": True,
            "data": result
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/status', methods=['GET'])
def status():
    """Vérifie que le moteur Stockfish est disponible"""
    try:
        import os
        from chess_generator import STOCKFISH_PATH
        
        exists = os.path.exists(STOCKFISH_PATH)
        
        return jsonify({
            "stockfish_available": exists,
            "stockfish_path": STOCKFISH_PATH
        })
    except Exception as e:
        return jsonify({
            "stockfish_available": False,
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
