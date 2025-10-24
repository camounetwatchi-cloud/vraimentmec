// Configuration - À MODIFIER selon votre déploiement
const API_URL = 'http://localhost:5000/api'; // En local
// const API_URL = 'https://votre-backend.herokuapp.com/api'; // En production

const generateBtn = document.getElementById('generateBtn');
const btnText = document.getElementById('btnText');
const btnLoader = document.getElementById('btnLoader');
const statusDiv = document.getElementById('status');
const resultsDiv = document.getElementById('results');

// Gestionnaire du bouton de génération
generateBtn.addEventListener('click', async () => {
    const targetMin = parseInt(document.getElementById('targetMin').value);
    const targetMax = parseInt(document.getElementById('targetMax').value);
    const maxAttempts = parseInt(document.getElementById('maxAttempts').value);

    // Validation
    if (targetMin >= targetMax) {
        showStatus('Erreur: L\'évaluation min doit être inférieure à l\'évaluation max', 'error');
        return;
    }

    // Désactiver le bouton et afficher le loader
    generateBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoader.style.display = 'inline-block';
    resultsDiv.classList.add('hidden');
    showStatus('Génération en cours... Cela peut prendre jusqu\'à 2 minutes.', 'info');

    try {
        const response = await fetch(`${API_URL}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                target_min: targetMin,
                target_max: targetMax,
                max_attempts: maxAttempts
            })
        });

        const result = await response.json();

        if (result.success) {
            displayResults(result.data);
            showStatus('✅ Position générée avec succès !', 'success');
        } else {
            showStatus(`❌ Erreur: ${result.error}`, 'error');
        }
    } catch (error) {
        showStatus(`❌ Erreur de connexion: ${error.message}. Vérifiez que le backend est démarré.`, 'error');
    } finally {
        // Réactiver le bouton
        generateBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoader.style.display = 'none';
    }
});

// Afficher les résultats
function displayResults(data) {
    document.getElementById('fenText').textContent = data.fen;
    document.getElementById('whiteMaterial').textContent = data.white_material;
    document.getElementById('blackMaterial').textContent = data.black_material;
    document.getElementById('materialDiff').textContent = data.material_difference;
    document.getElementById('turn').textContent = data.turn;
    document.getElementById('evalLine1').textContent = data.eval_line1;
    document.getElementById('evalLine2').textContent = data.eval_line2;
    document.getElementById('attempts').textContent = data.attempts.toLocaleString();
    document.getElementById('timeSeconds').textContent = `${data.time_seconds}s`;

    // Liens d'analyse
    const fenEncoded = encodeURIComponent(data.fen);
    document.getElementById('lichessLink').href = `https://lichess.org/analysis/${fenEncoded}`;
    document.getElementById('chesscomLink').href = `https://www.chess.com/analysis?fen=${fenEncoded}`;

    resultsDiv.classList.remove('hidden');
}

// Afficher un message de statut
function showStatus(message, type) {
    statusDiv.textContent = message;
    statusDiv.className = `status ${type}`;
    statusDiv.classList.remove('hidden');
}

// Copier la FEN dans le presse-papiers
function copyFEN() {
    const fenText = document.getElementById('fenText').textContent;
    navigator.clipboard.writeText(fenText).then(() => {
        const btn = event.target;
        const originalText = btn.textContent;
        btn.textContent = '✅ Copié !';
        setTimeout(() => {
            btn.textContent = originalText;
        }, 2000);
    }).catch(err => {
        alert('Erreur lors de la copie: ' + err);
    });
}
