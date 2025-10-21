import chess
import chess.engine
import random
import os
import time
import math

# --- Configuration ---
# Le chemin est construit RELATIVEMENT à la position du script (dans le dossier 'engine')
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres de génération aléatoire 
MIN_MOVES = 15  
MAX_MOVES = 50  
STOCKFISH_DEPTH = 16 

# PARAMÈTRES D'ÉVALUATION CIBLÉE
# Cherche une position entre -0.10 et +0.10 pions (centipions)
TARGET_MIN_CP = -10 
TARGET_MAX_CP = 10  
MAX_ATTEMPTS = 1000 # Augmenté car les conditions sont plus strictes

# NOUVEAU PARAMÈTRE : Différence matérielle minimale (en points)
MIN_MATERIAL_DIFFERENCE = 10.0 
MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    # Le Roi n'est pas compté dans la valeur matérielle classique
}


# --- Nouvelles Fonctions de Vérification ---

def calculate_material_value(board: chess.Board):
    """Calcule la valeur matérielle totale pour chaque couleur."""
    white_material = 0
    black_material = 0
    
    for piece_type, value in MATERIAL_VALUES.items():
        # Compte les pièces blanches
        white_material += len(board.pieces(piece_type, chess.WHITE)) * value
        # Compte les pièces noires
        black_material += len(board.pieces(piece_type, chess.BLACK)) * value
        
    return white_material, black_material


def is_material_compensated(board: chess.Board, min_diff: float):
    """Vérifie si la différence matérielle est supérieure ou égale au minimum requis."""
    white_mat, black_mat = calculate_material_value(board)
    difference = abs(white_mat - black_mat)
    
    # La valeur matérielle n'est pas censée être négative, mais nous vérifions
    # si la différence est au moins la valeur minimale requise.
    return difference >= min_diff, white_mat, black_mat


# --- Fonctions de Génération et d'Évaluation (Identiques à la V3) ---

def generate_random_fen_aggressive(engine: chess.engine.SimpleEngine):
    # ... (Garder cette fonction telle quelle depuis la dernière version)
    board = chess.Board()
    num_moves = random.randint(MIN_MOVES, MAX_MOVES)
    
    for i in range(num_moves):
        if board.is_game_over():
            break
        
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            break
            
        try:
            analysis = engine.analyse(board, chess.engine.Limit(depth=4), multipv=3)
            
            if random.random() < 0.20:
                move = random.choice(legal_moves)
            else:
                move = analysis[random.randint(0, min(len(analysis)-1, 2))]["pv"][0]
            
        except Exception:
            move = random.choice(legal_moves)

        board.push(move)
        
    return board.fen()


def get_stockfish_evaluation(fen: str):
    # ... (Garder cette fonction telle quelle depuis la dernière version)
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
            evaluation_cp = 99999 if score.mate() > 0 else -99999
        else:
            evaluation_cp = score.cp
            evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
        return evaluation_str, evaluation_cp
        
    except Exception as e:
        # print(f"\nErreur lors de l'analyse Stockfish: {e}") # Désactivé pour la boucle
        return None, None
    finally:
        if engine:
            engine.quit()


# --- Script Principal : Boucle de Filtrage avec Vérification Matérielle ---

if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    
    print("--- Générateur de Déséquilibre Matériel Compensé ---")
    print(f"Objectif : Évaluation {TARGET_MIN_CP/100:.2f} à {TARGET_MAX_CP/100:.2f} ET Différence Matérielle >= {MIN_MATERIAL_DIFFERENCE} points.")
    print("-" * 70)
    
    start_time = time.time()
    
    engine_for_generation = None
    try:
        engine_for_generation = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
    except FileNotFoundError:
        print(f"Erreur: Le moteur Stockfish n'a pas pu être démarré pour la génération. Veuillez vérifier le chemin: {STOCKFISH_PATH}")
        exit()

    try:
        while not fen_trouvee and tentatives < MAX_ATTEMPTS:
            tentatives += 1
            
            # 1. Génération de FEN
            fen = generate_random_fen_aggressive(engine_for_generation)
            board = chess.Board(fen)
            
            # 2. Vérification du matériel (rapide)
            is_compensated, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
            
            if is_compensated:
                # 3. Évaluation Stockfish (lent) si le matériel est déséquilibré
                evaluation_str, evaluation_cp = get_stockfish_evaluation(fen)
                
                if evaluation_cp is not None and TARGET_MIN_CP <= evaluation_cp <= TARGET_MAX_CP:
                    # 4. Succès ! Les deux conditions sont remplies.
                    fen_trouvee = True
                    
                    print("\n✅ POSITION DÉSÉQUILIBRÉE ET ÉQUILIBRÉE (COMPENSÉE) TROUVÉE !")
                    print(f"FEN : {fen}")
                    print(f"Matériel Blanc: {white_mat}, Matériel Noir: {black_mat}. Différence: {abs(white_mat - black_mat)} points.")
                    print(f"Tour au trait : {'Blanc' if board.turn == chess.WHITE else 'Noir'}")
                    print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
                    print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
                    
                else:
                    # Échec de l'évaluation, mais le matériel était OK.
                    print(f"Tentative {tentatives}: Matériel OK ({abs(white_mat - black_mat)}), Éval: {evaluation_str}. Retente...", end='\r')
            
            else:
                # Le déséquilibre matériel n'est pas suffisant, on ne lance même pas Stockfish.
                print(f"Tentative {tentatives}: Matériel insuffisant ({abs(white_mat - black_mat)}). Retente...", end='\r')
                
        if not fen_trouvee:
            print("\n\n❌ ÉCHEC : La position n'a pas été trouvée après le nombre maximal de tentatives.")
            
    finally:
        if engine_for_generation:
            engine_for_generation.quit()
