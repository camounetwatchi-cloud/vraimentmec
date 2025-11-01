from flask import Blueprint, request, jsonify, session
from .db_models import db, User
import re
from datetime import datetime
import uuid

auth_bp = Blueprint('auth', __name__)

def is_valid_email(email):
    """Valide le format d'un email."""
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

def is_valid_username(username):
    """Valide le format d'un username (alphanumérique et underscores)."""
    return re.match(r'^[a-zA-Z0-9_]{3,20}$', username)

@auth_bp.route('/guest', methods=['POST', 'OPTIONS'])
def guest_login():
    """
    Endpoint pour se connecter en tant qu'invité.
    Crée un utilisateur temporaire avec un nom aléatoire.
    """
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Générer un nom d'invité unique
        guest_username = f"Guest_{uuid.uuid4().hex[:8]}"
        guest_email = f"{guest_username.lower()}@guest.local"
        guest_password = uuid.uuid4().hex
        
        # Créer l'utilisateur invité
        user = User(username=guest_username, email=guest_email)
        user.set_password(guest_password)
        
        db.session.add(user)
        db.session.commit()
        
        # Créer la session
        session['user_id'] = user.id
        session['username'] = user.username
        session['elo'] = user.elo_rating
        session['is_guest'] = True
        session.permanent = True
        
        print(f"✅ Invité créé: {guest_username}")
        
        return jsonify({
            'success': True,
            'message': 'Connexion en tant qu\'invité réussie',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'elo': user.elo_rating,
                'games_played': user.games_played,
                'games_won': user.games_won,
                'is_guest': True
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de la création de l'invité: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur lors de la création de l\'invité'
        }), 500


@auth_bp.route('/register', methods=['POST', 'OPTIONS'])
def register():
    """Endpoint d'inscription d'un nouvel utilisateur"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Aucune donnée fournie'}), 400
        
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Validations
        if not username:
            return jsonify({'success': False, 'error': 'Username requis'}), 400
            
        if not is_valid_username(username):
            return jsonify({
                'success': False, 
                'error': 'Username invalide (3-20 caractères, lettres, chiffres et underscore uniquement)'
            }), 400
        
        if not email:
            return jsonify({'success': False, 'error': 'Email requis'}), 400
            
        if not is_valid_email(email):
            return jsonify({'success': False, 'error': 'Email invalide'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'Mot de passe requis'}), 400
            
        if len(password) < 6:
            return jsonify({
                'success': False, 
                'error': 'Mot de passe trop court (minimum 6 caractères)'
            }), 400
        
        if len(password) > 128:
            return jsonify({
                'success': False, 
                'error': 'Mot de passe trop long (maximum 128 caractères)'
            }), 400
        
        # Vérifier si l'utilisateur existe déjà
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({
                'success': False, 
                'error': 'Ce username est déjà pris'
            }), 409
        
        existing_email = User.query.filter_by(email=email).first()
        if existing_email:
            return jsonify({
                'success': False, 
                'error': 'Cet email est déjà utilisé'
            }), 409
        
        # Créer l'utilisateur
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        # Créer la session automatiquement après inscription
        session['user_id'] = user.id
        session['username'] = user.username
        session['elo'] = user.elo_rating
        session['is_guest'] = False
        session.permanent = True
        
        print(f"✅ Nouvel utilisateur créé: {username}")
        
        return jsonify({
            'success': True,
            'message': 'Inscription réussie',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'elo': user.elo_rating,
                'games_played': user.games_played,
                'games_won': user.games_won,
                'is_guest': False
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de l'inscription: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur lors de l\'inscription'
        }), 500


@auth_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    """Endpoint de connexion"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Aucune donnée fournie'}), 400
        
        username_or_email = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username_or_email:
            return jsonify({'success': False, 'error': 'Username ou email requis'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'Mot de passe requis'}), 400
        
        # Chercher l'utilisateur par username ou email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email.lower())
        ).first()
        
        if not user:
            return jsonify({
                'success': False, 
                'error': 'Identifiants incorrects'
            }), 401
        
        if not user.check_password(password):
            return jsonify({
                'success': False, 
                'error': 'Identifiants incorrects'
            }), 401
        
        # Mettre à jour le statut de l'utilisateur
        user.last_login = datetime.utcnow()
        user.is_online = True
        db.session.commit()
        
        # Créer la session
        session['user_id'] = user.id
        session['username'] = user.username
        session['elo'] = user.elo_rating
        session['is_guest'] = False
        session.permanent = True
        
        print(f"✅ Connexion réussie: {user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Connexion réussie',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'elo': user.elo_rating,
                'games_played': user.games_played,
                'games_won': user.games_won,
                'is_online': user.is_online,
                'is_guest': False,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de la connexion: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur lors de la connexion'
        }), 500


@auth_bp.route('/logout', methods=['POST', 'OPTIONS'])
def logout():
    """Endpoint de déconnexion"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = session.get('user_id')
        is_guest = session.get('is_guest', False)
        
        if user_id:
            user = User.query.get(user_id)
            if user:
                user.is_online = False
                
                # Supprimer les comptes invités après déconnexion
                if is_guest:
                    db.session.delete(user)
                    print(f"✅ Compte invité supprimé: {user.username}")
                else:
                    print(f"✅ Déconnexion: {user.username}")
                
                db.session.commit()
        
        # Nettoyer la session
        session.clear()
        
        return jsonify({
            'success': True,
            'message': 'Déconnexion réussie'
        }), 200
        
    except Exception as e:
        print(f"❌ Erreur lors de la déconnexion: {e}")
        session.clear()
        return jsonify({
            'success': True,
            'message': 'Déconnexion réussie'
        }), 200


@auth_bp.route('/me', methods=['GET', 'OPTIONS'])
def get_current_user():
    """Endpoint pour récupérer les informations de l'utilisateur connecté"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False, 
                'error': 'Non authentifié'
            }), 401
        
        user = User.query.get(user_id)
        
        if not user:
            session.clear()
            return jsonify({
                'success': False, 
                'error': 'Utilisateur introuvable'
            }), 404
        
        is_guest = session.get('is_guest', False)
        
        return jsonify({
            'success': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'elo': user.elo_rating,
                'games_played': user.games_played,
                'games_won': user.games_won,
                'is_online': user.is_online,
                'is_guest': is_guest,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Erreur lors de la récupération de l'utilisateur: {e}")
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur'
        }), 500


@auth_bp.route('/check', methods=['GET', 'OPTIONS'])
def check_auth():
    """Endpoint simple pour vérifier si l'utilisateur est connecté"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    user_id = session.get('user_id')
    return jsonify({
        'authenticated': user_id is not None,
        'user_id': user_id,
        'is_guest': session.get('is_guest', False)
    }), 200


@auth_bp.route('/stats', methods=['GET', 'OPTIONS'])
def get_user_stats():
    """Endpoint pour récupérer les statistiques détaillées de l'utilisateur"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = session.get('user_id')
        
        if not user_id:
            return jsonify({
                'success': False, 
                'error': 'Non authentifié'
            }), 401
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False, 
                'error': 'Utilisateur introuvable'
            }), 404
        
        win_rate = (user.games_won / user.games_played * 100) if user.games_played > 0 else 0
        
        return jsonify({
            'success': True,
            'stats': {
                'username': user.username,
                'elo': user.elo_rating,
                'games_played': user.games_played,
                'games_won': user.games_won,
                'games_lost': user.games_played - user.games_won,
                'win_rate': round(win_rate, 2),
                'is_guest': session.get('is_guest', False),
                'member_since': user.created_at.isoformat() if user.created_at else None
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des stats: {e}")
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur'
        }), 500


@auth_bp.route('/update-profile', methods=['PUT', 'OPTIONS'])
def update_profile():
    """Endpoint pour mettre à jour le profil utilisateur"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = session.get('user_id')
        is_guest = session.get('is_guest', False)
        
        if not user_id:
            return jsonify({
                'success': False, 
                'error': 'Non authentifié'
            }), 401
        
        if is_guest:
            return jsonify({
                'success': False, 
                'error': 'Les invités ne peuvent pas modifier leur profil'
            }), 403
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False, 
                'error': 'Utilisateur introuvable'
            }), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Aucune donnée fournie'}), 400
        
        # Mise à jour de l'email
        new_email = data.get('email', '').strip().lower()
        if new_email and new_email != user.email:
            if not is_valid_email(new_email):
                return jsonify({'success': False, 'error': 'Email invalide'}), 400
            
            existing = User.query.filter_by(email=new_email).first()
            if existing and existing.id != user_id:
                return jsonify({
                    'success': False, 
                    'error': 'Cet email est déjà utilisé'
                }), 409
            
            user.email = new_email
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Profil mis à jour',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'elo': user.elo_rating
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de la mise à jour du profil: {e}")
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur'
        }), 500


@auth_bp.route('/change-password', methods=['PUT', 'OPTIONS'])
def change_password():
    """Endpoint pour changer le mot de passe"""
    # Gérer les requêtes OPTIONS pour CORS
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = session.get('user_id')
        is_guest = session.get('is_guest', False)
        
        if not user_id:
            return jsonify({
                'success': False, 
                'error': 'Non authentifié'
            }), 401
        
        if is_guest:
            return jsonify({
                'success': False, 
                'error': 'Les invités ne peuvent pas changer leur mot de passe'
            }), 403
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({
                'success': False, 
                'error': 'Utilisateur introuvable'
            }), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Aucune donnée fournie'}), 400
        
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({
                'success': False, 
                'error': 'Mots de passe requis'
            }), 400
        
        if not user.check_password(current_password):
            return jsonify({
                'success': False, 
                'error': 'Mot de passe actuel incorrect'
            }), 401
        
        if len(new_password) < 6:
            return jsonify({
                'success': False, 
                'error': 'Le nouveau mot de passe doit contenir au moins 6 caractères'
            }), 400
        
        if len(new_password) > 128:
            return jsonify({
                'success': False, 
                'error': 'Le nouveau mot de passe est trop long'
            }), 400
        
        user.set_password(new_password)
        db.session.commit()
        
        print(f"✅ Mot de passe changé pour: {user.username}")
        
        return jsonify({
            'success': True,
            'message': 'Mot de passe mis à jour avec succès'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors du changement de mot de passe: {e}")
        return jsonify({
            'success': False, 
            'error': 'Erreur serveur'
        }), 500
