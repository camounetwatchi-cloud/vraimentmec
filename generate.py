import chess
import chess.engine
import random
import os
import time
import math

# --- Configuration ---
# Le chemin est construit RELATIVEMENT à la position du script
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "engine", "stockfish-windows-x86-64-avx2.exe")

# Paramètres d'analyse
STOCKFISH_DEPTH = 16 

# PARAMÈTRES D'ÉVALUATION CIBLÉE (Compensée)
TARGET_MIN_CP = -10 # Cherche entre -0.10 et +0.10 pions
TARGET_MAX_CP = 10  
MAX_ATTEMPTS = 5000 

# Déséquilibre Matériel Sévère
MIN_MATERIAL_DIFFERENCE = 3.0 
MIN_PIECE_DIFFERENCE = 1 

MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

# PIÈCES DISPONIBLES POUR LA GÉNÉRATION ALÉATOIRE
PIECES_TO_GENERATE = [
    chess.ROOK, chess.ROOK, chess.KNIGHT, chess.KNIGHT, chess.BISHOP, chess.BISHOP, chess.QUEEN, 
    chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN
] 


# --- Fonctions de Génération Aléatoire et Légalité ---

def generate_pure_random_fen():
    """Génère une FEN aléatoire en plaçant les pièces sur l'échiquier."""
    board = chess.Board(None) # Plateau vide

    # 1. Placer les Rois
    king_squares = random.sample(chess.SQUARES, 2)
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))

    # 2. Placer les autres pièces aléatoirement
    available_squares = list(set(chess.SQUARES) - set(king_squares))
    random.shuffle(available_squares)
    
    num_pieces_to_place = random.randint(10, len(PIECES_TO_GENERATE) * 2) 
    pieces_to_place = random.sample(PIECES_TO_GENERATE * 2, num_pieces_to_place)
    
    white_turn = random.choice([True, False])
    
    for piece_type in pieces_to_place:
        if not available_squares:
            break
            
        square = available_squares.pop()
        color = random.choice([chess.WHITE, chess.BLACK])
        
        # Les pions ne doivent pas être sur la 1ère ou 8ème rangée
        if piece_type == chess.PAWN:
            if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                continue

        board.set_piece_at(square, chess.Piece(piece_type, color))

    # 3. Finaliser la FEN
    fen_parts = board.fen().split(' ')
    fen_parts[1] = 'w' if white_turn else 'b' # Le trait
    fen_parts[2] = '-' # Droits de roque
    fen_parts[3] = '-' # En passant
    fen_parts[4] = '0'
    fen_parts[5] = str(random.randint(10, 50))

    return ' '.join(fen_parts)


def is_fen_legal(fen: str):
    """Vérifie si une FEN est valide et ne commence pas par un échec."""
    try:
        board = chess.Board(fen)
        
        # 1. Vérification de la légalité de base
        if not board.is_valid():
            return False, None
            
        # 2. Rejet des positions qui commencent par un échec
        if board.is_check():
            return False, None
            
        return True, board
        
    except ValueError:
        return False, None


# --- Fonctions de Vérification Matérielle ---

def calculate_material_value(board: chess.Board):
    """Calcule la valeur matérielle totale pour chaque couleur."""
    white_material = 0
    black_material = 0
    for piece_type, value in MATERIAL_VALUES.items():
        white_material += len(board.pieces(piece_type, chess.WHITE)) * value
        black_material += len(board.pieces(piece_type, chess.BLACK)) * value
    return white_material, black_material


def is_material_compensated(board: chess.Board, min_diff: float):
    """Vérifie si la différence matérielle totale est suffisante."""
    white_mat, black_mat = calculate_material_value(board)
    difference = abs(white_mat - black_mat)
    return difference >= min_diff, white_mat, black_mat


def check_piece_difference(board: chess.Board, min_piece_diff: int):
    """Vérifie s'il y a une différence nette d'au moins 1 pièce majeure/mineure."""
    
    white_majors = len(board.pieces(chess.ROOK, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.WHITE))
    black_majors = len(board.pieces(chess.ROOK, chess.BLACK)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    major_diff = abs(white_majors - black_majors)
    
    white_minors = len(board.pieces(chess.KNIGHT, chess.WHITE)) + len(board.pieces(chess.BISHOP, chess.WHITE))
    black_minors = len(board.pieces(chess.KNIGHT, chess.BLACK)) + len(board.pieces(chess.BISHOP, chess.BLACK))
    minor_diff = abs(white_minors - black_minors)
    
    if major_diff >= min_piece_diff or minor_diff >= min_piece_diff:
        return True
    return False


# --- Fonction d'Évaluation Stockfish (avec détection de nulle) ---

def get_stockfish_evaluation(fen: str):
    """Obtient l'évaluation Stockfish et détecte une potentielle nulle forcée."""
    engine = None
    try:
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        board = chess.Board(fen)
        
        # Analyser les 3 meilleurs coups pour la détection de nulle
        info_list = engine.analyse(board, chess.engine.Limit(depth=STOCKFISH_DEPTH), multipv=3)
        
        # L'évaluation principale
        info = info_list[0]
        score = info["score"].white()
        
        # --- LOGIQUE DE VÉRIFICATION DE NULLE ---
        # Si tous les 3 meilleurs coups sont évalués comme neutres (dans la marge de cible),
        # on rejette la position car elle mène probablement à une nulle forcée ou passive.
        null_count = 0
        for item in info_list:
            item_score = item["score"].white()
            # Vérifie si c'est un Mat (is_mate) ou si c'est très proche de zéro
            if not item_score.is_mate() and abs(item_score.cp) <= TARGET_MAX_CP: 
                null_count += 1

        is_forced_draw = (null_count == len(info_list))
        # --- Fin de la vérification de Nulle ---
        
        if score.is_mate():
            evaluation_str = f"Mat en {score.mate()}"
            evaluation_cp = 99999 if score.mate() > 0 else -99999
        else:
            evaluation_cp = score.cp
            evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
        return evaluation_str, evaluation_cp, is_forced_draw
        
    except Exception as e:
        # En cas d'erreur Stockfish, on suppose qu'il y a un problème (nulle ou illégale)
        return None, None, True 
    finally:
        if engine:
            engine.quit()

# --- Script Principal : Boucle de Filtrage Strict ---

if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    
    print("--- Générateur de Déséquilibre Matériel SÉVÈRE et Compensé ---")
    print(f"Objectif : Évaluation {TARGET_MIN_CP/100:.2f} à {TARGET_MAX_CP/100:.2f} (Pas de nulle forcée).")
    print(f"Critères : (Matériel Total >= {MIN_MATERIAL_DIFFERENCE}) ET (Différence de Pièce Majeure/Mineure >= {MIN_PIECE_DIFFERENCE}).")
    print("-" * 80)
    
    start_time = time.time()
    
    while not fen_trouvee and tentatives < MAX_ATTEMPTS:
        tentatives += 1
        
        # 1. Génération Aléatoire Pure
        fen = generate_pure_random_fen()
        
        # 2. Vérification de la Légalité Stricte et de l'Échec Initial
        is_legal, board = is_fen_legal(fen)
        
        if not is_legal:
            print(f"Tentative {tentatives}: Illégale ou en Échec. Retente...", end='\r')
            continue
            
        # 3. VÉRIFICATION DU MATÉRIEL TOTAL
        is_compensated_mat, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
        
        # 4. VÉRIFICATION DE LA DIFFÉRENCE DE PIÈCES
        is_compensated_piece = check_piece_difference(board, MIN_PIECE_DIFFERENCE)
        
        # Si les deux conditions matérielles sont remplies...
        if is_compensated_mat and is_compensated_piece:
            
            # 5. Évaluation Stockfish (lent) + détection de nulle
            evaluation_str, evaluation_cp, is_forced_draw = get_stockfish_evaluation(fen)
            
            # Rejet si le jeu mène probablement à une nulle
            if is_forced_draw:
                print(f"Tentative {tentatives}: Éval OK, mais mène probablement à une nulle forcée. Retente...", end='\r')
                continue
            
            if evaluation_cp is not None and TARGET_MIN_CP <= evaluation_cp <= TARGET_MAX_CP:
                # 6. Succès ! Toutes les conditions sont remplies.
                fen_trouvee = True
                
                print("\n✅ POSITION ALÉATOIRE COMPENSÉE TROUVÉE !")
                print(f"FEN : {fen}")
                print(f"Matériel Blanc: {white_mat}, Matériel Noir: {black_mat}. Différence: {abs(white_mat - black_mat)} points.")
                print(f"Tour au trait : {'Blanc' if board.turn == chess.WHITE else 'Noir'}")
                print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
                print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
                
            else:
                print(f"Tentative {tentatives}: Éval: {evaluation_str}. Retente...", end='\r')
        
        else:
            # Matériel ou différence de pièces insuffisante
            print(f"Tentative {tentatives}: Matériel insuffisant. Diff. Mat: {abs(white_mat - black_mat)}. Retente...", end='\r')
            
    if not fen_trouvee:
        print("\n\n❌ ÉCHEC : La position n'a pas été trouvée après le nombre maximal de tentatives.")
