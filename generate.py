import chess
import chess.engine
import random
import os
import time
import math

# --- Configuration ---
# Le chemin est construit RELATIVEMENT à la position du script (dans le dossier 'engine')
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres d'analyse
STOCKFISH_DEPTH = 16 

# PARAMÈTRES D'ÉVALUATION CIBLÉE
TARGET_MIN_CP = -10 # Cherche entre -0.10 et +0.10 pions
TARGET_MAX_CP = 10  
MAX_ATTEMPTS = 5000 # Augmenté car trouver une FEN légale ET égale est TRES difficile

# Déséquilibre Matériel Compensé
MIN_MATERIAL_DIFFERENCE = 3.0 
MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

# Pièces disponibles pour la génération aléatoire
PIECES_TO_GENERATE = [
    chess.ROOK, chess.ROOK, chess.KNIGHT, chess.KNIGHT, chess.BISHOP, chess.BISHOP, chess.QUEEN, 
    chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN
] # Une liste de pièces (sans les Rois)

# --- Nouvelles Fonctions de Génération Aléatoire et Légalité ---

def generate_pure_random_fen():
    """
    Génère une FEN aléatoire en plaçant les pièces.
    Cette méthode est plus lente mais génère des positions plus variées.
    """
    board = chess.Board(None) # Commence avec un plateau vide

    # 1. Placer les Rois (obligatoire pour la légalité)
    king_squares = random.sample(chess.SQUARES, 2)
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))

    # 2. Placer les autres pièces aléatoirement
    available_squares = list(set(chess.SQUARES) - set(king_squares))
    random.shuffle(available_squares)
    
    # On choisit aléatoirement combien de pièces placer (pour avoir des finales)
    num_pieces_to_place = random.randint(10, len(PIECES_TO_GENERATE) * 2) 
    
    pieces_to_place = random.sample(PIECES_TO_GENERATE * 2, num_pieces_to_place)
    
    white_turn = random.choice([True, False]) # Qui est au trait
    
    for piece_type in pieces_to_place:
        if not available_squares:
            break
            
        square = available_squares.pop()
        
        # 50% de chance d'être blanc ou noir
        color = random.choice([chess.WHITE, chess.BLACK])
        
        # Les pions ne doivent pas être sur la 1ère ou 8ème rangée
        if piece_type == chess.PAWN:
            if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                continue

        board.set_piece_at(square, chess.Piece(piece_type, color))

    # 3. Finaliser la FEN
    fen_parts = board.fen().split(' ')
    fen_parts[1] = 'w' if white_turn else 'b' # Le trait
    fen_parts[2] = '-' # Simplification des droits de roque
    fen_parts[3] = '-' # Simplification de l'en passant
    fen_parts[4] = '0'
    fen_parts[5] = str(random.randint(10, 50)) # Numéro de coup

    return ' '.join(fen_parts)


def is_fen_legal(fen: str):
    """Vérifie si une FEN est syntaxiquement et légalement valide."""
    try:
        board = chess.Board(fen)
        # La vérification la plus stricte : le côté qui n'est pas au trait NE DOIT PAS être en échec.
        # Et le côté au trait ne doit pas avoir un roi déjà en échec (impossible d'avoir des rois adjacents).
        
        # Vérifions si le côté qui vient de jouer (celui qui n'est PAS au trait) a laissé son roi en échec.
        # Si la couleur au trait (board.turn) est White, alors le Noir doit avoir joué
        # Le FEN est illégal si le roi qui vient de jouer est en échec (impossible en vrai partie)
        
        # Test 1: La position est-elle légale selon python-chess? (checkmate, stalemate, etc. sont OK)
        if board.is_valid():
            # Test 2: Le côté au trait peut-il capturer le roi adverse? (Vérification de la distance des rois)
            # Cette vérification est implicite dans board.is_valid()
            
            return True, board
        return False, None
    except ValueError:
        return False, None

# --- Fonctions de Vérification Matérielle et d'Évaluation (Identiques) ---

def calculate_material_value(board: chess.Board):
    """Calcule la valeur matérielle totale pour chaque couleur."""
    white_material = 0
    black_material = 0
    for piece_type, value in MATERIAL_VALUES.items():
        white_material += len(board.pieces(piece_type, chess.WHITE)) * value
        black_material += len(board.pieces(piece_type, chess.BLACK)) * value
    return white_material, black_material


def is_material_compensated(board: chess.Board, min_diff: float):
    """Vérifie si la différence matérielle est supérieure ou égale au minimum requis."""
    white_mat, black_mat = calculate_material_value(board)
    difference = abs(white_mat - black_mat)
    return difference >= min_diff, white_mat, black_mat


def get_stockfish_evaluation(fen: str):
    """Obtient l'évaluation Stockfish pour une FEN donnée (analyse finale)."""
    engine = None
    try:
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
        return None, None
    finally:
        if engine:
            engine.quit()

# --- Script Principal : Boucle de Filtrage Aléatoire ---

if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    
    print("--- Générateur de FEN Aléatoire Pure (Déséquilibre Matériel Compensé) ---")
    print(f"Objectif : Évaluation {TARGET_MIN_CP/100:.2f} à {TARGET_MAX_CP/100:.2f} ET Différence Matérielle >= {MIN_MATERIAL_DIFFERENCE} points.")
    print("-" * 80)
    
    start_time = time.time()
    
    # NOTE: L'ancienne fonction d'accélération n'est plus nécessaire car Stockfish n'est pas utilisé pour la génération.

    while not fen_trouvee and tentatives < MAX_ATTEMPTS:
        tentatives += 1
        
        # 1. Génération Aléatoire Pure
        fen = generate_pure_random_fen()
        
        # 2. Vérification de la Légalité Stricte
        is_legal, board = is_fen_legal(fen)
        
        if not is_legal:
            print(f"Tentative {tentatives}: Illégale. Retente...", end='\r')
            continue
            
        # 3. Vérification du Matériel
        is_compensated, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
        
        if is_compensated:
            # 4. Évaluation Stockfish (lent) si le matériel est OK
            evaluation_str, evaluation_cp = get_stockfish_evaluation(fen)
            
            if evaluation_cp is not None and TARGET_MIN_CP <= evaluation_cp <= TARGET_MAX_CP:
                # 5. Succès ! Les trois conditions sont remplies.
                fen_trouvee = True
                
                print("\n✅ POSITION ALÉATOIRE COMPENSÉE TROUVÉE !")
                print(f"FEN : {fen}")
                print(f"Matériel Blanc: {white_mat}, Matériel Noir: {black_mat}. Différence: {abs(white_mat - black_mat)} points.")
                print(f"Tour au trait : {'Blanc' if board.turn == chess.WHITE else 'Noir'}")
                print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
                print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
                
            else:
                print(f"Tentative {tentatives}: Légal, Matériel OK ({abs(white_mat - black_mat)}), Éval: {evaluation_str}. Retente...", end='\r')
        
        else:
            print(f"Tentative {tentatives}: Légal, Matériel insuffisant ({abs(white_mat - black_mat)}). Retente...", end='\r')
            
    if not fen_trouvee:
        print("\n\n❌ ÉCHEC : La position n'a pas été trouvée après le nombre maximal de tentatives.")
