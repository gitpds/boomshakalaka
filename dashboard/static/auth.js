/**
 * Boomshakalaka Dashboard - Authentication Utilities
 *
 * This module provides client-side authentication utilities for
 * pages that need to interact with auth state.
 */

// Check if user is logged in via session
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/me');
        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch (error) {
        console.error('Error checking auth status:', error);
        return null;
    }
}

// Logout the current user
async function logout() {
    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST',
        });

        if (response.ok) {
            // Also sign out of Firebase on the client
            // This requires Firebase to be initialized on the page
            if (typeof firebase !== 'undefined' && firebase.auth) {
                await firebase.auth().signOut();
            }

            // Redirect to home
            window.location.href = '/';
        } else {
            console.error('Logout failed');
        }
    } catch (error) {
        console.error('Error during logout:', error);
    }
}

// Export for use in other scripts
window.BoomAuth = {
    checkStatus: checkAuthStatus,
    logout: logout,
};
