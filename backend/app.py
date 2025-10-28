# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, session # Ajout de 'session'
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import queue
import os
import sys

# Importez la logique de gestion des événements et des salles
from .db_models import db, init_db
from .chess_generator import generate_fen_position
from .socket_manager import Game, MatchmakingManager, games
from .auth import auth_bp # Import du blueprint d'authentification

# --- CONFIGURATION INITIALE (Identique) ---
app = Flask(__name__)

# --- CONFIGURATION DE SESSIONS ET BLUEPRINT D'AUTHENTIFICATION (MODIFICATIONS) ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = False  # Mettre à True en production avec HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Enregistrer le blueprint d'authentification
app.register_blueprint(auth_bp, url_prefix='/api/auth')
# ---------------------------------------------------------------------------------

# Activez CORS pour les WebSockets (important pour le frontend)
# Permettre les WebSockets de toutes les origines (*) pour les tests.
CORS(app, resources={r"/*": {"origins": "*"}}) 

# Configurez Flask-SocketIO
# async_mode='gevent' est recommandé pour le scaling sur Beanstalk.
# Permet à l'ALB (Load Balancer) de gérer les connexions persistantes.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent') 

# Variables globales pour la configuration
DB_HOST = os.environ.get('DB_HOST', '').strip()
DB_USER = os.environ.get('DB_USER', '').strip()
DB_PASSWORD = os.environ.get('DB_PASSWORD', '').strip()
DB_NAME = os.environ.get('DB_NAME', '').strip()
DB_PORT = 5432

# Drapeau et Lock pour garantir l'initialisation unique de la base de données
db_initialized = False
db_init_lock = threading.Lock()

def configure_db(app):
    """Configure l'URI de la base de données."""
    if all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        from urllib.parse import quote_plus
        safe_password = quote_plus(DB_PASSWORD)
        
        SQLALCHEMY_DATABASE_URI = (
            f'postgresql://{DB_USER}:{safe_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
        )
        app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
        print(f"INFO: Tentative de connexion à RDS sur {DB_HOST}", file=sys.stderr)
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///local_chess_db.db'
        print("ATTENTION: Variables AWS non trouvées. Utilisation de SQLite locale.", file=sys.stderr)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

configure_db(app)

def ensure_db_is_initialized():
    """Initialise la base de données de manière thread-safe."""
    global db_initialized
    with db_init_lock:
        if not db_initialized:
            try:
                if 'sqlite' not in app.config['SQLALCHEMY_DATABASE_URI'] and not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
                    print("ERREUR BDD : Variables de connexion manquantes pour RDS.", file=sys.stderr)
                    db_initialized = True
                    return

                init_db(app)
                db_initialized = True
                print("INFO: Initialisation de la BDD réussie.", file=sys.stderr)
            except Exception as e:
                print(f"ERREUR BDD : Échec de l'initialisation ou de la connexion. {e}", file=sys.stderr)
                db_initialized = True

@app.before_request
def before_request():
    """S'assure que la base de données est initialisée avant chaque requête."""
    if not db_initialized:
        ensure_db_is_initialized()

result_queue = queue.Queue()

# --- POINTS D'ACCÈS HTTP (Identique) ---

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "database_connected": db_initialized,
        "message": "Chess FEN Generator API with WebSockets",
        "endpoints": {
            "/api/auth": "Blueprint pour l'authentification (Connexion/Inscription)",
            "/api/generate": "POST - Generate a chess position (HTTP)",
            "WebSocket": "Connect to start real-time game events"
        }
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    # Logique de génération FEN inchangée (HTTP)
    try:
        data = request.get_json() if request.is_json else {}
        
        target_min = data.get('target_min', 25)
        target_max = data.get('target_max', 100)
        max_attempts = data.get('max_attempts', 20000)
        
        def run_generation():
            try:
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
        thread.join(timeout=120)
        
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
    # Logique de statut inchangée
    try:
        from .chess_generator import STOCKFISH_PATH
        import platform
        
        exists = os.path.exists(STOCKFISH_PATH)
        
        return jsonify({
            "stockfish_available": exists,
            "stockfish_path": STOCKFISH_PATH,
            "platform": platform.system(),
            "db_host": DB_HOST if DB_HOST else "Non configuré",
            "db_initialized": db_initialized
        })
    except Exception as e:
        return jsonify({
            "stockfish_available": False,
            "error": str(e),
            "db_initialized": db_initialized
        })

# --- GESTION DES ÉVÉNEMENTS SOCKETIO (Temps Réel) ---

@socketio.on('connect')
def handle_connect():
    """Gère la connexion initiale d'un client WebSocket."""
    # Le 'request.sid' est l'ID de session unique pour SocketIO
    print(f"Client connecté: {request.sid}")
    
    # Tentative d'ajouter le joueur à la file d'attente
    MatchmakingManager.add_player(request.sid)

    # Vérifie si un match a été trouvé immédiatement
    game_id = MatchmakingManager.check_for_match(request.sid)
    
    if game_id:
        game = games[game_id]
        
        # Envoie l'événement à tous les joueurs de la salle
        socketio.emit('match_found', 
            {'game_id': game_id, 'fen': game.fen, 'color': game.get_player_color(request.sid)}, 
            room=game_id)
    else:
        # Envoie un message privé au client
        emit('status', {'message': 'En attente d\'un adversaire...'}, room=request.sid)


@socketio.on('move')
def handle_move(data):
    """Gère les mouvements de pièces reçus des clients."""
    game_id = data.get('game_id')
    move = data.get('move')
    
    if not game_id or game_id not in games:
        emit('error', {'message': 'Partie invalide.'})
        return
        
    game = games[game_id]
    player_color = game.get_player_color(request.sid)

    try:
        # Tente de faire le mouvement (logique dans socket_manager.py)
        new_fen, status = game.make_move(request.sid, move)
        
        # Envoie le nouveau FEN et le statut à TOUS les clients de cette partie (y compris celui qui a joué)
        socketio.emit('game_update', 
            {'fen': new_fen, 'last_move': move, 'status': status}, 
            room=game_id)
            
        # Si la partie est terminée (échec et mat, pat, etc.), on la retire de la mémoire
        if status not in ['running', 'check']:
            MatchmakingManager.remove_game(game_id)

    except ValueError as e:
        # Si le mouvement est invalide (pas au joueur de jouer, mouvement illégal)
        emit('error', {'message': str(e)})


@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion d'un client WebSocket."""
    print(f"Client déconnecté: {request.sid}")
    
    # 1. Retirer le joueur de la file d'attente si il y était
    MatchmakingManager.remove_player(request.sid)
    
    # 2. Gérer l'abandon d'une partie en cours
    game_id = MatchmakingManager.find_game_by_player_id(request.sid)
    if game_id and game_id in games:
        game = games[game_id]
        opponent_sid = game.get_opponent_id(request.sid)
        
        # Informe l'adversaire de l'abandon
        socketio.emit('opponent_left', 
            {'message': 'Votre adversaire a quitté la partie. Vous gagnez par abandon.'}, 
            room=opponent_sid)
            
        # Nettoie la partie
        MatchmakingManager.remove_game(game_id)


# --- POINT D'ENTRÉE PRINCIPAL (Utilise socketio.run) ---

if __name__ == '__main__':
    with app.app_context():
        ensure_db_is_initialized()
    # IMPORTANT: Utiliser socketio.run() au lieu de app.run()
    # pour démarrer le serveur SocketIO/WebSocket.
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

# Pour que Elastic Beanstalk (qui utilise WSGI) trouve votre application,
# le fichier doit contenir un objet `application`.
# Nous assignons l'objet Flask standard.
application = app
