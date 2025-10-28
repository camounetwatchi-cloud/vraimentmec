from flask import Blueprint, request, jsonify, session
from .db_models import db, User
import re

auth_bp = Blueprint('auth', __name__)

def is_valid_email(email):
    return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    # Validations
    if not username or len(username) < 3:
        return jsonify({'success': False, 'error': 'Username trop court (min 3 caractères)'}), 400
    
    if not is_valid_email(email):
        return jsonify({'success': False, 'error': 'Email invalide'}), 400
    
    if len(password) < 6:
        return jsonify({'success': False, 'error': 'Mot de passe trop court (min 6 caractères)'}), 400
    
    # Vérifier si l'utilisateur existe
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'error': 'Username déjà pris'}), 409
    
    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'error': 'Email déjà utilisé'}), 409
    
    # Créer l'utilisateur
    user = User(username=username, email=email)
    user.set_password(password)
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'elo': user.elo_rating
        }
    }), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username_or_email = data.get('username', '').strip()
    password = data.get('password', '')
    
    # Chercher par username ou email
    user = User.query.filter(
        (User.username == username_or_email) | (User.email == username_or_email.lower())
    ).first()
    
    if not user or not user.check_password(password):
        return jsonify({'success': False, 'error': 'Identifiants incorrects'}), 401
    
    # Mettre à jour le statut
    user.last_login = datetime.utcnow()
    user.is_online = True
    db.session.commit()
    
    # Créer la session
    session['user_id'] = user.id
    session['username'] = user.username
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'elo': user.elo_rating,
            'games_played': user.games_played,
            'games_won': user.games_won
        }
    }), 200

@auth_bp.route('/logout', methods=['POST'])
def logout():
    user_id = session.get('user_id')
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.is_online = False
            db.session.commit()
    
    session.clear()
    return jsonify({'success': True}), 200

@auth_bp.route('/me', methods=['GET'])
def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Non authentifié'}), 401
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'Utilisateur introuvable'}), 404
    
    return jsonify({
        'success': True,
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'elo': user.elo_rating,
            'games_played': user.games_played,
            'games_won': user.games_won,
            'is_online': user.is_online
        }
    }), 200
