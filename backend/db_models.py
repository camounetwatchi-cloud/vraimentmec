from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

class User(db.Model):
    """Modèle utilisateur avec authentification"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    elo_rating = db.Column(db.Integer, default=1200)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_online = db.Column(db.Boolean, default=False)
    
    # Relations
    games_as_white = db.relationship('GameHistory', foreign_keys='GameHistory.white_player_id', backref='white_player')
    games_as_black = db.relationship('GameHistory', foreign_keys='GameHistory.black_player_id', backref='black_player')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class GameHistory(db.Model):
    """Historique des parties jouées"""
    __tablename__ = 'game_history'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    white_player_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    black_player_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    starting_fen = db.Column(db.String(255), nullable=False)
    final_fen = db.Column(db.String(255))
    moves = db.Column(db.Text)  # Format PGN ou JSON des coups
    result = db.Column(db.String(20))  # 'white_win', 'black_win', 'draw', 'abandoned'
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
