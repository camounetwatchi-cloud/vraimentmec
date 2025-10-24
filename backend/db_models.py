from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Crée l'objet SQLAlchemy
db = SQLAlchemy()

# Définition d'un modèle de base (vous le complèterez plus tard)
class Game(db.Model):
    """Modèle pour stocker une partie ou une position d'échecs."""
    __tablename__ = 'games'
    id = db.Column(db.Integer, primary_key=True)
    fen_string = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Game {self.id} | {self.fen_string}>'

def init_db(app):
    """Initialise l'application Flask avec l'instance SQLAlchemy et crée les tables."""
    db.init_app(app)
    with app.app_context():
        # Crée les tables si elles n'existent pas
        db.create_all()
        print("INFO: Tables de la base de données vérifiées/créées.")
