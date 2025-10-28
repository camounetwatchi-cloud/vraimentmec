# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, session
from flask_cors import CORS
# L'importation de SQLAlchemy est supprimée d'ici, car db_models.py s'en charge
from flask_socketio import SocketIO, emit, join_room, leave_room
import threading
import queue
import os
import sys

# Importez la logique de gestion des événements et des salles
# 'db' et 'init_db' viennent maintenant de db_models.py
from .db_models import db, init_db
from .chess_generator import generate_fen_position
from .socket_manager import Game, MatchmakingManager, games
from .auth import auth_bp # Import du blueprint d'authentification

# --- CONFIGURATION INITIALE ---
app = Flask(__name__)

# --- CONFIGURATION DE SESSIONS ET BLUEPRINT D'AUTHENTIFICATION ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = False  # Mettre à True en production avec HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Enregistrer le blueprint d'authentification
app.register_blueprint(auth_bp, url_prefix='/api/auth')
# ---------------------------------------------------------------------------------

# Activez CORS
CORS(app, resources={r"/*": {"origins": "*"}}) 

# Configurez Flask-SocketIO
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

# La configuration de la BDD doit se faire avant son initialisation
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

                # 1. Initialise l'objet 'db' avec l'application
                init_db(app)
                
                # 2. (MODIFICATION) Crée les tables (User, GameHistory) si elles n'existent pas
                # Nécessite le contexte de l'application pour fonctionner
                with app.app_context():
                    db.create_all()
                    
                db_initialized = True
                print("INFO: Initialisation de la BDD et création des tables réussies.", file=sys.stderr)
            except Exception as e:
                print(f"ERREUR BDD : Échec de l'initialisation ou de la connexion. {e}", file=sys.stderr)
                db_initialized = True

@app.before_request
def before_request():
    """S'assure que la base de données est initialisée avant chaque requête."""
    if not db_initialized:
        ensure_db_is_initialized()

result_queue = queue.Queue()

# --- POINTS D'ACCÈS HTTP ---

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
    print(f"Client connecté: {request.sid}")
    
    # NOTE: Ceci doit être mis à jour pour utiliser l'authentification (session['user_id'])
    # Pour l'instant, on utilise des placeholders
    user_id_placeholder = session.get('user_id', request.sid) # Utilise le user_id ou le sid
    username_placeholder = session.get('username', 'Visiteur')
    
    # Tentative d'ajouter le joueur à la file d'attente
    MatchmakingManager.add_player(request.sid, user_id_placeholder, username_placeholder)

    # Vérifie si un match a été trouvé immédiatement
    game_id = MatchmakingManager.check_for_match(request.sid)
    
    if game_id:
        game = games[game_id]
        
        # Info de la partie pour les deux joueurs
        game_info = game.get_game_info()
        
        # Envoie l'événement à tous les joueurs de la salle
        for sid in game.players:
            socketio.emit('match_found', 
                {
                    'game_info': game_info,
                    'color': game.get_player_color(sid) # Couleur spécifique à ce joueur
                }, 
                room=sid) # Envoie en privé à chaque joueur
    else:
        # Envoie un message privé au client
        emit('status', {'message': 'En attente d\'un adversaire...'}, room=request.sid)


@socketio.on('move')
def handle_move(data):
    """Gère les mouvements de pièces reçus des clients."""
    game_id = data.get('game_id')
    uci_move = data.get('move') # Renommé en uci_move pour plus de clarté
    
    if not game_id or game_id not in games:
        emit('error', {'message': 'Partie invalide.'})
        return
        
    game = games[game_id]
    
    # Vérifier si le joueur est authentifié pour ce mouvement (sécurité)
    if request.sid not in game.players:
        emit('error', {'message': 'Vous n\'êtes pas joueur dans cette partie.'})
        return

    try:
        # Tente de faire le mouvement
        new_fen, status, move_info = game.make_move(request.sid, uci_move)
        
        # Envoie le nouveau FEN et le statut à TOUS les clients de cette partie
        socketio.emit('game_update', 
            {
                'fen': new_fen, 
                'last_move': uci_move, 
                'status': status,
                'move_info': move_info # Contient le résultat, etc.
            }, 
            room=game_id)
            
        # Si la partie est terminée, on la retire de la mémoire (après un délai?)
        if move_info.get('result'): # Si un résultat est défini
            MatchmakingManager.remove_game(game_id)

    except ValueError as e:
        # Si le mouvement est invalide (pas au joueur de jouer, mouvement illégal)
        emit('error', {'message': str(e)})


@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion d'un client WebSocket."""
    print(f"Client déconnecté: {request.sid}")
    
    # 1. Retirer le joueur de la file d'attente (gère aussi l'abandon)
    MatchmakingManager.remove_player(request.sid)
    
    # 2. Gérer l'abandon (c'est maintenant géré dans remove_player -> handle_player_disconnect)
    game_id = Matchror.find_game_by_player_id(request.sid)
    if game_id and game_id in games:
        game = games[game_id]
        opponent_sid = game.get_opponent_id(request.sid)
        
        # Informe l'adversaire de l'abandon
        if opponent_sid:
            socketio.emit('opponent_left', 
                {'message': 'Votre adversaire a quitté la partie. Vous gagnez par abandon.'}, 
                room=opponent_sid)
            
        # Nettoie la partie (maintenant géré par remove_player)
        # MatchmakingManager.remove_game(game_id)


# --- POINT D'ENTRÉE PRINCIPAL ---

if __name__ == '__main__':
    # Initialise la BDD et crée les tables au démarrage
    with app.app_context():
        ensure_db_is_initialized()
        
    # IMPORTANT: Utiliser socketio.run()
    print("Démarrage du serveur SocketIO sur http://0.0.0.0:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)

# Pour que Elastic Beanstalk (qui utilise WSGI) trouve votre application
application = app
