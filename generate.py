import chess
import chess.engine
import random
import os
import time

# --- Configuration ---
# Le chemin est construit RELATIVEMENT à la position du script (dans le dossier 'engine')
# C'est la façon la plus robuste de spécifier le chemin de Stockfish.
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres de génération aléatoire (plus de coups = position plus complexe)
MIN_MOVES = 15  
MAX_MOVES = 50  
STOCKFISH_DEPTH = 16 # Profondeur d'analyse du moteur

# PARAMÈTRES D'ÉVALUATION CIBLÉE
# Cherche une position entre -0.10 et +0.10 pions (centipions)
TARGET_MIN_CP = -10 
TARGET_MAX_CP = 10  
MAX_ATTEMPTS = 500 


# --- Fonctions ---

def generate_random_fen_aggressive(engine):
    """
    Génère une FEN en jouant des coups aléatoires et déviants pour créer 
    des positions structurellement plus déséquilibrées, tout en restant légales.
    """
    board = chess.Board()
    num_moves = random.randint(MIN_MOVES, MAX_MOVES)
    
    for i in range(num_moves):
        if board.is_game_over():
            break
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            break
            
        try:
            # Analyse rapide à faible profondeur pour déterminer les bons coups
            analysis = engine.analyse(board, chess.engine.Limit(depth=4), multipv=3)
            
            # 20% de chance de choisir un coup complètement aléatoire pour créer des déséquilibres
            if random.random() < 0.20:
                move = random.choice(legal_moves)
            else:
                # Sinon, on choisit un des 3 meilleurs coups (y compris le 2e ou 3e, pour varier)
                move = analysis[random.randint(0, min(len(analysis)-1, 2))]["pv"][0]
            
        except Exception:
            # Si l'analyse échoue pour une raison quelconque, on choisit un coup aléatoire simple
            move = random.choice(legal_moves)

        board.push(move)
        
    return board.fen()


def get_stockfish_evaluation(fen):
    """Obtient l'évaluation Stockfish pour une FEN donnée (analyse finale)."""
    engine = None
    try:
        if not os.path.exists(STOCKFISH_PATH):
             print(f"\nErreur: Fichier Stockfish non trouvé à l'emplacement: {STOCKFISH_PATH}")
             return None, None

        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        board = chess.Board(fen)
        
        # Analyse à la profondeur spécifiée (STOCKFISH_DEPTH)
        info = engine.analyse(board, chess.engine.Limit(depth=STOCKFISH_DEPTH))
        score = info["score"].white() 
        
        if score.is_mate():
            evaluation_str = f"Mat en {score.mate()}"
            evaluation_cp = 99999 if score.mate() > 0 else -99999
        else:
            evaluation_cp = score.cp
            evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
        return evaluation_str, evaluation_cp
        
    except Exception as e:
        # Ceci peut arriver si Stockfish ne peut pas démarrer ou est inaccessible.
        return None, None
    finally:
        if engine:
            engine.quit()

# --- Script Principal : Boucle de Filtrage ---
if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    
    print("--- Générateur de Scène d'Échecs Équilibrée (Filtrage Actif) ---")
    print(f"Objectif : Évaluation entre {TARGET_MIN_CP/100:.2f} et {TARGET_MAX_CP/100:.2f} Pions.")
    print("-" * 40)
    
    start_time = time.time()
    
    # Démarrer le moteur une seule fois pour la génération rapide (depth=4)
    engine_for_generation = None
    try:
        engine_for_generation = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError:
        print(f"Erreur: Le moteur Stockfish n'a pas pu être démarré pour la génération. Veuillez vérifier le chemin: {STOCKFISH_PATH}")
        exit()

    try:
        while not fen_trouvee and tentatives < MAX_ATTEMPTS:
            tentatives += 1
            
            # 1. Génération
            fen = generate_random_fen_aggressive(engine_for_generation)
            
            # 2. Évaluation (La fonction get_stockfish_evaluation redémarre le moteur pour l'analyse approfondie)
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
                # Utilisez l'évaluation formatée 'evaluation_str' qui est plus lisible
                print(f"Tentative {tentatives}: Éval: {evaluation_str}. Retente...", end='\r')
                
        if not fen_trouvee:
            print("\n\n❌ ÉCHEC : La position équilibrée n'a pas été trouvée après le nombre maximal de tentatives.")
            
    finally:
        # Fermer le moteur utilisé pour la génération
        if engine_for_generation:
            engine_for_generation.quit()
