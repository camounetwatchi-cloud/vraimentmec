import json
import time
import sys
from pathlib import Path

# --- Configuration des chemins (essentiel) ---
# Ajoute le dossier courant au path pour que l'import fonctionne
# et que le script 'chess_generator' trouve bien ses dépendances (Stockfish)
# en utilisant sa propre logique de 'BASE_DIR'.
CURRENT_DIR = Path(__file__).parent
sys.path.append(str(CURRENT_DIR))

# On importe la fonction principale de VOTRE script
try:
    from chess_generator import generate_fen_position
except ImportError as e:
    print(f"ERREUR: Impossible d'importer 'chess_generator'.")
    print(f"Assurez-vous que ce script est dans le même dossier que 'chess_generator.py'.")
    print(f"Détail : {e}")
    sys.exit(1)
except Exception as e:
    print(f"ERREUR lors du chargement de 'chess_generator.py' (problème Stockfish ?): {e}")
    sys.exit(1)

# --- Paramètres de la génération ---

# Le nombre de positions que vous voulez générer
NUM_POSITIONS = 50 

# Le nom du fichier qui contiendra les résultats
OUTPUT_FILENAME = "generated_positions_50.json"

# --- Exécution de la boucle ---

all_positions = []
print(f"🚀 Démarrage de la génération de {NUM_POSITIONS} positions...")
start_total_time = time.time()

for i in range(NUM_POSITIONS):
    print(f"\n--- 🔄 Génération de la position {i+1}/{NUM_POSITIONS} ---")
    
    try:
        # On appelle la fonction de votre script
        position_data = generate_fen_position() 
        
        all_positions.append(position_data)
        
        # Affiche un retour pour l'utilisateur
        print(f"✅ SUCCÈS ({position_data['time_seconds']}s) : {position_data['fen']}")
        
    except Exception as e:
        print(f"❌ ERREUR lors de la génération de la position {i+1}: {e}")
        # On continue avec la suivante
        
print("\n--- ⌛ Génération terminée ---")

# --- Sauvegarde des résultats ---

try:
    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(all_positions, f, indent=2, ensure_ascii=False)
    
    end_total_time = time.time()
    print(f"\n👍 Terminé !")
    print(f"Nombre total de positions générées : {len(all_positions)}")
    print(f"Temps total : {round(end_total_time - start_total_time, 1)} secondes")
    print(f"✅ Résultats sauvegardés dans le fichier : {OUTPUT_FILENAME}")

except Exception as e:
    print(f"❌ ERREUR lors de la sauvegarde du fichier JSON : {e}")
