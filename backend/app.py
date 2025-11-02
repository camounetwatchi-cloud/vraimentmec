from flask import Flask, request, jsonify, session, send_from_directory
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
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# Configuration de la session
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'votre-cle-secrete-super-securisee-changez-moi')
app.config['SESSION_COOKIE_SECURE'] = False  # True en production HTTPS uniquement
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ========================================
# CONFIGURATION CORS - SIMPLIFIÉE ET FONCTIONNELLE
# ========================================

is_production = os.environ.get('FLASK_ENV') == 'production'

print(f"🔧 Mode: {'Production' if is_production else 'Développement'}")

# Configuration CORS simple et permissive pour le développement
CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# ========================================
# INITIALISATION
# ========================================

# Initialiser la base de données
init_db(app)

# Déterminer le mode async approprié
async_mode = 'gevent' if is_production else 'threading'

print(f"🔧 Mode async: {async_mode}")

# Initialiser SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=async_mode,
    logger=True,
    engineio_logger=False,
    ping_timeout=60,
    ping_interval=25,
    manage_session=False
)

# Créer les tables au démarrage
try:
    with app.app_context():
        create_tables(app)
        print("✅ Tables créées avec succès!")
except Exception as e:
    print(f"⚠️ Avertissement lors de la création des tables: {e}")

# ========================================
# ROUTES POUR SERVIR LES FICHIERS FRONTEND
# ========================================

@app.route('/auth')
@app.route('/auth.html')
def serve_auth():
    """Sert la page d'authentification"""
    return send_from_directory('../frontend', 'auth.html')

@app.route('/game')
@app.route('/game.html')
def serve_game():
    """Sert la page de jeu"""
    return send_from_directory('../frontend', 'game.html')

@app.route('/index.html')
@app.route('/home')
def serve_index():
    """Sert la page d'accueil"""
    return send_from_directory('../frontend', 'index.html')

@app.route('/style.css')
def serve_css():
    """Sert le CSS"""
    return send_from_directory('../frontend', 'style.css')

@app.route('/script.js')
def serve_js():
    """Sert le JavaScript"""
    return send_from_directory('../frontend', 'script.js')

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
        'mode': 'production' if is_production else 'development',
        'async_mode': socketio.async_mode,
        'endpoints': {
            'auth': '/api/auth/*',
            'generate': '/api/generate',
            'health': '/api/health',
            'frontend': {
                'auth': '/auth',
                'game': '/game',
                'home': '/home'
            }
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
            'async_mode': socketio.async_mode,
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
    emit('connection_established', {'sid': request.sid, 'async_mode': socketio.async_mode})

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
        emit('error', {'message': "Erreur lors de l'abandon"})

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
# ENDPOINTS POUR JOUEURS EN LIGNE
# ========================================

@app.route('/api/players/online', methods=['GET'])
def get_online_players():
    """Récupère la liste des joueurs connectés"""
    try:
        from backend.db_models import User
        
        # Récupérer tous les joueurs en ligne
        online_players = User.query.filter_by(is_online=True).all()
        
        players_list = []
        for player in online_players:
            # Vérifier si le joueur est dans une partie active
            in_game = False
            for game_id, game in games.items():
                if any(p['user_id'] == player.id for p in game.players.values()):
                    in_game = True
                    break
            
            players_list.append({
                'id': player.id,
                'username': player.username,
                'elo': player.elo_rating,
                'in_game': in_game,
                'games_played': player.games_played,
                'games_won': player.games_won
            })
        
        return jsonify({
            'success': True,
            'players': players_list,
            'count': len(players_list)
        })
        
    except Exception as e:
        print(f"❌ Erreur get_online_players: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


@app.route('/api/players/set-online', methods=['POST'])
def set_player_online():
    """Marque le joueur comme en ligne"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Non authentifié'
            }), 401
        
        from backend.db_models import User
        from datetime import datetime
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Utilisateur introuvable'
            }), 404
        
        # Mettre à jour le statut
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        print(f"✅ {user.username} est maintenant en ligne")
        
        # Notifier les autres joueurs via WebSocket (CORRIGÉ : sans broadcast=True)
        socketio.emit('player_online', {
            'user_id': user.id,
            'username': user.username,
            'elo': user.elo_rating
        })
        
        return jsonify({
            'success': True,
            'message': 'Statut mis à jour'
        })
        
    except Exception as e:
        print(f"❌ Erreur set_player_online: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


@app.route('/api/players/set-offline', methods=['POST'])
def set_player_offline():
    """Marque le joueur comme hors ligne"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Non authentifié'
            }), 401
        
        from backend.db_models import User
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Utilisateur introuvable'
            }), 404
        
        user.is_online = False
        db.session.commit()
        
        print(f"✅ {user.username} est maintenant hors ligne")
        
        # Notifier les autres joueurs via WebSocket (CORRIGÉ : sans broadcast=True)
        socketio.emit('player_offline', {
            'user_id': user.id,
            'username': user.username
        })
        
        return jsonify({
            'success': True,
            'message': 'Statut mis à jour'
        })
        
    except Exception as e:
        print(f"❌ Erreur set_player_offline: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


# ========================================
# ENDPOINTS POUR LES DÉFIS
# ========================================

# Structure pour stocker les défis
challenges = {}

@app.route('/api/challenges', methods=['GET'])
def get_challenges():
    """Récupère la liste des défis disponibles"""
    try:
        from datetime import datetime, timedelta
        
        # Nettoyer les défis expirés (plus de 5 minutes)
        now = datetime.utcnow()
        expired = []
        for challenge_id, challenge in challenges.items():
            if (now - challenge['created_at']).seconds > 300:
                expired.append(challenge_id)
        
        for challenge_id in expired:
            del challenges[challenge_id]
        
        # Retourner les défis actifs
        challenges_list = []
        for challenge_id, challenge in challenges.items():
            challenges_list.append({
                'id': challenge_id,
                'challenger_id': challenge['challenger_id'],
                'challenger_name': challenge['challenger_name'],
                'challenger_elo': challenge['challenger_elo'],
                'fen': challenge['fen'],
                'created_at': challenge['created_at'].isoformat()
            })
        
        return jsonify({
            'success': True,
            'challenges': challenges_list
        })
        
    except Exception as e:
        print(f"❌ Erreur get_challenges: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


@app.route('/api/challenges/create', methods=['POST'])
def create_challenge():
    """Crée un nouveau défi"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Non authentifié'
            }), 401
        
        from backend.db_models import User
        from datetime import datetime
        import uuid
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'error': 'Utilisateur introuvable'
            }), 404
        
        data = request.get_json()
        fen = data.get('fen', chess.STARTING_FEN)
        
        # Créer le défi
        challenge_id = str(uuid.uuid4())
        challenges[challenge_id] = {
            'challenger_id': user_id,
            'challenger_name': user.username,
            'challenger_elo': user.elo_rating,
            'fen': fen,
            'created_at': datetime.utcnow()
        }
        
        print(f"✅ Défi créé: {challenge_id} par {user.username}")
        
        # Notifier tous les joueurs via WebSocket (CORRIGÉ : sans broadcast=True)
        socketio.emit('new_challenge', {
            'challenge_id': challenge_id,
            'challenger_name': user.username,
            'challenger_elo': user.elo_rating
        })
        
        return jsonify({
            'success': True,
            'challenge_id': challenge_id,
            'message': 'Défi créé avec succès'
        })
        
    except Exception as e:
        print(f"❌ Erreur create_challenge: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


@app.route('/api/challenges/<challenge_id>/accept', methods=['POST'])
def accept_challenge(challenge_id):
    """Accepte un défi et notifie les joueurs"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Non authentifié'
            }), 401
        
        if challenge_id not in challenges:
            return jsonify({
                'success': False,
                'error': 'Défi introuvable ou expiré'
            }), 404
        
        challenge = challenges[challenge_id]
        
        # Vérifier qu'on n'accepte pas son propre défi
        if challenge['challenger_id'] == user_id:
            return jsonify({
                'success': False,
                'error': 'Vous ne pouvez pas accepter votre propre défi'
            }), 400
        
        from backend.db_models import User
        
        user = User.query.get(user_id)
        challenger = User.query.get(challenge['challenger_id'])
        
        if not user or not challenger:
            return jsonify({
                'success': False,
                'error': 'Utilisateur introuvable'
            }), 404
        
        # Générer un game_id unique
        import uuid
        game_id = str(uuid.uuid4())
        
        print(f"✅ Défi accepté: {challenge_id}")
        print(f"   Challenger: {challenger.username}")
        print(f"   Accepteur: {user.username}")
        print(f"   FEN: {challenge['fen']}")
        
        # Supprimer le défi de la liste
        del challenges[challenge_id]
        
        # Notifier les deux joueurs via WebSocket (CORRIGÉ : sans broadcast=True)
        socketio.emit('challenge_accepted', {
            'challenge_id': challenge_id,
            'game_id': game_id,
            'challenger_id': challenge['challenger_id'],
            'accepter_id': user_id,
            'challenger_name': challenger.username,
            'accepter_name': user.username,
            'fen': challenge['fen']
        })
        
        return jsonify({
            'success': True,
            'game_id': game_id,
            'challenge_id': challenge_id,
            'message': 'Défi accepté ! La partie va commencer...'
        })
        
    except Exception as e:
        print(f"❌ Erreur accept_challenge: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


@app.route('/api/challenges/<challenge_id>/cancel', methods=['DELETE'])
def cancel_challenge(challenge_id):
    """Annule un défi"""
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Non authentifié'
            }), 401
        
        if challenge_id not in challenges:
            return jsonify({
                'success': False,
                'error': 'Défi introuvable'
            }), 404
        
        challenge = challenges[challenge_id]
        
        # Vérifier que c'est bien le créateur du défi
        if challenge['challenger_id'] != user_id:
            return jsonify({
                'success': False,
                'error': 'Vous ne pouvez annuler que vos propres défis'
            }), 403
        
        # Supprimer le défi
        del challenges[challenge_id]
        
        print(f"✅ Défi annulé: {challenge_id}")
        
        # Notifier tous les joueurs (CORRIGÉ : sans broadcast=True)
        socketio.emit('challenge_cancelled', {
            'challenge_id': challenge_id
        })
        
        return jsonify({
            'success': True,
            'message': 'Défi annulé avec succès'
        })
        
    except Exception as e:
        print(f"❌ Erreur cancel_challenge: {e}")
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500


# ========================================
# DÉMARRAGE DE L'APPLICATION
# ========================================

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
