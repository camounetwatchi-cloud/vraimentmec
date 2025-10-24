from flask import Flask, jsonify, request
from flask_cors import CORS
import threading
import queue
import os
import sys # Ajout pour les logs plus précis

# --- Imports pour la Base de Données (Ajoutés) ---
from db_models import db, init_db
from flask_sqlalchemy import SQLAlchemy 

# --- Votre Logique Métier ---
from chess_generator import generate_fen_position

app = Flask(__name__)
CORS(app)  # Permet les requêtes cross-origin

# Variables globales pour la configuration
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = 5432

# Drapeau pour garantir l'initialisation unique de la base de données
db_initialized = False
db_init_lock = threading.Lock()

# =========================================================
# CONFIGURATION DE LA BASE DE DONNÉES
# =========================================================

def configure_db(app):
    """Configure l'URI de la base de données."""
    if all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        # URI pour PostgreSQL RDS
        SQLALCHEMY_DATABASE_URI = (
            f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
        print(f"INFO: Tentative de connexion à RDS sur {DB_HOST}", file=sys.stderr)
    else:
        # URI pour SQLite locale (Fallback)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///local_chess_db.db'
        print("ATTENTION: Variables AWS non trouvées. Utilisation de SQLite locale.", file=sys.stderr)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

configure_db(app) # Configure l'URI, mais n'appelle PAS init_db ici

def ensure_db_is_initialized():
    """Initialise la base de données de manière thread-safe."""
    global db_initialized
    with db_init_lock:
        if not db_initialized:
            try:
                init_db(app) # Initialise l'instance db et crée les tables
                db_initialized = True
                print("INFO: Initialisation de la BDD réussie.", file=sys.stderr)
            except Exception as e:
                print(f"ERREUR BDD FATALE : {e}", file=sys.stderr)
                # En production, il est préférable de crasher l'app si la BDD est vitale
                raise Exception(f"Échec de l'initialisation de la base de données : {e}")

# =========================================================
# ENDPOINTS FLASK
# =========================================================

@app.before_request
def before_request():
    """S'assure que la base de données est initialisée avant chaque requête."""
    if not db_initialized:
        ensure_db_is_initialized()

# Queue pour gérer les résultats des threads
result_queue = queue.Queue()

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "database_connected": db_initialized,
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
        data = request.get_json() if request.is_json else {}
        
        target_min = data.get('target_min', 25)
        target_max = data.get('target_max', 100)
        max_attempts = data.get('max_attempts', 20000)
        
        # Lancer la génération dans un thread
        def run_generation():
            try:
                # Assurez-vous que l'initialisation est faite avant d'utiliser la BDD dans un thread
                if not db_initialized:
                   ensure_db_is_initialized()
                   
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
            "db_host": DB_HOST if DB_HOST else "Non configuré",
            "db_initialized": db_initialized
        })
    except Exception as e:
        return jsonify({
            "stockfish_available": False,
            "error": str(e),
            "db_initialized": db_initialized
        })

# La ligne ci-dessous n'est pas utilisée par gunicorn sur Elastic Beanstalk
if __name__ == '__main__':
    # Initialisation locale uniquement
    with app.app_context():
        ensure_db_is_initialized()
    app.run(debug=True)
