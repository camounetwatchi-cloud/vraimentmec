from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
from datetime import timedelta, datetime
import chess

# Importer les modules du backend
from backend.db_models import db, init_db, create_tables
from backend.auth import auth_bp
from backend.chess_generator import generate_fen_position
from backend.socket_manager import MatchmakingManager, games

# Créer l'application Flask
app = Flask(__name__)

# ========================================
# CONFIGURATION
# ========================================

# Configuration de la base de données
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///chess_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuration de la session
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'votre-cle-secrete-super-securisee-changez-moi')
# --- MODIFICATION ---
# En production (avec HTTPS), SESSION_COOKIE_SECURE devrait être True
# Pour les tests locaux (http ou file://), False est OK.
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None' # Nécessaire pour les cookies cross-origin
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ========================================
# CONFIGURATION CORS (CORRIGÉE)
# ========================================

# --- MODIFICATION ---
# 1. Définir les origines autorisées.
#    "*" est INTERDIT avec "supports_credentials=True".
#    Nous devons lister explicitement toutes les origines autorisées.
allowed_origins = [
    "null",  # Pour les tests en local (file://...) - LA CORRECTION CLÉ
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    # L'URL de votre frontend déployé (ajoutez-la si elle est différente de l'API)
    "http://chessishard-env.eba-msuf2pqs.eu-west-1.elasticbeanstalk.com" 
]

# 2. Appliquer la configuration CORS
CORS(app,
     resources={
         r"/api/*": {
             "origins": allowed_origins, # Utiliser la liste sans "*"
             "supports_credentials": True, # C'est correct
             "allow_headers": ["Content-Type", "Authorization"], # C'est correct
             "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
             "expose_headers": ["Content-Type"]
         }
     })
# J'ai supprimé 'supports_credentials=True' à l'extérieur car il est déjà dans 'resources'

# ========================================
# INITIALISATION
# ========================================

# Initialiser la base de données
init_db(app)

# --- MODIFICATION ---
# Initialiser SocketIO avec la MÊME liste d'origines
socketio = SocketIO(app,
                    cors_allowed_origins=allowed_origins, # Utiliser la même liste
                    async_mode='threading', # Changé de 'gevent' à 'threading' pour compatibilité
                    logger=True,
                    engineio_logger=True)

# Créer les tables au démarrage
with app.app_context():
    create_tables(app)
    print("✅ Tables créées avec succès!")

# ========================================
# ENREGISTREMENT DES BLUEPRINTS
# ========================================

app.register_blueprint(auth_bp, url_prefix='/api/auth')

# ========================================
# ROUTES API REST
# ========================================

@app.route('/')
def home():
    """Page d'accueil de l'API"""
    return jsonify({
        'message': 'Bienvenue sur l\'API Chess Generator',
        'version': '1.0.0',
        'status': 'running',
        'endpoints': {
            'auth': '/api/auth/*',
            'generate': '/api/generate',
            'health': '/api/health'
        }
    })

@app.route('/api/health')
def health_check():
    """Endpoint de santé pour vérifier que l'API fonctionne"""
    try:
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'active_games': MatchmakingManager.get_active_games_count(),
            'waiting_players': MatchmakingManager.get_waiting_players_count(),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate_position():
    """Endpoint pour générer une position FEN d'échecs"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        
        target_min = data.get('target_min', 25)
        target_max = data.get('target_max', 100)
        max_attempts = data.get('max_attempts', 20000)
        
        # Validation des paramètres
        if target_min >= target_max:
            return jsonify({
                'success': False,
                'error': 'target_min doit être inférieur à target_max'
            }), 400
        
        if max_attempts < 1000 or max_attempts > 50000:
            return jsonify({
                'success': False,
                'error': 'max_attempts doit être entre 1000 et 50000'
            }), 400
        
        # Générer la position
        result = generate_fen_position(target_min, target_max, max_attempts)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        print(f"❌ Erreur lors de la génération: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ========================================
# ÉVÉNEMENTS SOCKETIO
# ========================================

@socketio.on('connect')
def handle_connect():
    """Gère la connexion d'un client WebSocket"""
    print(f"✅ Client connecté: {request.sid}")
    emit('connection_established', {'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion d'un client WebSocket"""
    print(f"❌ Client déconnecté: {request.sid}")
    
    MatchmakingManager.remove_player(request.sid)
    
    game_id = MatchmakingManager.find_game_by_player_id(request.sid)
    if game_id:
        game = games.get(game_id)
        if game:
            opponent_sid = game.get_opponent_id(request.sid)
            if opponent_sid:
                emit('opponent_disconnected', 
                     {'message': 'Votre adversaire s\'est déconnecté'},
                     room=opponent_sid)
        
        MatchmakingManager.handle_player_disconnect(request.sid, game_id)

@socketio.on('join_queue')
def handle_join_queue(data):
    """Gère l'ajout d'un joueur à la file d'attente"""
    try:
        user_id = data.get('user_id')
        username = data.get('username', 'Joueur')
        elo = data.get('elo', 1200)
        
        if not user_id:
            emit('error', {'message': 'user_id requis'})
            return
        
        MatchmakingManager.add_player(request.sid, user_id, username, elo)
        
        emit('queue_joined', {
            'message': 'Vous êtes dans la file d\'attente',
            'waiting_players': MatchmakingManager.get_waiting_players_count()
        })
        
        game_id = MatchmakingManager.check_for_match(request.sid)
        
        if game_id:
            game = games[game_id]
            
            for player_sid in game.players.keys():
                player_color = game.get_player_color(player_sid)
                opponent_sid = game.get_opponent_id(player_sid)
                opponent_info = game.get_player_info(opponent_sid)
                
                emit('game_start', {
                    'game_id': game_id,
                    'color': player_color,
                    'fen': game.fen,
                    'opponent': {
                        'username': opponent_info['username'],
                        'user_id': opponent_info['user_id']
                    },
                    'game_info': game.get_game_info()
                }, room=player_sid)
        
    except Exception as e:
        print(f"❌ Erreur dans join_queue: {e}")
        emit('error', {'message': 'Erreur lors de l\'ajout à la file d\'attente'})

@socketio.on('leave_queue')
def handle_leave_queue():
    """Gère le retrait d'un joueur de la file d'attente"""
    MatchmakingManager.remove_player(request.sid)
    emit('queue_left', {'message': 'Vous avez quitté la file d\'attente'})

@socketio.on('make_move')
def handle_make_move(data):
    """Gère un mouvement d'échecs"""
    try:
        game_id = data.get('game_id')
        move = data.get('move')
        
        if not game_id or not move:
            emit('error', {'message': 'game_id et move requis'})
            return
        
        game = games.get(game_id)
        if not game:
            emit('error', {'message': 'Partie introuvable'})
            return
        
        try:
            new_fen, status, info = game.make_move(request.sid, move)
            
            emit('move_made', {
                'fen': new_fen,
                'move': move,
                'status': status,
                'info': info
            }, room=game_id)
            
            if info.get('result'):
                MatchmakingManager.remove_game(game_id)
            
        except ValueError as e:
            emit('invalid_move', {'message': str(e)})
    
    except Exception as e:
        print(f"❌ Erreur dans make_move: {e}")
        emit('error', {'message': 'Erreur lors du mouvement'})

@socketio.on('resign')
def handle_resign(data):
    """Gère l'abandon d'une partie"""
    try:
        game_id = data.get('game_id')
        
        if not game_id:
            emit('error', {'message': 'game_id requis'})
            return
        
        game = games.get(game_id)
        if not game:
            emit('error', {'message': 'Partie introuvable'})
            return
        
        player_color = game.get_player_color_enum(request.sid)
        result = 'black_win' if player_color == chess.WHITE else 'white_win'
        
        game.save_to_database(result)
        
        emit('game_over', {
            'result': result,
            'reason': 'resignation'
        }, room=game_id)
        
        MatchmakingManager.remove_game(game_id)
        
    except Exception as e:
        print(f"❌ Erreur dans resign: {e}")
        emit('error', {'message': 'Erreur lors de l\'abandon'})

@socketio.on('offer_draw')
def handle_offer_draw(data):
    """Gère une proposition de nulle"""
    try:
        game_id = data.get('game_id')
        
        if not game_id:
            emit('error', {'message': 'game_id requis'})
            return
        
        game = games.get(game_id)
        if not game:
            emit('error', {'message': 'Partie introuvable'})
            return
        
        opponent_sid = game.get_opponent_id(request.sid)
        emit('draw_offered', {
            'message': 'Votre adversaire propose une nulle'
        }, room=opponent_sid)
        
    except Exception as e:
        print(f"❌ Erreur dans offer_draw: {e}")
        emit('error', {'message': 'Erreur lors de la proposition de nulle'})

@socketio.on('accept_draw')
def handle_accept_draw(data):
    """Gère l'acceptation d'une nulle"""
    try:
        game_id = data.get('game_id')
        
        if not game_id:
            emit('error', {'message': 'game_id requis'})
            return
        
        game = games.get(game_id)
        if not game:
            emit('error', {'message': 'Partie introuvable'})
            return
        
        game.save_to_database('draw')
        
        emit('game_over', {
            'result': 'draw',
            'reason': 'agreement'
        }, room=game_id)
        
        MatchmakingManager.remove_game(game_id)
        
    except Exception as e:
        print(f"❌ Erreur dans accept_draw: {e}")
        emit('error', {'message': 'Erreur lors de l\'acceptation de la nulle'})

# ========================================
# GESTION D'ERREURS
# ========================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint non trouvé'}), 404

@app.errorhandler(500)
def internal_error(error):
    print(f"❌ Erreur serveur: {error}")
    return jsonify({'error': 'Erreur interne du serveur'}), 500

# ========================================
# DÉMARRAGE DE L'APPLICATION
# ========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 Démarrage du serveur sur le port {port}...")
    
    # En développement
    socketio.run(app, 
                 host='0.0.0.0', 
                 port=port, 
                 debug=True,
                 use_reloader=True,
                 allow_unsafe_werkzeug=True)
