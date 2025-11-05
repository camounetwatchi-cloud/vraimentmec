from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import json
import random
from datetime import timedelta, datetime
from pathlib import Path
import chess
import uuid

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
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# ========================================
# CONFIGURATION CORS
# ========================================

is_production = os.environ.get('FLASK_ENV') == 'production'

print(f"🔧 Mode: {'Production' if is_production else 'Développement'}")

CORS(app, 
     resources={r"/*": {"origins": "*"}},
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

# ========================================
# INITIALISATION
# ========================================

init_db(app)

async_mode = 'gevent' if is_production else 'threading'

print(f"🔧 Mode async: {async_mode}")

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

try:
    with app.app_context():
        create_tables(app)
        print("✅ Tables créées avec succès!")
except Exception as e:
    print(f"⚠️ Avertissement lors de la création des tables: {e}")

# Charger les positions depuis le fichier JSON
POSITIONS_FILE = Path(__file__).parent / 'positions.json'
CACHED_POSITIONS = []

def load_positions():
    """Charge les positions depuis le fichier JSON"""
    global CACHED_POSITIONS
    try:
        if POSITIONS_FILE.exists():
            with open(POSITIONS_FILE, 'r', encoding='utf-8') as f:
                CACHED_POSITIONS = json.load(f)
                print(f"✅ {len(CACHED_POSITIONS)} positions chargées depuis positions.json")
        else:
            print("⚠️ Fichier positions.json introuvable")
            CACHED_POSITIONS = []
    except Exception as e:
        print(f"❌ Erreur chargement positions.json: {e}")
        CACHED_POSITIONS = []

# Charger les positions au démarrage
load_positions()

# ========================================
# ROUTES POUR SERVIR LES FICHIERS FRONTEND
# ========================================

@app.route('/auth')
@app.route('/auth.html')
def serve_auth():
    return send_from_directory('../frontend', 'auth.html')

@app.route('/game')
@app.route('/game.html')
def serve_game():
    return send_from_directory('../frontend', 'game.html')

@app.route('/generator')
@app.route('/generator.html')
def serve_generator():
    return send_from_directory('../frontend', 'generator.html')

@app.route('/index.html')
@app.route('/home')
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

@app.route('/style.css')
def serve_css():
    return send_from_directory('../frontend', 'style.css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('../frontend', 'script.js')

@app.route('/navbar.js')
def serve_navbar_js():
    return send_from_directory('../frontend', 'navbar.js')

@app.route('/navbar.css')
def serve_navbar_css():
    return send_from_directory('../frontend', 'navbar.css')

@app.route('/global.css')
def serve_global_css():
    return send_from_directory('../frontend', 'global.css')

# ========================================
# ENREGISTREMENT DES BLUEPRINTS
# ========================================

app.register_blueprint(auth_bp, url_prefix='/api/auth')

# ========================================
# ROUTES API REST
# ========================================

@app.route('/')
def home():
    return jsonify({
        'message': 'Bienvenue sur l\'API Chess Generator',
        'version': '1.0.0',
        'status': 'running',
        'mode': 'production' if is_production else 'development',
        'async_mode': socketio.async_mode,
        'cached_positions': len(CACHED_POSITIONS),
        'endpoints': {
            'auth': '/api/auth/*',
            'generate': '/api/generate',
            'random_position': '/api/random-position',
            'health': '/api/health',
            'frontend': {
                'auth': '/auth',
                'game': '/game',
                'generator': '/generator',
                'home': '/home'
            }
        }
    })

@app.route('/api/health')
def health_check():
    try:
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'active_games': MatchmakingManager.get_active_games_count(),
            'waiting_players': MatchmakingManager.get_waiting_players_count(),
            'async_mode': socketio.async_mode,
            'cached_positions': len(CACHED_POSITIONS),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@app.route('/api/random-position', methods=['GET', 'OPTIONS'])
def get_random_position():
    """Retourne une position aléatoire depuis le fichier JSON"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        if not CACHED_POSITIONS:
            return jsonify({
                'success': False,
                'error': 'Aucune position disponible dans le cache'
            }), 404
        
        # Sélectionner une position aléatoire
        position = random.choice(CACHED_POSITIONS)
        
        return jsonify({
            'success': True,
            'data': position
        })
        
    except Exception as e:
        print(f"❌ Erreur lors de la récupération d'une position aléatoire: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate', methods=['POST', 'OPTIONS'])
def generate_position():
    """Génère une nouvelle position avec Stockfish (pour la page generator)"""
    if request.method == 'OPTIONS':
        return '', 204
        
    try:
        data = request.get_json()
        
        # Récupérer les paramètres avec valeurs par défaut
        target_min = data.get('target_min', 25)
        target_max = data.get('target_max', 100)
        material_diff = data.get('material_diff', 3)
        max_material = data.get('max_material', 22)
        max_attempts = data.get('max_attempts', 20000)
        excluded_pieces = data.get('excluded_pieces', [])  # AJOUTER CETTE LIGNE
        
        # Validations
        if target_min < 0 or target_min > 99:
            return jsonify({
                'success': False,
                'error': 'target_min doit être entre 0 et 99'
            }), 400
        
        if target_max < 1 or target_max > 99:
            return jsonify({
                'success': False,
                'error': 'target_max doit être entre 1 et 99'
            }), 400
        
        if target_min >= target_max:
            return jsonify({
                'success': False,
                'error': 'target_min doit être inférieur à target_max'
            }), 400
        
        if material_diff < 0 or material_diff > 6:
            return jsonify({
                'success': False,
                'error': 'material_diff doit être entre 0 et 6'
            }), 400
        
        if max_material < 10 or max_material > 25:
            return jsonify({
                'success': False,
                'error': 'max_material doit être entre 10 et 25'
            }), 400
        
        if max_attempts < 1000 or max_attempts > 50000:
            return jsonify({
                'success': False,
                'error': 'max_attempts doit être entre 1000 et 50000'
            }), 400
        
        # Valider excluded_pieces
        if not isinstance(excluded_pieces, list):
            return jsonify({
                'success': False,
                'error': 'excluded_pieces doit être une liste'
            }), 400
        
        valid_pieces = ['queen', 'rook', 'bishop', 'knight', 'pawn']
        for piece in excluded_pieces:
            if piece not in valid_pieces:
                return jsonify({
                    'success': False,
                    'error': f'Pièce invalide: {piece}'
                }), 400
        
        # MODIFIER L'APPEL À LA FONCTION
        result = generate_fen_position(
            target_min, 
            target_max, 
            material_diff, 
            max_material, 
            max_attempts,
            excluded_pieces  # AJOUTER CE PARAMÈTRE
        )
        
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

@app.route('/api/reload-positions', methods=['POST', 'OPTIONS'])
def reload_positions():
    """Recharge les positions depuis le fichier JSON"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        load_positions()
        return jsonify({
            'success': True,
            'message': f'{len(CACHED_POSITIONS)} positions rechargées',
            'count': len(CACHED_POSITIONS)
        })
    except Exception as e:
        print(f"❌ Erreur lors du rechargement: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ========================================
# ÉVÉNEMENTS SOCKETIO
# ========================================

@socketio.on('connect')
def handle_connect():
    print(f"✅ Client connecté: {request.sid}")
    emit('connection_established', {'sid': request.sid, 'async_mode': socketio.async_mode})

@socketio.on('join_game')
def handle_join_game(data):
    """Permet aux joueurs de rejoindre une partie créée"""
    try:
        game_id = data.get('game_id')
        user_id = session.get('user_id')
        
        if not game_id or not user_id:
            emit('error', {'message': 'game_id et authentification requis'})
            return
        
        # Vérifier si la partie existe déjà
        if game_id in games:
            game = games[game_id]
            print(f"✅ Joueur {user_id} rejoint la partie existante {game_id}")
            join_room(game_id, sid=request.sid)
            
            emit('game_joined', {
                'game_id': game_id,
                'color': game.get_player_color(request.sid),
                'fen': game.fen,
                'opponent': {
                    'username': game.get_opponent_id(request.sid)
                }
            })
            return
        
        # Sinon, chercher dans les parties en attente
        if not hasattr(app, 'pending_games') or game_id not in app.pending_games:
            emit('error', {'message': 'Partie introuvable'})
            return
        
        game_info = app.pending_games[game_id]
        
        # Vérifier que l'utilisateur fait partie de cette partie
        if user_id not in [game_info['challenger_id'], game_info['accepter_id']]:
            emit('error', {'message': 'Vous ne faites pas partie de cette partie'})
            return
        
        # Enregistrer le SID pour cet utilisateur
        if 'sids' not in game_info:
            game_info['sids'] = {}
        
        game_info['sids'][user_id] = request.sid
        
        print(f"✅ {user_id} connecté avec SID {request.sid} pour la partie {game_id}")
        
        # Si les deux joueurs sont connectés, créer l'objet Game
        if len(game_info['sids']) == 2:
            from backend.socket_manager import Game
            
            challenger_sid = game_info['sids'][game_info['challenger_id']]
            accepter_sid = game_info['sids'][game_info['accepter_id']]
            
            game = Game.__new__(Game)
            game.game_id = game_id
            game.board = chess.Board(game_info['fen'])
            game.starting_fen = game_info['fen']
            game.moves_history = []
            game.started_at = game_info['created']
            
            # Ajout du time control
            tc = game_info.get('time_control', {'minutes': 5, 'increment': 0})
            game.time_control = tc
            game.white_time = tc['minutes'] * 60
            game.black_time = tc['minutes'] * 60
            game.increment = tc.get('increment', 0)
            game.last_move_time = game_info['created']
            
            from backend.db_models import User
            game.user1 = User.query.get(game_info['challenger_id'])
            game.user2 = User.query.get(game_info['accepter_id'])
            
            # Assigner les couleurs
            if game_info['challenger_color'] == 'white':
                game.players = {
                    challenger_sid: {
                        'color': chess.WHITE,
                        'user_id': game_info['challenger_id'],
                        'username': game_info['challenger_name']
                    },
                    accepter_sid: {
                        'color': chess.BLACK,
                        'user_id': game_info['accepter_id'],
                        'username': game_info['accepter_name']
                    }
                }
            else:
                game.players = {
                    challenger_sid: {
                        'color': chess.BLACK,
                        'user_id': game_info['challenger_id'],
                        'username': game_info['challenger_name']
                    },
                    accepter_sid: {
                        'color': chess.WHITE,
                        'user_id': game_info['accepter_id'],
                        'username': game_info['accepter_name']
                    }
                }
            
            join_room(game_id, sid=challenger_sid)
            join_room(game_id, sid=accepter_sid)
            
            games[game_id] = game
            del app.pending_games[game_id]
            
            print(f"✅ Partie {game_id} complètement initialisée avec les deux joueurs")
            
            # Envoyer game_start aux deux joueurs
            emit('game_start', {
                'white_time': game.white_time,
                'black_time': game.black_time,
                'time_control': game.time_control,
                'game_id': game_id,
                'color': game.get_player_color(challenger_sid),
                'fen': game.fen,
                'opponent': {
                    'username': game_info['accepter_name']
                }
            }, room=challenger_sid)
            
            emit('game_start', {
                'white_time': game.white_time,
                'black_time': game.black_time,
                'time_control': game.time_control,
                'game_id': game_id,
                'color': game.get_player_color(accepter_sid),
                'fen': game.fen,
                'opponent': {
                    'username': game_info['challenger_name']
                }
            }, room=accepter_sid)
        else:
            # Un seul joueur connecté, attendre l'autre
            emit('game_joined', {
                'game_id': game_id,
                'status': 'waiting_opponent'
            })
    
    except Exception as e:
        print(f"❌ Erreur dans join_game: {e}")
        import traceback
        traceback.print_exc()
        emit('error', {'message': 'Erreur lors de la connexion à la partie'})

@socketio.on('disconnect')
def handle_disconnect():
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

@socketio.on('make_move')
def handle_make_move(data):
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
    try:
        from backend.db_models import User
        
        online_players = User.query.filter_by(is_online=True).all()
        
        players_list = []
        for player in online_players:
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
        
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        print(f"✅ {user.username} est maintenant en ligne")
        
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

challenges = {}

@app.route('/api/challenges', methods=['GET'])
def get_challenges():
    try:
        now = datetime.utcnow()
        expired = []
        for challenge_id, challenge in challenges.items():
            if (now - challenge['created_at']).seconds > 300:
                expired.append(challenge_id)
        
        for challenge_id in expired:
            del challenges[challenge_id]
        
        challenges_list = []
        for challenge_id, challenge in challenges.items():
            challenges_list.append({
                'id': challenge_id,
                'challenger_id': challenge['challenger_id'],
                'challenger_name': challenge['challenger_name'],
                'challenger_elo': challenge['challenger_elo'],
                'fen': challenge['fen'],
                'time_control': challenge.get('time_control', {'minutes': 5, 'increment': 0}),
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
        
        data = request.get_json()
        fen = data.get('fen')
        time_control = data.get('time_control', {'minutes': 5, 'increment': 0})
        
        if not fen:
            return jsonify({
                'success': False,
                'error': 'FEN requis'
            }), 400
        
        challenge_id = str(uuid.uuid4())
        
        challenges[challenge_id] = {
            'id': challenge_id,
            'challenger_id': user_id,
            'challenger_name': user.username,
            'challenger_elo': user.elo_rating,
            'fen': fen,
            'time_control': time_control,
            'created_at': datetime.utcnow()
        }
        
        print(f"✅ Défi créé: {challenge_id} par {user.username} ({time_control['minutes']}+{time_control['increment']})")
        
        socketio.emit('new_challenge', {
            'challenge_id': challenge_id,
            'challenger_name': user.username,
            'time_control': time_control
        })
        
        return jsonify({
            'success': True,
            'challenge_id': challenge_id,
            'message': 'Défi créé avec succès'
        })
        
    except Exception as e:
        print(f"❌ Erreur create_challenge: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': 'Erreur serveur'
        }), 500

@app.route('/api/challenges/<challenge_id>/accept', methods=['POST'])
def accept_challenge(challenge_id):
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
        
        game_id = str(uuid.uuid4())
        
        print(f"✅ Défi accepté: {challenge_id}")
        print(f"   Challenger: {challenger.username}")
        print(f"   Accepteur: {user.username}")
        print(f"   Cadence: {challenge['time_control']['minutes']}+{challenge['time_control']['increment']}")
        
        del challenges[challenge_id]
        
        # Attribution aléatoire des couleurs
        colors = ['white', 'black']
        challenger_color = random.choice(colors)
        accepter_color = 'black' if challenger_color == 'white' else 'white'
        
        # Créer un mapping temporaire pour retrouver la partie
        game_info = {
            'game_id': game_id,
            'challenger_id': challenge['challenger_id'],
            'accepter_id': user_id,
            'challenger_color': challenger_color,
            'accepter_color': accepter_color,
            'fen': challenge['fen'],
            'time_control': challenge['time_control'],
            'challenger_name': challenger.username,
            'accepter_name': user.username,
            'created': datetime.utcnow()
        }
        
        # Stocker temporairement les infos de la partie
        if not hasattr(app, 'pending_games'):
            app.pending_games = {}
        app.pending_games[game_id] = game_info
        
        print(f"✅ Partie créée en attente: {game_id}")
        print(f"   {challenger.username} ({challenger_color}) vs {user.username} ({accepter_color})")
        print(f"   Cadence: {challenge['time_control']['minutes']}+{challenge['time_control']['increment']}")
        
        socketio.emit('challenge_accepted', {
            'challenge_id': challenge_id,
            'game_id': game_id,
            'challenger_id': challenge['challenger_id'],
            'accepter_id': user_id,
            'challenger_name': challenger.username,
            'accepter_name': user.username,
            'challenger_color': challenger_color,
            'accepter_color': accepter_color,
            'fen': challenge['fen'],
            'time_control': challenge['time_control']
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
        
        if challenge['challenger_id'] != user_id:
            return jsonify({
                'success': False,
                'error': 'Vous ne pouvez annuler que vos propres défis'
            }), 403
        
        del challenges[challenge_id]
        
        print(f"✅ Défi annulé: {challenge_id}")
        
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
