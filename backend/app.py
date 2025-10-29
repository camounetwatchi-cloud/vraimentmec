import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from .db_models import db, init_db, create_tables
from .auth import auth_bp
from .chess_generator import generate_fen_position
from .socket_manager import MatchmakingManager, games

# Créer l'application Flask
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///chess.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = False  # True en production avec HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialiser CORS
CORS(app, supports_credentials=True, origins=['http://localhost:3000', 'http://localhost:5000'])

# Initialiser la base de données
init_db(app)

# Initialiser SocketIO avec gevent
socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='gevent',
    logger=True,
    engineio_logger=True
)

# Créer les tables au démarrage
with app.app_context():
    create_tables(app)

# Enregistrer les blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')


# ============================================
# ROUTES API REST
# ============================================

@app.route('/')
def index():
    """Page d'accueil de l'API"""
    return jsonify({
        'message': 'Chess Game API',
        'version': '1.0.0',
        'endpoints': {
            'auth': '/api/auth/*',
            'generate': '/api/generate',
            'health': '/api/health'
        }
    })


@app.route('/api/health')
def health():
    """Endpoint de santé pour vérifier que l'API fonctionne"""
    return jsonify({
        'status': 'healthy',
        'database': 'connected',
        'socketio': 'ready'
    })


@app.route('/api/generate', methods=['POST'])
def generate_position():
    """
    Endpoint pour générer une position d'échecs avec déséquilibre matériel.
    
    Body JSON:
    {
        "target_min": 25,
        "target_max": 100,
        "max_attempts": 20000
    }
    """
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
        print(f"Erreur lors de la génération: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================
# ÉVÉNEMENTS SOCKETIO
# ============================================

@socketio.on('connect')
def handle_connect():
    """Gère la connexion d'un client WebSocket"""
    print(f"Client connecté: {request.sid}")
    emit('connected', {'sid': request.sid})


@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion d'un client WebSocket"""
    print(f"Client déconnecté: {request.sid}")
    
    # Retirer le joueur de la file d'attente
    MatchmakingManager.remove_player(request.sid)
    
    # Si le joueur était dans une partie, gérer l'abandon
    game_id = MatchmakingManager.find_game_by_player_id(request.sid)
    if game_id:
        game = games.get(game_id)
        if game:
            opponent_sid = game.get_opponent_id(request.sid)
            if opponent_sid:
                emit('opponent_disconnected', {
                    'message': 'Votre adversaire s\'est déconnecté'
                }, room=opponent_sid)
        
        MatchmakingManager.handle_player_disconnect(request.sid, game_id)


@socketio.on('join_queue')
def handle_join_queue(data):
    """
    Gère l'entrée d'un joueur dans la file d'attente.
    
    Data attendu:
    {
        "user_id": "string",
        "username": "string",
        "elo": 1200
    }
    """
    user_id = data.get('user_id')
    username = data.get('username', 'Anonymous')
    elo = data.get('elo', 1200)
    
    print(f"Joueur {username} rejoint la file d'attente")
    
    # Ajouter le joueur à la file d'attente
    MatchmakingManager.add_player(request.sid, user_id, username, elo)
    
    # Notifier le joueur
    emit('queue_joined', {
        'message': 'Vous êtes dans la file d\'attente',
        'waiting_players': MatchmakingManager.get_waiting_players_count()
    })
    
    # Chercher un match
    game_id = MatchmakingManager.check_for_match(request.sid)
    
    if game_id:
        game = games[game_id]
        
        # Notifier les deux joueurs que la partie commence
        for player_sid, player_data in game.players.items():
            player_color = 'white' if player_data['color'] == True else 'black'
            opponent_sid = game.get_opponent_id(player_sid)
            opponent_data = game.get_player_info(opponent_sid)
            
            emit('game_start', {
                'game_id': game_id,
                'fen': game.fen,
                'your_color': player_color,
                'opponent': {
                    'username': opponent_data['username'],
                    'user_id': opponent_data['user_id']
                },
                'starting_fen': game.starting_fen
            }, room=player_sid)
        
        print(f"Match trouvé ! Partie {game_id} créée")


@socketio.on('leave_queue')
def handle_leave_queue():
    """Gère la sortie d'un joueur de la file d'attente"""
    print(f"Joueur {request.sid} quitte la file d'attente")
    MatchmakingManager.remove_player(request.sid)
    
    emit('queue_left', {
        'message': 'Vous avez quitté la file d\'attente'
    })


@socketio.on('make_move')
def handle_make_move(data):
    """
    Gère un coup joué par un joueur.
    
    Data attendu:
    {
        "game_id": "string",
        "move": "e2e4" (format UCI)
    }
    """
    game_id = data.get('game_id')
    move_uci = data.get('move')
    
    if not game_id or not move_uci:
        emit('error', {'message': 'game_id et move sont requis'})
        return
    
    game = games.get(game_id)
    
    if not game:
        emit('error', {'message': 'Partie introuvable'})
        return
    
    try:
        # Effectuer le mouvement
        new_fen, status, info = game.make_move(request.sid, move_uci)
        
        # Notifier les deux joueurs du nouveau coup
        emit('move_made', {
            'fen': new_fen,
            'move': move_uci,
            'status': status,
            'moves_count': info['moves_count']
        }, room=game_id)
        
        # Si la partie est terminée
        if status in ['checkmate', 'stalemate', 'draw_insufficient', 'draw_75_moves', 'draw_repetition']:
            emit('game_over', {
                'status': status,
                'result': info.get('result'),
                'winner': info.get('winner'),
                'final_fen': new_fen
            }, room=game_id)
            
            # Supprimer la partie après un délai
            MatchmakingManager.remove_game(game_id)
            
    except ValueError as e:
        emit('error', {'message': str(e)})
    except Exception as e:
        print(f"Erreur lors du mouvement: {e}")
        emit('error', {'message': 'Erreur lors du mouvement'})


@socketio.on('resign')
def handle_resign(data):
    """
    Gère l'abandon d'un joueur.
    
    Data attendu:
    {
        "game_id": "string"
    }
    """
    game_id = data.get('game_id')
    
    if not game_id:
        emit('error', {'message': 'game_id requis'})
        return
    
    game = games.get(game_id)
    
    if not game:
        emit('error', {'message': 'Partie introuvable'})
        return
    
    # Déterminer le gagnant
    resigning_player = game.get_player_info(request.sid)
    if resigning_player:
        if resigning_player['color']:  # WHITE
            result = 'black_win'
        else:
            result = 'white_win'
        
        # Sauvegarder la partie
        game.save_to_database(result)
        
        # Notifier les joueurs
        emit('game_over', {
            'status': 'resignation',
            'result': result,
            'resigning_player': resigning_player['username']
        }, room=game_id)
        
        # Supprimer la partie
        MatchmakingManager.remove_game(game_id)


@socketio.on('request_draw')
def handle_request_draw(data):
    """
    Gère une demande de nulle.
    
    Data attendu:
    {
        "game_id": "string"
    }
    """
    game_id = data.get('game_id')
    
    if not game_id:
        emit('error', {'message': 'game_id requis'})
        return
    
    game = games.get(game_id)
    
    if not game:
        emit('error', {'message': 'Partie introuvable'})
        return
    
    # Notifier l'adversaire
    opponent_sid = game.get_opponent_id(request.sid)
    requesting_player = game.get_player_info(request.sid)
    
    emit('draw_offered', {
        'from_player': requesting_player['username']
    }, room=opponent_sid)


@socketio.on('accept_draw')
def handle_accept_draw(data):
    """
    Gère l'acceptation d'une nulle.
    
    Data attendu:
    {
        "game_id": "string"
    }
    """
    game_id = data.get('game_id')
    
    if not game_id:
        emit('error', {'message': 'game_id requis'})
        return
    
    game = games.get(game_id)
    
    if not game:
        emit('error', {'message': 'Partie introuvable'})
        return
    
    # Sauvegarder la partie comme nulle
    game.save_to_database('draw')
    
    # Notifier les joueurs
    emit('game_over', {
        'status': 'draw_agreement',
        'result': 'draw'
    }, room=game_id)
    
    # Supprimer la partie
    MatchmakingManager.remove_game(game_id)


@socketio.on('decline_draw')
def handle_decline_draw(data):
    """
    Gère le refus d'une nulle.
    
    Data attendu:
    {
        "game_id": "string"
    }
    """
    game_id = data.get('game_id')
    
    if not game_id:
        emit('error', {'message': 'game_id requis'})
        return
    
    game = games.get(game_id)
    
    if not game:
        emit('error', {'message': 'Partie introuvable'})
        return
    
    # Notifier l'adversaire
    opponent_sid = game.get_opponent_id(request.sid)
    
    emit('draw_declined', {
        'message': 'Votre adversaire a refusé la nulle'
    }, room=opponent_sid)


# ============================================
# POINT D'ENTRÉE
# ============================================

if __name__ == '__main__':
    # Lancer le serveur en mode développement
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
