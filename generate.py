import chess
import chess.engine
import random
import os

# --- Configuration ---
# Chemin RELATIF vers Stockfish. Il est attendu dans le dossier 'engine' du projet.
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres de génération
MIN_MOVES = 15
MAX_MOVES = 50
STOCKFISH_DEPTH = 18 # Profondeur d'analyse

# --- Fonctions ---

def generate_random_fen():
    """Génère une FEN valide en jouant un nombre aléatoire de coups légaux."""
    board = chess.Board()
    num_moves = random.randint(MIN_MOVES, MAX_MOVES)
    
    for _ in range(num_moves):
        if board.is_game_over():
            break
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            break
            
        move = random.choice(legal_moves)
        board.push(move)
        
    return board.fen()

def get_stockfish_evaluation(fen):
    """Obtient l'évaluation Stockfish pour une FEN donnée."""
    engine = None
    try:
        # Vérifiez que le fichier Stockfish existe avant de le démarrer
        if not os.path.exists(STOCKFISH_PATH):
             return f"Erreur: Fichier Stockfish non trouvé à l'emplacement: {STOCKFISH_PATH}", None

        # Démarrage du moteur Stockfish
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        board = chess.Board(fen)
        
        # Analyse à la profondeur spécifiée
        info = engine.analyse(board, chess.engine.Limit(depth=STOCKFISH_DEPTH))
        score = info["score"].white() # Score du point de vue des Blancs
        
        # Formatage de l'évaluation
        if score.is_mate():
            evaluation_str = f"Mat en {score.mate()}"
            evaluation_cp = 99999 if score.mate() > 0 else -99999
        else:
            # Centipions convertis en pions (ex: 50 cp -> +0.50)
            evaluation_cp = score.cp
            evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
        return evaluation_str, evaluation_cp
        
    except Exception as e:
        return f"Erreur lors de l'analyse Stockfish: {e}", None
    finally:
        if engine:
            engine.quit()

# --- Script Principal ---
if __name__ == "__main__":
    
    print("--- Génération et Évaluation de Scène d'Échecs ---")
    
    # 1. Génération de la FEN
    fen = generate_random_fen()
    
    # 2. Évaluation
    evaluation_str, evaluation_cp = get_stockfish_evaluation(fen)
    
    # 3. Affichage
    print(f"\nFEN : {fen}")
    
    # Vérifiez la validité de l'évaluation
    if evaluation_cp is not None:
        print(f"Tour au trait : {'Blanc' if chess.Board(fen).turn == chess.WHITE else 'Noir'}")
        print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
        
        # Exemple de filtrage: ne garder que les positions "équilibrées"
        # On définit une plage d'équilibre de +/- 0.50 pion (50 centipions)
        if -50 <= evaluation_cp <= 50:
            print("\n✅ Position considérée comme équilibrée (+/- 0.50 Pions).")
        else:
            print("\n❌ Position avec un avantage significatif (non équilibrée).")
    else:
        print(evaluation_str) # Affiche le message d'erreur
