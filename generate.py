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
STOCKFISH_DEPTH = 30 

# NOUVEAUX PARAMÈTRES D'ÉVALUATION CIBLÉE
TARGET_ABS_MIN_CP = 25  # 0.25 pion
TARGET_ABS_MAX_CP = 100 # 1.00 pion
MAX_ATTEMPTS = 20000 

# NOUVELLE CONTRAINTE MATÉRIELLE MAXIMALE
MAX_MATERIAL_PER_SIDE = 22

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
# Le Roi n'est pas inclus car il est placé séparément.
PIECES_TO_GENERATE = [
    chess.ROOK, chess.ROOK, chess.KNIGHT, chess.KNIGHT, chess.BISHOP, chess.BISHOP, chess.QUEEN, 
    chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN, chess.PAWN
] 


# --- Fonctions de Vérification ---

def get_square_color(square: chess.Square) -> bool:
    """Détermine la couleur de la case (True pour clair, False pour sombre)."""
    return (chess.square_rank(square) + chess.square_file(square)) % 2 == 0

def get_piece_value(piece_type: chess.PieceType) -> int:
    """Retourne la valeur matérielle de la pièce, ou 0 si non trouvée."""
    return MATERIAL_VALUES.get(piece_type, 0)


def generate_pure_random_fen():
    """
    Génère une FEN aléatoire en respectant les contraintes :
    1. Max 22 points de matériel par joueur.
    2. Pas plus d'un Fou par couleur de case et par joueur.
    """
    board = chess.Board(None)
    
    # 1. Placement des Rois
    king_squares = random.sample(chess.SQUARES, 2)
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))

    available_squares = list(set(chess.SQUARES) - set(king_squares))
    random.shuffle(available_squares)
    
    num_pieces_to_place = random.randint(10, len(PIECES_TO_GENERATE) * 2) 
    pieces_to_place = random.sample(PIECES_TO_GENERATE * 2, num_pieces_to_place)
    
    # 2. Suivi des contraintes
    current_material = {chess.WHITE: 0, chess.BLACK: 0}
    bishops_on_light = {chess.WHITE: False, chess.BLACK: False}
    bishops_on_dark = {chess.WHITE: False, chess.BLACK: False}
    
    temp_available_squares = available_squares[:]

    for piece_type in pieces_to_place:
        if not temp_available_squares:
            break
            
        piece_value = get_piece_value(piece_type)
        color = random.choice([chess.WHITE, chess.BLACK])
        valid_squares_for_placement = temp_available_squares[:]

        # --- A. APPLICATION DES CONTRAINTES DE PLACEMENT ---

        # 1. Contrainte Matérielle Maximum (Nouvelle)
        if current_material[color] + piece_value > MAX_MATERIAL_PER_SIDE:
            continue # La pièce dépasse la limite de 22 points pour ce camp

        # 2. Contrainte des Pions
        if piece_type == chess.PAWN:
            valid_squares_for_placement = [sq for sq in valid_squares_for_placement if chess.square_rank(sq) not in (0, 7)]
        
        # 3. Contrainte des Fous
        elif piece_type == chess.BISHOP:
            allowed_squares_for_bishop = []
            
            if not bishops_on_light[color]:
                allowed_squares_for_bishop.extend([sq for sq in valid_squares_for_placement if get_square_color(sq)])
            
            if not bishops_on_dark[color]:
                allowed_squares_for_bishop.extend([sq for sq in valid_squares_for_placement if not get_square_color(sq)])
            
            valid_squares_for_placement = allowed_squares_for_bishop

        # --- B. PLACEMENT FINAL ---

        if not valid_squares_for_placement:
            continue # Aucune case valide restante pour cette pièce
            
        # Sélection aléatoire parmi les cases valides restantes
        square = random.choice(valid_squares_for_placement)
        
        # Mise à jour du suivi pour les Fous
        if piece_type == chess.BISHOP:
            is_light = get_square_color(square)
            if is_light:
                bishops_on_light[color] = True
            else:
                bishops_on_dark[color] = True
        
        # Mise à jour du matériel
        current_material[color] += piece_value
        
        # Placer la pièce et retirer la case de la liste des cases disponibles
        board.set_piece_at(square, chess.Piece(piece_type, color))
        temp_available_squares.remove(square)

    # 3. Finalisation de la FEN
    fen_parts = board.fen().split(' ')
    white_turn = random.choice([True, False])
    fen_parts[1] = 'w' if white_turn else 'b'
    fen_parts[2] = '-' 
    fen_parts[3] = '-' 
    fen_parts[4] = '0'
    fen_parts[5] = str(random.randint(10, 50)) 

    return ' '.join(fen_parts), board


def is_fen_legal(fen_and_board: tuple):
    """Vérifie si une FEN est valide et ne commence pas par un échec."""
    fen, board = fen_and_board
    try:
        # Les contraintes Matérielles et Fous sont garanties par la fonction de génération
        
        if not board.is_valid():
            return False, None
            
        if board.is_check():
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


# --- Fonction d'Évaluation Stockfish (multipv=2) ---

def get_stockfish_evaluation(engine: chess.engine.SimpleEngine, fen: str):
    """Obtient les deux premières évaluations (multipv=2) Stockfish pour une FEN donnée."""
    try:
        board = chess.Board(fen)
        
        # Utiliser multipv=2 pour obtenir au moins deux lignes
        info = engine.analyse(board, chess.engine.Limit(depth=STOCKFISH_DEPTH), multipv=2)
        
        scores_cp = []
        scores_str = []
        
        # Extraire les scores des 2 meilleures lignes
        for pv_info in info: 
            score = pv_info["score"].white() 
            
            if score.is_mate():
                evaluation_cp = 99999 if score.mate() > 0 else -99999
                evaluation_str = f"Mat en {score.mate()}"
            else:
                evaluation_cp = score.cp
                evaluation_str = f"{evaluation_cp / 100.0:+.2f} Pions"
            
            scores_cp.append(evaluation_cp)
            scores_str.append(evaluation_str)

        return scores_cp, scores_str
        
    except Exception as e:
        return None, None 


# --- Script Principal : Boucle de Filtrage pour Avantage Léger Décisif ---

if __name__ == "__main__":
    
    fen_trouvee = False
    tentatives = 0
    engine = None 
    
    print("--- Générateur de Déséquilibre Matériel SÉVÈRE avec double Ligne d'Analyse (Optimisé) ---")
    print(f"Objectif : **AU MOINS 2 LIGNES** évaluées dans la plage [{-TARGET_ABS_MAX_CP/100:.2f} à -{-TARGET_ABS_MIN_CP/100:.2f}] OU [{TARGET_ABS_MIN_CP/100:.2f} à {TARGET_ABS_MAX_CP/100:.2f}].")
    print(f"Critères : (Matériel Total >= {MIN_MATERIAL_DIFFERENCE}) ET (Différence de Pièce Majeure/Mineure >= {MIN_PIECE_DIFFERENCE}).")
    print(f"**Contrainte** : Matériel Max par joueur : {MAX_MATERIAL_PER_SIDE} points. Garantie par la génération.")
    print(f"**Contrainte** : Unicité de la couleur des Fous. Garantie par la génération.")
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
            
            # 1. Génération Aléatoire Pure (qui garantit maintenant Fous et Matériel Max)
            fen, board = generate_pure_random_fen()
            
            # 2. Vérification de la Légalité Stricte et de l'Échec Initial
            is_legal, board = is_fen_legal((fen, board))
            
            if not is_legal:
                print(f"Tentative {tentatives}: Illégale ou en Échec. Retente...", end='\r')
                continue
                
            # 3. VÉRIFICATION DU MATÉRIEL TOTAL ET DES PIÈCES
            is_compensated_mat, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
            is_compensated_piece = check_piece_difference(board, MIN_PIECE_DIFFERENCE)
            
            if is_compensated_mat and is_compensated_piece:
                
                # 4. Évaluation Stockfish (multipv=2)
                evaluation_cps, evaluation_strs = get_stockfish_evaluation(engine, fen)
                
                valid_lines_count = 0
                
                if evaluation_cps is not None and len(evaluation_cps) >= 2:
                    
                    # On vérifie si au moins 2 des lignes tombent dans la plage cible
                    for cp_score in evaluation_cps[:2]: 
                        
                        # Plage Avantage Blanc (+0.25 à +1.00)
                        in_white_range = TARGET_ABS_MIN_CP <= cp_score <= TARGET_ABS_MAX_CP
                        # Plage Avantage Noir (-1.00 à -0.25)
                        in_black_range = -TARGET_ABS_MAX_CP <= cp_score <= -TARGET_ABS_MIN_CP
                        
                        if in_white_range or in_black_range:
                            valid_lines_count += 1
                
                
                if valid_lines_count >= 2:
                    # 5. Succès ! Toutes les conditions sont remplies.
                    fen_trouvee = True
                    
                    print("\n" + "—" * 80)
                    print("✅ POSITION AVEC DÉSÉQUILIBRE MATÉRIEL ET DOUBLE LIGNE JOUABLE TROUVÉE !")
                    print(f"FEN : {fen}")
                    print(f"Matériel Blanc: {white_mat}, Matériel Noir: {black_mat}. Différence: {abs(white_mat - black_mat)} points.")
                    print(f"Tour au trait : {'Blanc' if board.turn == chess.WHITE else 'Noir'}")
                    print(f"Évaluation Ligne 1 (dép. {STOCKFISH_DEPTH}) : {evaluation_strs[0]}")
                    print(f"Évaluation Ligne 2 (dép. {STOCKFISH_DEPTH}) : {evaluation_strs[1]}")
                    print(f"Trouvé en {tentatives} tentatives (Temps écoulé : {time.time() - start_time:.2f}s)")
                    print("—" * 80)
                    
                else:
                    first_score = evaluation_strs[0] if evaluation_strs and len(evaluation_strs) > 0 else "N/A"
                    second_score = evaluation_strs[1] if evaluation_strs and len(evaluation_strs) > 1 else "N/A"
                    print(f"Tentative {tentatives}: Ligne 1: {first_score}, Ligne 2: {second_score}. Retente...", end='\r')
            
            else:
                print(f"Tentative {tentatives}: Matériel insuffisant. Diff. Mat: {abs(white_mat - black_mat)}. Retente...", end='\r')
                
        if not fen_trouvee:
            print("\n\n❌ ÉCHEC : La position n'a pas été trouvée après le nombre maximal de tentatives.")
            
    finally:
        # ÉTAPE CRITIQUE : FERMER STOCKFISH UNE SEULE FOIS
        if engine:
            engine.quit()
            print("Moteur Stockfish fermé.")
