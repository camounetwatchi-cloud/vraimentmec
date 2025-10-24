from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import queue
import os

# --- Imports pour la Base de Données (Ajoutés) ---
from flask_sqlalchemy import SQLAlchemy
from db_models import db, init_db # Import de la nouvelle logique BDD

# --- Votre Logique Métier ---
from chess_generator import generate_fen_position

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin

# =========================================================
# CONFIGURATION DE LA BASE DE DONNÉES (POUR AWS RDS)
# =========================================================

# 1. Lecture des variables d'environnement (Définies dans Elastic Beanstalk)
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = 5432 # Port standard pour PostgreSQL

# 2. Construction de l'URI de connexion
if all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
    # Exemple pour PostgreSQL (nécessite psycopg2-binary dans requirements.txt)
    SQLALCHEMY_DATABASE_URI = (
        f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialise la connexion et crée les tables si l'application s'exécute sur le serveur
    init_db(app)
    print(f"INFO: Connexion à la BDD RDS réussie sur {DB_HOST}")
else:
    # Utilisation d'une BDD SQLite locale pour le développement
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///local_chess_db.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    init_db(app)
    print("ATTENTION: Variables AWS non trouvées. Utilisation de la base de données SQLite locale.")


# Queue pour gérer les résultats des threads
result_queue = queue.Queue()

# =========================================================
# ENDPOINTS FLASK
# =========================================================

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "database_connected": bool(DB_HOST),
        "message": "Chess FEN Generator API",
        "endpoints": {
            "/api/generate": "POST - Generate a chess position"
        }
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    """Endpoint pour générer une position d'échecs"""
    # Votre logique de génération reste la même
    try:
        # ... (Votre code de génération non modifié) ...
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
        from chess_generator import STOCKFISH_PATH
        
        exists = os.path.exists(STOCKFISH_PATH)
        
        return jsonify({
            "stockfish_available": exists,
            "stockfish_path": STOCKFISH_PATH,
            "db_host": DB_HOST if DB_HOST else "Non configuré"
        })
    except Exception as e:
        return jsonify({
            "stockfish_available": False,
            "error": str(e)
        })

# La ligne ci-dessous n'est pas utilisée par gunicorn sur Elastic Beanstalk
if __name__ == '__main__':
    # Lance la base de données en local si les variables d'environnement ne sont pas là
    with app.app_context():
        db.create_all()
    app.run(debug=True)
