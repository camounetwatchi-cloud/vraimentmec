import uuid
from collections import deque
import chess
import random
from flask_socketio import join_room, leave_room

# Dictionnaire global pour stocker toutes les parties actives
# Clé: game_id (str), Valeur: Game object
games = {}

class Game:
    """Représente une partie d'échecs active."""
    def __init__(self, player1_sid, player2_sid, fen_start):
        self.game_id = str(uuid.uuid4())
        self.board = chess.Board(fen_start)
        
        # Attribution aléatoire des couleurs
        if random.choice([True, False]):
            self.players = {
                player1_sid: chess.WHITE,
                player2_sid: chess.BLACK
            }
        else:
            self.players = {
                player1_sid: chess.BLACK,
                player2_sid: chess.WHITE
            }
            
        # Joindre les joueurs à la "salle" SocketIO pour la partie
        join_room(self.game_id, sid=player1_sid)
        join_room(self.game_id, sid=player2_sid)
        
        print(f"Nouvelle partie créée: {self.game_id}. Joueurs: {player1_sid} (W) vs {player2_sid} (B)")
        
    @property
    def fen(self):
        """Retourne la position FEN actuelle."""
        return self.board.fen()

    def get_player_color(self, sid):
        """Retourne la couleur du joueur (chess.WHITE ou chess.BLACK)."""
        return 'white' if self.players.get(sid) == chess.WHITE else 'black'
        
    def get_opponent_id(self, sid):
        """Retourne le SID de l'adversaire."""
        for player_sid, color in self.players.items():
            if player_sid != sid:
                return player_sid
        return None

    def make_move(self, player_sid, uci_move):
        """
        Tente de faire un mouvement.
        :param player_sid: ID de session du joueur
        :param uci_move: Mouvement au format UCI (ex: 'e2e4')
        :return: (Nouveau FEN, Statut de la partie)
        :raises ValueError: Si le mouvement est illégal ou ce n'est pas son tour.
        """
        player_color = self.players.get(player_sid)
        if player_color is None:
            raise ValueError("Vous n'êtes pas dans cette partie.")

        # Vérifie si c'est le tour du joueur
        if player_color != self.board.turn:
            raise ValueError("Ce n'est pas votre tour de jouer.")

        try:
            # Créer l'objet mouvement à partir de la chaîne UCI
            move = chess.Move.from_uci(uci_move)
            
            # Vérifier si le mouvement est légal
            if move not in self.board.legal_moves:
                raise ValueError("Mouvement illégal.")

            # Effectuer le mouvement
            self.board.push(move)
            
            # Déterminer le statut de la partie
            status = 'running'
            if self.board.is_checkmate():
                status = 'checkmate'
            elif self.board.is_stalemate():
                status = 'stalemate'
            elif self.board.is_insufficient_material():
                status = 'draw_insufficient'
            elif self.board.is_seventy_five_moves():
                status = 'draw_75_moves'
            elif self.board.is_check():
                status = 'check'

            return self.board.fen(), status

        except Exception as e:
            # Capturer les erreurs de format UCI ou autres exceptions
            raise ValueError(f"Erreur de mouvement: {e}")


class MatchmakingManager:
    """Gère la file d'attente et l'appariement des joueurs."""
    
    # File d'attente pour les joueurs seuls. Utilisation d'un deque pour l'efficacité.
    waiting_players = deque()

    @staticmethod
    def add_player(sid):
        """Ajoute un joueur à la file d'attente si il n'y est pas déjà."""
        if sid not in MatchmakingManager.waiting_players:
            MatchmakingManager.waiting_players.append(sid)
            print(f"Joueur ajouté à la file: {sid}. Taille de la file: {len(MatchmakingManager.waiting_players)}")

    @staticmethod
    def remove_player(sid):
        """Retire un joueur de la file d'attente (s'il y est)."""
        try:
            MatchmakingManager.waiting_players.remove(sid)
            print(f"Joueur retiré de la file: {sid}")
        except ValueError:
            pass  # N'était pas dans la file
            
        # Si le joueur était dans une partie, retire la partie
        game_id = MatchmakingManager.find_game_by_player_id(sid)
        if game_id:
            MatchmakingManager.remove_game(game_id)


    @staticmethod
    def check_for_match(new_player_sid):
        """
        Vérifie si un match peut être trouvé pour le dernier joueur ajouté.
        :return: game_id (str) si un match est trouvé, sinon None.
        """
        # Nécessite au moins 2 joueurs dans la file d'attente.
        if len(MatchmakingManager.waiting_players) >= 2:
            # Le premier joueur est l'adversaire
            player1_sid = MatchmakingManager.waiting_players.popleft() 
            # Le deuxième joueur (celui qui vient de se connecter)
            player2_sid = MatchmakingManager.waiting_players.popleft() 
            
            # Assurez-vous d'utiliser votre générateur FEN ici
            # Pour l'exemple, nous utilisons le FEN de départ standard.
            # Remplacer par la génération de position aléatoire plus tard.
            from .chess_generator import generate_fen_position
            # Tente de générer une position (avec des valeurs par défaut ou en cache)
            # Pour l'instant, on utilise le FEN de départ.
            fen_result = generate_fen_position() 
            fen_start = fen_result.get('fen', chess.STARTING_FEN) # Utilisez votre FEN généré

            # Créer la partie
            game = Game(player1_sid, player2_sid, fen_start)
            games[game.game_id] = game
            
            return game.game_id
            
        return None

    @staticmethod
    def remove_game(game_id):
        """Supprime la partie de la mémoire et gère les salles."""
        if game_id in games:
            game = games[game_id]
            
            # Retirer les joueurs de la salle SocketIO
            for player_sid in game.players.keys():
                leave_room(game_id, sid=player_sid)
                
            del games[game_id]
            print(f"Partie {game_id} supprimée.")

    @staticmethod
    def find_game_by_player_id(sid):
        """Trouve la partie à laquelle appartient un SID donné."""
        for game_id, game in games.items():
            if sid in game.players:
                return game_id
        return None

# Installez la dépendance `python-chess` (doit être ajoutée à votre requirements.txt)
# Installez la dépendance `python-engineio` (nécessaire pour SocketIO)
# Installez la dépendance `gevent` (pour async_mode='gevent')
