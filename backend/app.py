from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
from flask_sqlalchemy import SQLAlchemy

# Déclarer l'objet 'db' (sans l'initialiser tout de suite)
db = SQLAlchemy()

def init_db(app):
    """
    Initialise l'objet db avec l'application Flask.
    Cette fonction sera appelée depuis app.py pour finaliser l'initialisation.
    """
    db.init_app(app)


class User(db.Model):
    """
    Modèle utilisateur avec authentification et statistiques de jeu.
    """
    __tablename__ = 'users'
    
    # Identifiants
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Statistiques de jeu
    elo_rating = db.Column(db.Integer, default=1200, nullable=False)
    games_played = db.Column(db.Integer, default=0, nullable=False)
    games_won = db.Column(db.Integer, default=0, nullable=False)
    games_drawn = db.Column(db.Integer, default=0, nullable=False)
    
    # Horodatages
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)
    
    # Statut
    is_online = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relations
    games_as_white = db.relationship(
        'GameHistory', 
        foreign_keys='GameHistory.white_player_id', 
        backref='white_player',
        lazy='dynamic'
    )
    games_as_black = db.relationship(
        'GameHistory', 
        foreign_keys='GameHistory.black_player_id', 
        backref='black_player',
        lazy='dynamic'
    )
    
    def set_password(self, password):
        """
        Hash et stocke le mot de passe de manière sécurisée.
        
        Args:
            password: Mot de passe en clair
        """
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """
        Vérifie si le mot de passe fourni correspond au hash stocké.
        
        Args:
            password: Mot de passe en clair à vérifier
            
        Returns:
            bool: True si le mot de passe est correct
        """
        return check_password_hash(self.password_hash, password)
    
    def get_win_rate(self):
        """
        Calcule le taux de victoire de l'utilisateur.
        
        Returns:
            float: Pourcentage de victoires (0-100)
        """
        if self.games_played == 0:
            return 0.0
        return round((self.games_won / self.games_played) * 100, 2)
    
    def get_loss_count(self):
        """
        Calcule le nombre de défaites.
        
        Returns:
            int: Nombre de parties perdues
        """
        return self.games_played - self.games_won - self.games_drawn
    
    def update_stats(self, result):
        """
        Met à jour les statistiques après une partie.
        
        Args:
            result: 'win', 'loss', ou 'draw'
        """
        self.games_played += 1
        
        if result == 'win':
            self.games_won += 1
        elif result == 'draw':
            self.games_drawn += 1
    
    def to_dict(self, include_email=False):
        """
        Convertit l'utilisateur en dictionnaire.
        
        Args:
            include_email: Si True, inclut l'email (données sensibles)
            
        Returns:
            dict: Représentation de l'utilisateur
        """
        data = {
            'id': self.id,
            'username': self.username,
            'elo': self.elo_rating,
            'games_played': self.games_played,
            'games_won': self.games_won,
            'games_drawn': self.games_drawn,
            'games_lost': self.get_loss_count(),
            'win_rate': self.get_win_rate(),
            'is_online': self.is_online,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        
        if include_email:
            data['email'] = self.email
        
        return data
    
    def __repr__(self):
        return f'<User {self.username} (ELO: {self.elo_rating})>'


class GameHistory(db.Model):
    """
    Modèle pour l'historique des parties jouées.
    """
    __tablename__ = 'game_history'
    
    # Identifiant
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Joueurs
    white_player_id = db.Column(
        db.String(36), 
        db.ForeignKey('users.id'), 
        nullable=False,
        index=True
    )
    black_player_id = db.Column(
        db.String(36), 
        db.ForeignKey('users.id'), 
        nullable=False,
        index=True
    )
    
    # Données de la partie
    starting_fen = db.Column(db.String(255), nullable=False)
    final_fen = db.Column(db.String(255))
    moves = db.Column(db.Text)  # Coups au format UCI séparés par des espaces
    
    # Résultat
    result = db.Column(db.String(20), nullable=False, index=True)
    # Valeurs possibles: 'white_win', 'black_win', 'draw', 'abandoned'
    
    # Horodatages
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    ended_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
    
    def get_winner_id(self):
        """
        Retourne l'ID du gagnant.
        
        Returns:
            str or None: ID du gagnant, ou None en cas de nulle/abandon
        """
        if self.result == 'white_win':
            return self.white_player_id
        elif self.result == 'black_win':
            return self.black_player_id
        return None
    
    def get_loser_id(self):
        """
        Retourne l'ID du perdant.
        
        Returns:
            str or None: ID du perdant, ou None en cas de nulle/abandon
        """
        if self.result == 'white_win':
            return self.black_player_id
        elif self.result == 'black_win':
            return self.white_player_id
        return None
    
    def get_moves_list(self):
        """
        Retourne la liste des coups.
        
        Returns:
            list: Liste des coups au format UCI
        """
        if not self.moves:
            return []
        return self.moves.split()
    
    def get_move_count(self):
        """
        Retourne le nombre de coups joués.
        
        Returns:
            int: Nombre de coups
        """
        return len(self.get_moves_list())
    
    def to_dict(self):
        """
        Convertit la partie en dictionnaire.
        
        Returns:
            dict: Représentation de la partie
        """
        return {
            'id': self.id,
            'white_player': {
                'id': self.white_player_id,
                'username': self.white_player.username if self.white_player else None
            },
            'black_player': {
                'id': self.black_player_id,
                'username': self.black_player.username if self.black_player else None
            },
            'starting_fen': self.starting_fen,
            'final_fen': self.final_fen,
            'moves': self.get_moves_list(),
            'move_count': self.get_move_count(),
            'result': self.result,
            'winner_id': self.get_winner_id(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
            'duration_seconds': self.duration_seconds
        }
    
    def __repr__(self):
        white_name = self.white_player.username if self.white_player else 'Unknown'
        black_name = self.black_player.username if self.black_player else 'Unknown'
        return f'<Game {white_name} vs {black_name} ({self.result})>'


# Fonction utilitaire pour créer toutes les tables
def create_tables(app):
    """
    Crée toutes les tables dans la base de données.
    À appeler au démarrage de l'application.
    
    Args:
        app: Instance de l'application Flask
    """
    with app.app_context():
        db.create_all()
        print("Tables de base de données créées avec succès!")


# Fonction utilitaire pour supprimer toutes les tables (DANGER!)
def drop_tables(app):
    """
    Supprime toutes les tables de la base de données.
    ATTENTION: Cette opération est irréversible!
    
    Args:
        app: Instance de l'application Flask
    """
    with app.app_context():
        db.drop_all()
        print("Toutes les tables ont été supprimées!")


# Fonction utilitaire pour obtenir des statistiques globales
def get_global_stats():
    """
    Récupère les statistiques globales de la plateforme.
    
    Returns:
        dict: Statistiques globales
    """
    total_users = User.query.count()
    total_games = GameHistory.query.count()
    online_users = User.query.filter_by(is_online=True).count()
    
    return {
        'total_users': total_users,
        'total_games': total_games,
        'online_users': online_users
    }


# Fonction utilitaire pour obtenir le classement
def get_leaderboard(limit=10):
    """
    Récupère le classement des meilleurs joueurs.
    
    Args:
        limit: Nombre de joueurs à retourner
        
    Returns:
        list: Liste des meilleurs joueurs
    """
    top_players = User.query.order_by(User.elo_rating.desc()).limit(limit).all()
    
    leaderboard = []
    for rank, player in enumerate(top_players, start=1):
        leaderboard.append({
            'rank': rank,
            'username': player.username,
            'elo': player.elo_rating,
            'games_played': player.games_played,
            'games_won': player.games_won,
            'win_rate': player.get_win_rate()
        })
    
    return leaderboard
