import chess
import chess.engine
import random
import os
import sys
import time

# Détection automatique du système d'exploitation
if os.name == 'nt':  # Windows
    STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "..", "engine", "stockfish-windows-x86-64-avx2.exe")
else:  # Linux/Unix (Elastic Beanstalk)
    STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "..", "engine", "stockfish")

# Vérification au démarrage
if not os.path.exists(STOCKFISH_PATH):
    print(f"ATTENTION: Stockfish non trouvé à {STOCKFISH_PATH}", file=sys.stderr)
else:
    print(f"INFO: Stockfish trouvé à {STOCKFISH_PATH}", file=sys.stderr)

STOCKFISH_DEPTH = 30
STOCKFISH_TIME_LIMIT = 0.5

MAX_MATERIAL_PER_SIDE = 22
MIN_MATERIAL_DIFFERENCE = 3.0
MIN_PIECE_DIFFERENCE = 1

MATERIAL_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

def generate_pieces_with_imbalance():
    """Génère une liste de pièces garantissant un déséquilibre matériel."""
    strong_side_material = random.randint(17, 22)
    weak_side_material = strong_side_material - random.randint(3, 6)
    
    pieces_strong = []
    pieces_weak = []
    
    for pieces_list, target_material in [(pieces_strong, strong_side_material), 
                                          (pieces_weak, weak_side_material)]:
        current = 0
        available = [chess.QUEEN, chess.ROOK, chess.ROOK, chess.BISHOP, chess.BISHOP,
                     chess.KNIGHT, chess.KNIGHT, chess.PAWN, chess.PAWN, chess.PAWN,
                     chess.PAWN, chess.PAWN, chess.PAWN]
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

def generate_optimized_random_fen():
    """Génère une FEN avec déséquilibre matériel intégré."""
    board = chess.Board(None)
    
    king_squares = random.sample(chess.SQUARES, 2)
    while chess.square_distance(king_squares[0], king_squares[1]) < 2:
        king_squares = random.sample(chess.SQUARES, 2)
    
    board.set_piece_at(king_squares[0], chess.Piece(chess.KING, chess.WHITE))
    board.set_piece_at(king_squares[1], chess.Piece(chess.KING, chess.BLACK))
    
    available_squares = list(set(chess.SQUARES) - set(king_squares))
    random.shuffle(available_squares)
    
    pieces_strong, pieces_weak = generate_pieces_with_imbalance()
    
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

def get_stockfish_evaluation_batch(engine: chess.engine.SimpleEngine, fens: list):
    """Évalue plusieurs positions en batch."""
    results = []
    for fen in fens:
        try:
            board = chess.Board(fen)
            info = engine.analyse(board, 
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
    
    return results

def generate_fen_position(target_min=25, target_max=100, max_attempts=20000):
    """Fonction principale appelée par l'API"""
    engine = None
    start_time = time.time()
    tentatives = 0
    
    try:
        if not os.path.exists(STOCKFISH_PATH):
            raise Exception(f"Stockfish non trouvé: {STOCKFISH_PATH}")
        
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        
        BATCH_SIZE = 5
        candidates_buffer = []
        
        while tentatives < max_attempts:
            tentatives += 1
            
            fen, board = generate_optimized_random_fen()
            is_legal, board = is_fen_legal((fen, board))
            
            if not is_legal:
                continue
            
            is_compensated_mat, white_mat, black_mat = is_material_compensated(board, MIN_MATERIAL_DIFFERENCE)
            is_compensated_piece = check_piece_difference(board, MIN_PIECE_DIFFERENCE)
            
            if is_compensated_mat and is_compensated_piece:
                candidates_buffer.append((fen, board, white_mat, black_mat))
                
                if len(candidates_buffer) >= BATCH_SIZE:
                    fens_to_analyze = [c[0] for c in candidates_buffer]
                    results = get_stockfish_evaluation_batch(engine, fens_to_analyze)
                    
                    for (fen, board, w_mat, b_mat), (scores_cp, scores_str) in zip(candidates_buffer, results):
                        if scores_cp and len(scores_cp) >= 2:
                            valid_count = sum(1 for cp in scores_cp[:2] 
                                            if (target_min <= cp <= target_max) or
                                               (-target_max <= cp <= -target_min))
                            
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
        if engine:
            engine.quit()
