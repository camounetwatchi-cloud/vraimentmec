// navbar.js - Logique commune pour toutes les pages

// Configuration de l'API
const API_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? 'http://localhost:5000'
    : 'http://chessishard-env-env.eba-f8bxehfn.eu-west-1.elasticbeanstalk.com';

let navUser = null;

// Fonction pour vérifier l'authentification et mettre à jour la navbar
async function initNavbar() {
    try {
        const response = await fetch(`${API_URL}/api/auth/me`, {
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (data.success) {
            navUser = data.user;
            showAuthenticatedNavbar(navUser);
        } else {
            showUnauthenticatedNavbar();
        }
    } catch (error) {
        console.error('❌ Erreur init navbar:', error);
        showUnauthenticatedNavbar();
    }
}

// Afficher la navbar pour utilisateur connecté
function showAuthenticatedNavbar(user) {
    const navUserInfo = document.getElementById('navUserInfo');
    const navLogoutBtn = document.getElementById('navLogoutBtn');
    const navLoginBtn = document.getElementById('navLoginBtn');
    const navUsername = document.getElementById('navUsername');
    const navElo = document.getElementById('navElo');
    
    if (navUserInfo) navUserInfo.style.display = 'flex';
    if (navLogoutBtn) navLogoutBtn.style.display = 'inline-block';
    if (navLoginBtn) navLoginBtn.style.display = 'none';
    
    if (navUsername) navUsername.textContent = user.username;
    if (navElo) navElo.textContent = `ELO: ${user.elo}`;
}

// Afficher la navbar pour utilisateur non connecté
function showUnauthenticatedNavbar() {
    const navUserInfo = document.getElementById('navUserInfo');
    const navLogoutBtn = document.getElementById('navLogoutBtn');
    const navLoginBtn = document.getElementById('navLoginBtn');
    
    if (navUserInfo) navUserInfo.style.display = 'none';
    if (navLogoutBtn) navLogoutBtn.style.display = 'none';
    if (navLoginBtn) navLoginBtn.style.display = 'inline-block';
}

// Gérer la déconnexion
async function handleNavLogout() {
    if (!confirm('Voulez-vous vraiment vous déconnecter ?')) {
        return;
    }

    try {
        // Mettre le joueur hors ligne si la fonction existe (page game)
        if (typeof setPlayerOffline === 'function') {
            await setPlayerOffline();
        }
        
        const response = await fetch(`${API_URL}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });

        const data = await response.json();

        if (data.success) {
            localStorage.clear();
            window.location.href = 'auth.html';
        } else {
            alert('Erreur de déconnexion: ' + data.error);
        }
    } catch (error) {
        console.error('❌ Erreur:', error);
        alert('Erreur de connexion au serveur');
    }
}

// Marquer le lien actif
function setActiveNavLink() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    const links = document.querySelectorAll('.navbar-link');
    
    links.forEach(link => {
        link.classList.remove('active');
        const href = link.getAttribute('href');
        
        if (href === currentPage || 
            (currentPage === '' && href === 'index.html') ||
            (currentPage === '/' && href === 'index.html')) {
            link.classList.add('active');
        }
    });
}

// Initialiser au chargement
window.addEventListener('DOMContentLoaded', () => {
    initNavbar();
    setActiveNavLink();
});
