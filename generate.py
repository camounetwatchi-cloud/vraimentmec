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
# Profondeur augmentée pour une meilleure stabilité/précision de l'évaluation
STOCKFISH_DEPTH = 30

# PARAMÈTRES D'ÉVALUATION CIBLÉE (Avantage léger décisif)
TARGET_ABS_MIN_CP = 30  
TARGET_ABS_MAX_CP = 150 
MAX_ATTEMPTS = 20000 

# Déséquilibre Matériel Sévère (inchangé)
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
    board = chess.Board(None)
    king_squares = random.sample(chess.SQUARES, 2)
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))

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
        
        if piece_type == chess.PAWN:
            if chess.square_rank(square) == 0 or chess.square_rank(square) == 7:
                continue

        board.set_piece_at(square, chess.Piece(piece_type, color))

    fen_parts = board.fen().split(' ')
    fen_parts[1] = 'w' if white_turn else 'b'
    fen_parts[2] = '-' 
    fen_parts[3] = '-' 
    fen_parts[4] = '0'
    fen_parts[5] = str(random.randint(10, 50))

    return ' '.join(fen_parts)

def has_two_bishops_of_same_color(board: chess.Board, color: bool) -> bool:
    """Vérifie si le joueur 'color' a deux fous sur des cases de la même couleur."""
    
    bishop_squares = board.pieces(chess.BISHOP, color)
    if len(bishop_squares) < 2:
        return False

    # Couleur des cases : True pour clair (Blanc), False pour sombre (Noir)
    square_colors = [chess.square_color(sq) for sq in bishop_squares]

    # Compter le nombre de Fous sur cases claires et le nombre sur cases sombres
    light_square_bishops = sum(square_colors)
    dark_square_bishops = len(square_colors) - light_square_bishops
    
    # Si le joueur a deux fous ou plus sur des cases CLAIRES OU deux fous ou plus sur des cases SOMBRE,
    # cela signifie qu'il a deux fous de "même couleur" (par rapport à la case).
    if light_square_bishops >= 2 or dark_square_bishops >= 2:
        return True
    
    return False


def is_fen_legal(fen: str):
    """Vérifie si une FEN est valide, ne commence pas par un échec, et respecte la contrainte des Fous."""
    try:
        board = chess.Board(fen)
        
        if not board.is_valid():
            return False, None
            
        if board.is_check():
            return False, None
            
        # NOUVELLE CONTRAINTE : Vérifier les Fous Blancs et Noirs
        if has_two_bishops_of_same_color(board, chess.WHITE) or has_two_bishops_of_same_color(board, chess.BLACK):
            return False, None
            
        return True, board
        
    except ValueError:
        return False, None


# --- Fonctions de Vérification Matérielle (Inchangées) ---

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


# --- Fonction d'Évaluation Stockfish (Stabilisée, Inchangée) ---

def get_stockfish_evaluation(engine: chess.engine.SimpleEngine, fen: str):
    """Obtient l'évaluation Stockfish pour une FEN donnée en utilisant le moteur PRÉ-OUVERT."""
    try:
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


# --- Script Principal : Boucle de Filtrage pour Avantage Léger Décisif ---

if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    engine = None 
    
    print("--- Générateur de Déséquilibre Matériel SÉVÈRE avec Avantage Léger Décisif (Stabilisé) ---")
    print(f"Objectif : Évaluation [{-TARGET_ABS_MAX_CP/100:.2f} à -{-TARGET_ABS_MIN_CP/100:.2f}] OU [{TARGET_ABS_MIN_CP/100:.2f} à {TARGET_ABS_MAX_CP/100:.2f}].")
    print(f"Critères : (Matériel Total >= {MIN_MATERIAL_DIFFERENCE}) ET (Différence de Pièce Majeure/Mineure >= {MIN_PIECE_DIFFERENCE}).")
    print(f"**Contrainte** : Pas plus d'un Fou par couleur de case (par joueur).")
    print(f"Profondeur d'analyse du script : {STOCKFISH_DEPTH} demi-coups.")
    print("-" * 80)
    
    start_time = time.time()
    
    # ÉTAPE CRITIQUE : OUVRIR STOCKFISH UNE SEULE FOIS
    try:
        if not os.path.exists(STOCKFISH_PATH):
             print(f"\nERREUR FATALE: Fichier Stockfish non trouvé à l'emplacement: {STOCKFISH_PATH}")
             exit()

        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        print("Moteur Stockfish démarré avec succès. Début du filtrage...")

    except Exception as e:
        print(f"\nERREUR FATALE: Impossible de démarrer Stockfish: {e}")
        exit()


    try:
        while not fen_trouvee and tentatives < MAX_ATTEMPTS:
            tentatives += 1
            
            # 1. Génération Aléatoire Pure
            fen = generate_pure_random_fen()
            
            # 2. Vérification de la Légalité Stricte, de l'Échec Initial et des FOUS
            is_legal, board = is_fen_legal(fen)
            
            if not is_legal:
                print(f"Tentative {tentatives}: Illégale, en Échec, ou 2 Fous même couleur. Retente...", end='\r')
                continue
                
            # 3. VÉRIFICATION DU MATÉRIEL TOTAL ET DES PIÈCES
            is_compensated_mat, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
            is_compensated_piece = check_piece_difference(board, MIN_PIECE_DIFFERENCE)
            
            if is_compensated_mat and is_compensated_piece:
                
                # 4. Évaluation Stockfish (lent) - Passage du moteur PRÉ-OUVERT
                evaluation_str, evaluation_cp = get_stockfish_evaluation(engine, fen)
                
                # --- LOGIQUE DE FILTRAGE : VÉRIFICATION DES DEUX PLAGES D'AVANTAGE ---
                is_in_target_range = False
                
                if evaluation_cp is not None:
                    # Plage Avantage Blanc (+0.30 à +1.50)
                    if TARGET_ABS_MIN_CP <= evaluation_cp <= TARGET_ABS_MAX_CP:
                        is_in_target_range = True
                    # Plage Avantage Noir (-1.50 à -0.30)
                    elif -TARGET_ABS_MAX_CP <= evaluation_cp <= -TARGET_ABS_MIN_CP:
                        is_in_target_range = True
                
                if is_in_target_range:
                    # 5. Succès ! Toutes les conditions sont remplies.
                    fen_trouvee = True
                    
                    print("\n" + "—" * 80)
                    print("✅ POSITION ALÉATOIRE AVEC AVANTAGE LÉGER DÉCISIF TROUVÉE !")
                    print(f"FEN : {fen}")
                    print(f"Matériel Blanc: {white_mat}, Matériel Noir: {black_mat}. Différence: {abs(white_mat - black_mat)} points.")
                    print(f"Tour au trait : {'Blanc' if board.turn == chess.WHITE else 'Noir'}")
                    print(f"Évaluation Stockfish (dép. {STOCKFISH_DEPTH}) : {evaluation_str}")
                    print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
                    print("—" * 80)
                    
                else:
                    print(f"Tentative {tentatives}: Éval: {evaluation_str}. Retente...", end='\r')
            
            else:
                print(f"Tentative {tentatives}: Matériel insuffisant. Diff. Mat: {abs(white_mat - black_mat)}. Retente...", end='\r')
                
        if not fen_trouvee:
            print("\n\n❌ ÉCHEC : La position n'a pas été trouvée après le nombre maximal de tentatives.")
            
    finally:
        # ÉTAPE CRITIQUE : FERMER STOCKFISH UNE SEULE FOIS
        if engine:
            engine.quit()
            print("Moteur Stockfish fermé.")
