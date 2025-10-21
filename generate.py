import chess
import chess.engine
import random
import os
import time

# --- Configuration ---
# Chemin RELATIF vers Stockfish.
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres de génération aléatoire (plus de coups = position plus complexe)
MIN_MOVES = 15  
MAX_MOVES = 50  
STOCKFISH_DEPTH = 16 # Une profondeur un peu plus faible pour la rapidité du filtrage

# PARAMÈTRES D'ÉVALUATION CIBLÉE (Le coeur de la modification)
# Nous allons chercher une position entre -0.10 et +0.10 pions (centipions)
TARGET_MIN_CP = -10 
TARGET_MAX_CP = 10  
MAX_ATTEMPTS = 500 # Limiter le nombre d'essais pour éviter une boucle infinie


# --- Fonctions ---

def generate_random_fen():
    """Génère une FEN valide en jouant un nombre aléatoire de coups légaux."""
    board = chess.Board()
    # Le nombre de demi-coups joués varie
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
        if not os.path.exists(STOCKFISH_PATH):
             print(f"\nErreur: Fichier Stockfish non trouvé à l'emplacement: {STOCKFISH_PATH}")
             return None, None

        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        board = chess.Board(fen)
        
        info = engine.analyse(board, chess.engine.Limit(depth=STOCKFISH_DEPTH))
        score = info["score"].white() 
        
        if score.is_mate():
            evaluation_str = f"Mat en {score.mate()}"
            # Utilisez une valeur très élevée pour le mat, ce qui ne rentrera pas dans la cible
            evaluation_cp = 99999 if score.mate() > 0 else -99999
        else:
            evaluation_cp = score.cp
            evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
        return evaluation_str, evaluation_cp
        
    except Exception as e:
        print(f"\nErreur lors de l'analyse Stockfish: {e}")
        return None, None
    finally:
        if engine:
            engine.quit()

# --- Script Principal : Boucle de Filtrage ---
if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    
    print("--- Générateur de Scène d'Échecs Équilibrée ---")
    print(f"Objectif : Évaluation entre {TARGET_MIN_CP/100:.2f} et {TARGET_MAX_CP/100:.2f} Pions.")
    print("-" * 40)
    
    start_time = time.time()
    
    while not fen_trouvee and tentatives < MAX_ATTEMPTS:
        tentatives += 1
        
        # 1. Génération
        fen = generate_random_fen()
        
        # 2. Évaluation
        evaluation_str, evaluation_cp = get_stockfish_evaluation(fen)
        
        if evaluation_cp is not None and TARGET_MIN_CP <= evaluation_cp <= TARGET_MAX_CP:
            # 3. Succès !
            fen_trouvee = True
            
            print("\n✅ POSITION ÉQUILIBRÉE TROUVÉE !")
            print(f"FEN : {fen}")
            print(f"Tour au trait : {'Blanc' if chess.Board(fen).turn == chess.WHITE else 'Noir'}")
            print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
            print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
            
        else:
            # Échec, continue la boucle
            print(f"Tentative {tentatives}: Éval: {evaluation_str}. Retente...", end='\r')
            
    if not fen_trouvee:
        print("\n\n❌ ÉCHEC : La position équilibrée n'a pas été trouvée après le nombre maximal de tentatives.")
        print(f"Veuillez augmenter MAX_ATTEMPTS ou élargir la fourchette cible ({TARGET_MIN_CP/100:.2f} à {TARGET_MAX_CP/100:.2f}).")
