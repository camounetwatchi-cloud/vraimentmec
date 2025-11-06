import chess
import chess.engine
import random
import os
import sys
import time
from pathlib import Path

# --- CORRECTION CRITIQUE DU CHEMIN ---
BASE_DIR = Path(__file__).parent.parent

if os.name == 'nt':  # Windows
    STOCKFISH_EXECUTABLE = "stockfish-windows-x86-64-avx2.exe"
    STOCKFISH_PATH = BASE_DIR / "stockfish" / STOCKFISH_EXECUTABLE
else:  # Linux/Unix
    STOCKFISH_EXECUTABLE = "stockfish"  # NOM SIMPLIFIÉ
    STOCKFISH_PATH = BASE_DIR / "stockfish" / STOCKFISH_EXECUTABLE

STOCKFISH_PATH = str(STOCKFISH_PATH)

# Vérification au démarrage
if not os.path.exists(STOCKFISH_PATH):
    print(f"ATTENTION: Stockfish non trouvé à {STOCKFISH_PATH}", file=sys.stderr)
elif not os.access(STOCKFISH_PATH, os.X_OK):
    print(f"ATTENTION: Stockfish n'est pas exécutable à {STOCKFISH_PATH}", file=sys.stderr)
    # Tenter de le rendre exécutable
    try:
        os.chmod(STOCKFISH_PATH, 0o755)
        print(f"✅ Permissions corrigées pour {STOCKFISH_PATH}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Impossible de corriger les permissions: {e}", file=sys.stderr)
else:
    print(f"INFO: Stockfish trouvé et exécutable à {STOCKFISH_PATH}", file=sys.stderr)

# --- FIN DE LA CORRECTION CRITIQUE ---

STOCKFISH_DEPTH = 26
STOCKFISH_TIME_LIMIT = 0.5

MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

# --- Initialisation du moteur Stockfish (à l'extérieur de la fonction generate_fen_position) ---
# On tente de l'initialiser une fois pour toutes.
engine = None
try:
    if os.path.exists(STOCKFISH_PATH):
        # Utilisation de SimpleEngine.popen_uci pour l'initialisation
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        # Définir les options du moteur (si nécessaire, mais souvent non nécessaire pour SimpleEngine)
        # engine.configure({"Threads": 2, "Hash": 1024}) 
    else:
        print("ERREUR FATALE: Le moteur Stockfish n'existe pas ou le chemin est incorrect.", file=sys.stderr)
except Exception as e:
    print(f"ERREUR lors de l'initialisation de l'Engine Stockfish: {e}", file=sys.stderr)
    engine = None

# --- Reste des fonctions (inchangées, sauf l'appel à l'engine) ---

def generate_pieces_with_imbalance(max_material, material_diff, excluded_pieces=None):
    """Génère une liste de pièces garantissant un déséquilibre matériel.
    
    Args:
        max_material: Matériel maximum par côté
        material_diff: Différence matérielle entre les camps
        excluded_pieces: Liste des types de pièces à exclure (ex: ['queen', 'rook'])
    """
    if excluded_pieces is None:
        excluded_pieces = []
    
    # Convertir les noms en types chess
    piece_mapping = {
        'queen': chess.QUEEN,
        'rook': chess.ROOK,
        'bishop': chess.BISHOP,
        'knight': chess.KNIGHT,
        'pawn': chess.PAWN
    }
    
    excluded_types = [piece_mapping.get(p) for p in excluded_pieces if p in piece_mapping]
    
    # Calculer les limites basées sur les paramètres
    max_strong = min(max_material, 22)
    min_weak = max(10, max_strong - 6)
    
    strong_side_material = random.randint(max_strong - 3, max_strong)
    
    if material_diff == 0:
        weak_side_material = strong_side_material
    else:
        weak_side_material = strong_side_material - random.randint(material_diff, min(material_diff + 2, 6))
    
    weak_side_material = max(weak_side_material, 10)
    
    pieces_strong = []
    pieces_weak = []
    
    for pieces_list, target_material in [(pieces_strong, strong_side_material), 
                                         (pieces_weak, weak_side_material)]:
        current = 0
        # Créer la liste des pièces disponibles en excluant celles filtrées
        available = []
        
        if chess.QUEEN not in excluded_types:
            available.append(chess.QUEEN)
        if chess.ROOK not in excluded_types:
            available.extend([chess.ROOK, chess.ROOK])
        if chess.BISHOP not in excluded_types:
            available.extend([chess.BISHOP, chess.BISHOP])
        if chess.KNIGHT not in excluded_types:
            available.extend([chess.KNIGHT, chess.KNIGHT])
        if chess.PAWN not in excluded_types:
            available.extend([chess.PAWN] * 6)
        
        # Si aucune pièce n'est disponible, lever une erreur
        if not available:
            raise ValueError("Impossible de générer une position : toutes les pièces sont exclues")
        
        random.shuffle(available)
        
        for piece in available:
            value = MATERIAL_VALUES[piece]
            if current + value <= target_material:
                pieces_list.append(piece)
                current += value
            if current >= target_material - 1:
                break
    
    return pieces_strong, pieces_weak

def get_square_color(square: chess.Square) -> bool:
    """Détermine la couleur de la case."""
    return (chess.square_rank(square) + chess.square_file(square)) % 2 == 0

def generate_optimized_random_fen(max_material, material_diff, excluded_pieces=None):
    """Génère une FEN avec déséquilibre matériel intégré.
    
    Args:
        max_material: Matériel maximum par côté
        material_diff: Différence matérielle
        excluded_pieces: Liste des pièces à exclure
    """
    board = chess.Board(None)
    
    king_squares = random.sample(chess.SQUARES, 2)
    while chess.square_distance(king_squares[0], king_squares[1]) < 2:
        king_squares = random.sample(chess.SQUARES, 2)
    
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))
    
    available_squares = list(set(chess.SQUARES) - set(king_squares))
    random.shuffle(available_squares)
    
    pieces_strong, pieces_weak = generate_pieces_with_imbalance(max_material, material_diff, excluded_pieces)
    
    if random.choice([True, False]):
        white_pieces, black_pieces = pieces_strong, pieces_weak
    else:
        white_pieces, black_pieces = pieces_weak, pieces_strong
    
    bishops_on_light = {chess.WHITE: False, chess.BLACK: False}
    bishops_on_dark = {chess.WHITE: False, chess.BLACK: False}
    
    for color, pieces_list in [(chess.WHITE, white_pieces), (chess.BLACK, black_pieces)]:
        for piece_type in pieces_list:
            if not available_squares:
                break
            
            valid_squares = available_squares[:]
            
            if piece_type == chess.PAWN:
                valid_squares = [sq for sq in valid_squares if chess.square_rank(sq) not in (0, 7)]
            
            elif piece_type == chess.BISHOP:
                allowed = []
                if not bishops_on_light[color]:
                    allowed.extend([sq for sq in valid_squares if get_square_color(sq)])
                if not bishops_on_dark[color]:
                    allowed.extend([sq for sq in valid_squares if not get_square_color(sq)])
                valid_squares = allowed
            
            if not valid_squares:
                continue
            
            square = random.choice(valid_squares)
            
            if piece_type == chess.BISHOP:
                if get_square_color(square):
                    bishops_on_light[color] = True
                else:
                    bishops_on_dark[color] = True
            
            board.set_piece_at(square, chess.Piece(piece_type, color))
            available_squares.remove(square)
    
    fen_parts = board.fen().split(' ')
    white_turn = random.choice([True, False])
    fen_parts[1] = 'w' if white_turn else 'b'
    fen_parts[2] = '-'
    fen_parts[3] = '-'
    fen_parts[4] = '0'
    fen_parts[5] = str(random.randint(10, 50))
    
    return ' '.join(fen_parts), board

def is_fen_legal(fen_and_board: tuple):
    """Vérifie légalité basique."""
    fen, board = fen_and_board
    try:
        if not board.is_valid():
            return False, None
        if board.is_check():
            return False, None
        return True, board
    except ValueError:
        return False, None

def calculate_material_value(board: chess.Board):
    """Calcule valeur matérielle par couleur."""
    white_material = sum(len(board.pieces(pt, chess.WHITE)) * val 
                         for pt, val in MATERIAL_VALUES.items())
    black_material = sum(len(board.pieces(pt, chess.BLACK)) * val 
                         for pt, val in MATERIAL_VALUES.items())
    return white_material, black_material

def is_material_compensated(board: chess.Board, min_diff: float):
    """Vérifie déséquilibre matériel."""
    white_mat, black_mat = calculate_material_value(board)
    difference = abs(white_mat - black_mat)
    
    # Si min_diff est 0, accepter toute position
    if min_diff == 0:
        return True, white_mat, black_mat
    
    return difference >= min_diff, white_mat, black_mat

def check_piece_difference(board: chess.Board, min_piece_diff: int):
    """Vérifie différence de pièces."""
    white_majors = (len(board.pieces(chess.ROOK, chess.WHITE)) + 
                    len(board.pieces(chess.QUEEN, chess.WHITE)))
    black_majors = (len(board.pieces(chess.ROOK, chess.BLACK)) + 
                    len(board.pieces(chess.QUEEN, chess.BLACK)))
    major_diff = abs(white_majors - black_majors)
    
    white_minors = (len(board.pieces(chess.KNIGHT, chess.WHITE)) + 
                    len(board.pieces(chess.BISHOP, chess.WHITE)))
    black_minors = (len(board.pieces(chess.KNIGHT, chess.BLACK)) + 
                    len(board.pieces(chess.BISHOP, chess.BLACK)))
    minor_diff = abs(white_minors - black_minors)
    
    return major_diff >= min_piece_diff or minor_diff >= min_piece_diff

def get_stockfish_evaluation_batch(fens: list):
    """Évalue plusieurs positions en batch."""
    # Utilise l'objet engine initialisé globalement
    if not engine:
        return [(None, None)] * len(fens)

    results = []
    
    # Ouvrir l'engine de nouveau pour éviter les problèmes de timeout/thread (solution plus robuste)
    temp_engine = None
    try:
        if os.path.exists(STOCKFISH_PATH):
            temp_engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        else:
             print("Engine non trouvé pour l'analyse en batch.", file=sys.stderr)
             return [(None, None)] * len(fens)
             
        for fen in fens:
            try:
                board = chess.Board(fen)
                info = temp_engine.analyse(board, 
                                          chess.engine.Limit(depth=STOCKFISH_DEPTH, 
                                                             time=STOCKFISH_TIME_LIMIT),
                                          multipv=2)
                
                if len(info) < 2:
                    results.append((None, None))
                    continue
                
                scores_cp = []
                scores_str = []
                
                for pv_info in info:
                    score = pv_info["score"].white()
                    if score.is_mate():
                        evaluation_cp = 99999 if score.mate() > 0 else -99999
                        evaluation_str = f"Mat en {score.mate()}"
                    else:
                        evaluation_cp = score.cp
                        evaluation_str = f"{evaluation_cp / 100.0:+.2f}"
                    
                    scores_cp.append(evaluation_cp)
                    scores_str.append(evaluation_str)
                
                results.append((scores_cp, scores_str))
            except Exception:
                results.append((None, None))
    finally:
        if temp_engine:
            temp_engine.quit()

    return results

def generate_fen_position(negative_min=-99, negative_max=-15, positive_min=15, positive_max=99, material_diff=3, max_material=22, max_attempts=20000, excluded_pieces=None):    """Fonction principale appelée par l'API
    
    Args:
        target_min: Évaluation minimum en centipions (0-99)
        target_max: Évaluation maximum en centipions (1-99)
        material_diff: Différence matérielle minimum (0-6)
        max_material: Matériel maximum par côté (10-25)
        max_attempts: Nombre maximum de tentatives
        excluded_pieces: Liste des types de pièces à exclure (['queen', 'rook', etc.])
    """
    global engine
    start_time = time.time()
    tentatives = 0
    
    if not engine:
        raise Exception(f"Le moteur Stockfish n'est pas initialisé. Chemin: {STOCKFISH_PATH}")
    
    # Validation des paramètres
    if target_min < 0 or target_min > 99:
        raise ValueError("target_min doit être entre 0 et 99")
    if target_max < 1 or target_max > 99:
        raise ValueError("target_max doit être entre 1 et 99")
    if target_min >= target_max:
        raise ValueError("target_min doit être inférieur à target_max")
    if material_diff < 0 or material_diff > 6:
        raise ValueError("material_diff doit être entre 0 et 6")
    if max_material < 10 or max_material > 25:
        raise ValueError("max_material doit être entre 10 et 25")
    
    if excluded_pieces is None:
        excluded_pieces = []
    
    try:
        BATCH_SIZE = 5
        candidates_buffer = []
        
        min_piece_diff = 1 if material_diff >= 2 else 0
        
        while tentatives < max_attempts:
            tentatives += 1
            
            fen, board = generate_optimized_random_fen(max_material, material_diff, excluded_pieces)
            is_legal, board = is_fen_legal((fen, board))
            
            if not is_legal:
                continue
            
            is_compensated_mat, white_mat, black_mat = is_material_compensated(board, material_diff)
            is_compensated_piece = check_piece_difference(board, min_piece_diff)
            
            if is_compensated_mat and is_compensated_piece:
                candidates_buffer.append((fen, board, white_mat, black_mat))
                
                if len(candidates_buffer) >= BATCH_SIZE:
                    fens_to_analyze = [c[0] for c in candidates_buffer]
                    results = get_stockfish_evaluation_batch(fens_to_analyze)
                    
                    for (fen, board, w_mat, b_mat), (scores_cp, scores_str) in zip(candidates_buffer, results):
                        if scores_cp and len(scores_cp) >= 2:
                            valid_count = sum(1 for cp in scores_cp[:2] 
                  if (negative_min <= cp <= negative_max) or
                     (positive_min <= cp <= positive_max)))
                            
                            if valid_count >= 2:
                                return {
                                    "fen": fen,
                                    "white_material": w_mat,
                                    "black_material": b_mat,
                                    "material_difference": abs(w_mat - b_mat),
                                    "turn": "Blanc" if board.turn else "Noir",
                                    "eval_line1": scores_str[0],
                                    "eval_line2": scores_str[1],
                                    "attempts": tentatives,
                                    "time_seconds": round(time.time() - start_time, 1)
                                }
                    
                    candidates_buffer = []
            
        raise Exception("Position non trouvée après maximum de tentatives")
    
    finally:
    pass
