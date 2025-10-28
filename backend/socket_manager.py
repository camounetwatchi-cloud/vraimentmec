import uuid
from collections import deque
import chess
import random
from flask_socketio import join_room, leave_room
from datetime import datetime

# Dictionnaire global pour stocker toutes les parties actives
# Clé: game_id (str), Valeur: Game object
games = {}

class Game:
    """Représente une partie d'échecs active avec gestion complète."""
    
    def __init__(self, player1_sid, player2_sid, player1_user_id, player2_user_id, fen_start):
        """
        Initialise une nouvelle partie d'échecs.
        
        Args:
            player1_sid: Session ID du premier joueur (SocketIO)
            player2_sid: Session ID du second joueur (SocketIO)
            player1_user_id: ID utilisateur du premier joueur (base de données)
            player2_user_id: ID utilisateur du second joueur (base de données)
            fen_start: Position FEN de départ
        """
        self.game_id = str(uuid.uuid4())
        self.board = chess.Board(fen_start)
        self.starting_fen = fen_start
        self.moves_history = []  # Liste des coups en notation UCI
        self.started_at = datetime.now()
        
        # Importer ici pour éviter les imports circulaires
        from .db_models import User
        
        # Récupérer les utilisateurs depuis la base de données
        self.user1 = User.query.get(player1_user_id)
        self.user2 = User.query.get(player2_user_id)
        
        # Attribution aléatoire des couleurs
        if random.choice([True, False]):
            self.players = {
                player1_sid: {
                    'color': chess.WHITE,
                    'user_id': player1_user_id,
                    'username': self.user1.username if self.user1 else 'Joueur 1'
                },
                player2_sid: {
                    'color': chess.BLACK,
                    'user_id': player2_user_id,
                    'username': self.user2.username if self.user2 else 'Joueur 2'
                }
            }
        else:
            self.players = {
                player1_sid: {
                    'color': chess.BLACK,
                    'user_id': player1_user_id,
                    'username': self.user1.username if self.user1 else 'Joueur 1'
                },
                player2_sid: {
                    'color': chess.WHITE,
                    'user_id': player2_user_id,
                    'username': self.user2.username if self.user2 else 'Joueur 2'
                }
            }
        
        # Joindre les joueurs à la "salle" SocketIO pour la partie
        join_room(self.game_id, sid=player1_sid)
        join_room(self.game_id, sid=player2_sid)
        
        player1_name = self.user1.username if self.user1 else player1_user_id
        player2_name = self.user2.username if self.user2 else player2_user_id
        print(f"Nouvelle partie créée: {self.game_id}")
        print(f"  {player1_name} vs {player2_name}")
        
    @property
    def fen(self):
        """Retourne la position FEN actuelle."""
        return self.board.fen()

    def get_player_color(self, sid):
        """
        Retourne la couleur du joueur en format string.
        
        Args:
            sid: Session ID du joueur
            
        Returns:
            'white' ou 'black'
        """
        player_data = self.players.get(sid)
        if player_data:
            return 'white' if player_data['color'] == chess.WHITE else 'black'
        return None
    
    def get_player_color_enum(self, sid):
        """
        Retourne la couleur du joueur en format chess.Color.
        
        Args:
            sid: Session ID du joueur
            
        Returns:
            chess.WHITE ou chess.BLACK
        """
        player_data = self.players.get(sid)
        return player_data['color'] if player_data else None
        
    def get_opponent_id(self, sid):
        """
        Retourne le SID de l'adversaire.
        
        Args:
            sid: Session ID du joueur actuel
            
        Returns:
            Session ID de l'adversaire ou None
        """
        for player_sid in self.players.keys():
            if player_sid != sid:
                return player_sid
        return None
    
    def get_player_info(self, sid):
        """
        Retourne les informations complètes d'un joueur.
        
        Args:
            sid: Session ID du joueur
            
        Returns:
            Dictionnaire avec les infos du joueur
        """
        return self.players.get(sid)
    
    def get_game_info(self):
        """
        Retourne les informations de la partie pour l'affichage.
        
        Returns:
            Dictionnaire avec toutes les infos de la partie
        """
        players_info = {}
        for sid, data in self.players.items():
            color_name = 'white' if data['color'] == chess.WHITE else 'black'
            players_info[color_name] = {
                'username': data['username'],
                'user_id': data['user_id']
            }
        
        return {
            'game_id': self.game_id,
            'fen': self.fen,
            'players': players_info,
            'turn': 'white' if self.board.turn == chess.WHITE else 'black',
            'moves_count': len(self.moves_history),
            'started_at': self.started_at.isoformat()
        }

    def make_move(self, player_sid, uci_move):
        """
        Tente de faire un mouvement.
        
        Args:
            player_sid: ID de session du joueur
            uci_move: Mouvement au format UCI (ex: 'e2e4')
            
        Returns:
            Tuple (Nouveau FEN, Statut de la partie, Info additionnelles)
            
        Raises:
            ValueError: Si le mouvement est illégal ou ce n'est pas son tour.
        """
        player_data = self.players.get(player_sid)
        
        if not player_data:
            raise ValueError("Vous n'êtes pas dans cette partie.")
        
        player_color = player_data['color']

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
            self.moves_history.append(uci_move)
            
            # Déterminer le statut de la partie
            status = 'running'
            result = None
            winner = None
            
            if self.board.is_checkmate():
                status = 'checkmate'
                # Le joueur qui vient de jouer a gagné (car c'est l'autre qui est mat)
                result = 'white_win' if player_color == chess.WHITE else 'black_win'
                winner = player_data['username']
                
            elif self.board.is_stalemate():
                status = 'stalemate'
                result = 'draw'
                
            elif self.board.is_insufficient_material():
                status = 'draw_insufficient'
                result = 'draw'
                
            elif self.board.is_seventy_five_moves():
                status = 'draw_75_moves'
                result = 'draw'
                
            elif self.board.is_fivefold_repetition():
                status = 'draw_repetition'
                result = 'draw'
                
            elif self.board.is_check():
                status = 'check'
            
            # Si la partie est terminée, sauvegarder dans la base de données
            if result:
                self.save_to_database(result)
            
            return self.board.fen(), status, {
                'moves_count': len(self.moves_history),
                'last_move': uci_move,
                'result': result,
                'winner': winner
            }

        except ValueError as e:
            # Erreur déjà bien formatée
            raise e
        except Exception as e:
            # Capturer les erreurs de format UCI ou autres exceptions
            raise ValueError(f"Erreur de mouvement: {str(e)}")
    
    def save_to_database(self, result):
        """
        Sauvegarde la partie dans la base de données et met à jour les statistiques.
        
        Args:
            result: Résultat de la partie ('white_win', 'black_win', 'draw', 'abandoned')
        """
        try:
            from .db_models import GameHistory, User, db
            
            # Identifier les joueurs blancs et noirs
            white_player_id = None
            black_player_id = None
            
            for sid, data in self.players.items():
                if data['color'] == chess.WHITE:
                    white_player_id = data['user_id']
                else:
                    black_player_id = data['user_id']
            
            # Créer l'entrée d'historique
            game_history = GameHistory(
                white_player_id=white_player_id,
                black_player_id=black_player_id,
                starting_fen=self.starting_fen,
                final_fen=self.board.fen(),
                moves=' '.join(self.moves_history),
                result=result,
                ended_at=datetime.now(),
                duration_seconds=(datetime.now() - self.started_at).seconds
            )
            
            db.session.add(game_history)
            
            # Mettre à jour les statistiques des joueurs
            white_player = User.query.get(white_player_id)
            black_player = User.query.get(black_player_id)
            
            if white_player:
                white_player.games_played += 1
                if result == 'white_win':
                    white_player.games_won += 1
            
            if black_player:
                black_player.games_played += 1
                if result == 'black_win':
                    black_player.games_won += 1
            
            db.session.commit()
            print(f"Partie {self.game_id} sauvegardée. Résultat: {result}")
            
        except Exception as e:
            print(f"Erreur lors de la sauvegarde de la partie: {e}")
            # Ne pas lever l'exception pour ne pas bloquer le flux de jeu


class MatchmakingManager:
    """Gère la file d'attente et l'appariement des joueurs."""
    
    # File d'attente pour les joueurs seuls
    # Format: {sid: {'user_id': str, 'username': str, 'elo': int}}
    waiting_players = {}

    @staticmethod
    def add_player(sid, user_id, username=None, elo=1200):
        """
        Ajoute un joueur à la file d'attente si il n'y est pas déjà.
        
        Args:
            sid: Session ID du joueur (SocketIO)
            user_id: ID utilisateur dans la base de données
            username: Nom d'utilisateur (optionnel)
            elo: Rating ELO du joueur (optionnel)
        """
        if sid not in MatchmakingManager.waiting_players:
            MatchmakingManager.waiting_players[sid] = {
                'user_id': user_id,
                'username': username or f"User_{user_id[:8]}",
                'elo': elo
            }
            print(f"Joueur ajouté à la file: {username} (ELO: {elo})")
            print(f"Taille de la file: {len(MatchmakingManager.waiting_players)}")

    @staticmethod
    def remove_player(sid):
        """
        Retire un joueur de la file d'attente (s'il y est).
        
        Args:
            sid: Session ID du joueur
        """
        if sid in MatchmakingManager.waiting_players:
            player_info = MatchmakingManager.waiting_players[sid]
            del MatchmakingManager.waiting_players[sid]
            print(f"Joueur retiré de la file: {player_info['username']}")
        
        # Si le joueur était dans une partie, gérer l'abandon
        game_id = MatchmakingManager.find_game_by_player_id(sid)
        if game_id:
            MatchmakingManager.handle_player_disconnect(sid, game_id)

    @staticmethod
    def check_for_match(new_player_sid):
        """
        Vérifie si un match peut être trouvé pour le dernier joueur ajouté.
        
        Args:
            new_player_sid: Session ID du nouveau joueur
            
        Returns:
            game_id (str) si un match est trouvé, sinon None.
        """
        # Nécessite au moins 2 joueurs dans la file d'attente
        if len(MatchmakingManager.waiting_players) >= 2:
            # Récupérer les deux premiers joueurs
            waiting_list = list(MatchmakingManager.waiting_players.items())
            
            # Le nouveau joueur et le premier de la file
            player1_sid, player1_data = waiting_list[0]
            player2_sid, player2_data = waiting_list[1]
            
            # Les retirer de la file d'attente
            del MatchmakingManager.waiting_players[player1_sid]
            del MatchmakingManager.waiting_players[player2_sid]
            
            print(f"Match trouvé: {player1_data['username']} vs {player2_data['username']}")
            
            # Générer une position avec le générateur FEN
            try:
                from .chess_generator import generate_fen_position
                
                # Génération rapide avec moins de tentatives pour le matchmaking
                fen_result = generate_fen_position(
                    target_min=25,
                    target_max=100,
                    max_attempts=5000  # Moins d'attempts pour ne pas faire attendre
                )
                fen_start = fen_result.get('fen', chess.STARTING_FEN)
                
            except Exception as e:
                print(f"Erreur lors de la génération FEN: {e}")
                print("Utilisation de la position de départ standard")
                fen_start = chess.STARTING_FEN
            
            # Créer la partie
            game = Game(
                player1_sid,
                player2_sid,
                player1_data['user_id'],
                player2_data['user_id'],
                fen_start
            )
            
            games[game.game_id] = game
            
            return game.game_id
        
        return None

    @staticmethod
    def remove_game(game_id):
        """
        Supprime la partie de la mémoire et gère les salles SocketIO.
        
        Args:
            game_id: ID de la partie à supprimer
        """
        if game_id in games:
            game = games[game_id]
            
            # Retirer les joueurs de la salle SocketIO
            for player_sid in game.players.keys():
                leave_room(game_id, sid=player_sid)
            
            del games[game_id]
            print(f"Partie {game_id} supprimée de la mémoire.")

    @staticmethod
    def find_game_by_player_id(sid):
        """
        Trouve la partie à laquelle appartient un SID donné.
        
        Args:
            sid: Session ID du joueur
            
        Returns:
            game_id (str) ou None si le joueur n'est dans aucune partie
        """
        for game_id, game in games.items():
            if sid in game.players:
                return game_id
        return None
    
    @staticmethod
    def handle_player_disconnect(sid, game_id):
        """
        Gère la déconnexion d'un joueur pendant une partie.
        
        Args:
            sid: Session ID du joueur qui s'est déconnecté
            game_id: ID de la partie
        """
        if game_id not in games:
            return
        
        game = games[game_id]
        
        # Sauvegarder la partie comme abandonnée
        disconnected_player = game.players.get(sid)
        if disconnected_player:
            # Déterminer le résultat (l'adversaire gagne)
            if disconnected_player['color'] == chess.WHITE:
                result = 'black_win'
            else:
                result = 'white_win'
            
            game.save_to_database('abandoned')
            print(f"Partie {game_id} terminée par abandon de {disconnected_player['username']}")
        
        # Supprimer la partie
        MatchmakingManager.remove_game(game_id)
    
    @staticmethod
    def get_waiting_players_count():
        """
        Retourne le nombre de joueurs en attente.
        
        Returns:
            int: Nombre de joueurs dans la file d'attente
        """
        return len(MatchmakingManager.waiting_players)
    
    @staticmethod
    def get_active_games_count():
        """
        Retourne le nombre de parties actives.
        
        Returns:
            int: Nombre de parties en cours
        """
        return len(games)
