"""
Firebase Authentication Module for Boomshakalaka Dashboard

Provides Firebase token verification and role-based access control
by sharing authentication with True Tracking (true-tracking-prod project).
"""

import os
import functools
from typing import Optional
from flask import session, redirect, url_for, request, jsonify

import requests

# Firebase Admin SDK initialization
try:
    import firebase_admin
    from firebase_admin import auth as firebase_auth
    from firebase_admin import credentials
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    firebase_admin = None
    firebase_auth = None
    credentials = None

# Configuration
FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID', 'true-tracking-dashboard')
TRUE_TRACKING_API_URL = os.environ.get('TRUE_TRACKING_API_URL', 'http://localhost:4000')

# Path to service account key (shared with True Tracking)
SERVICE_ACCOUNT_PATH = os.environ.get(
    'GOOGLE_APPLICATION_CREDENTIALS',
    '/home/pds/businesses/true-tracking/customer_dashboard/secrets/firebase-admin-key.json'
)

# Firebase Admin app instance
_firebase_app = None


def init_firebase() -> bool:
    """Initialize Firebase Admin SDK. Returns True if successful."""
    global _firebase_app

    if not FIREBASE_AVAILABLE:
        print("Warning: firebase-admin package not installed")
        return False

    if _firebase_app is not None:
        return True

    try:
        # Check if already initialized
        try:
            _firebase_app = firebase_admin.get_app()
            return True
        except ValueError:
            pass

        # Initialize with service account
        if os.path.exists(SERVICE_ACCOUNT_PATH):
            cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
            _firebase_app = firebase_admin.initialize_app(cred, {
                'projectId': FIREBASE_PROJECT_ID
            })
            print(f"Firebase Admin initialized with project: {FIREBASE_PROJECT_ID}")
            return True
        else:
            print(f"Warning: Service account not found at {SERVICE_ACCOUNT_PATH}")
            return False

    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        return False


def verify_firebase_token(id_token: str) -> Optional[dict]:
    """
    Verify a Firebase ID token and return the decoded claims.

    Args:
        id_token: The Firebase ID token from the client

    Returns:
        Decoded token claims if valid, None otherwise
    """
    if not FIREBASE_AVAILABLE or not init_firebase():
        return None

    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        return decoded_token
    except firebase_auth.InvalidIdTokenError:
        print("Invalid Firebase ID token")
        return None
    except firebase_auth.ExpiredIdTokenError:
        print("Expired Firebase ID token")
        return None
    except Exception as e:
        print(f"Error verifying token: {e}")
        return None


def get_user_role(firebase_token: str) -> Optional[dict]:
    """
    Get user information including role from True Tracking API.

    Args:
        firebase_token: The Firebase ID token

    Returns:
        User dict with {id, email, name, role, customerId} or None
    """
    try:
        response = requests.get(
            f"{TRUE_TRACKING_API_URL}/api/auth/me",
            headers={'Authorization': f'Bearer {firebase_token}'},
            timeout=10
        )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            # User not in True Tracking database - still valid Firebase user
            # but no role assigned
            return None
        else:
            print(f"True Tracking API error: {response.status_code}")
            return None

    except requests.RequestException as e:
        print(f"Error calling True Tracking API: {e}")
        return None


def get_current_user() -> Optional[dict]:
    """Get the current logged-in user from session."""
    return session.get('user')


def is_authenticated() -> bool:
    """Check if a user is currently authenticated."""
    return get_current_user() is not None


def is_admin() -> bool:
    """Check if the current user has admin or super_admin role."""
    user = get_current_user()
    if not user:
        return False
    return user.get('role') in ['admin', 'super_admin']


def requires_auth(f):
    """
    Decorator to require authentication for a route.
    Redirects to login page if not authenticated.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def requires_role(*roles):
    """
    Decorator to require specific role(s) for a route.

    Usage:
        @app.route('/admin')
        @requires_role('admin', 'super_admin')
        def admin_page():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                return redirect(url_for('login', next=request.url))
            if user.get('role') not in roles:
                # User is authenticated but lacks permission
                return jsonify({
                    'error': 'Forbidden',
                    'message': f'This page requires one of these roles: {", ".join(roles)}'
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def login_user(firebase_token: str) -> tuple[bool, Optional[str]]:
    """
    Log in a user with their Firebase token.

    Args:
        firebase_token: The Firebase ID token from client

    Returns:
        (success, error_message)
    """
    # Verify the Firebase token
    decoded = verify_firebase_token(firebase_token)
    if not decoded:
        return False, "Invalid or expired token"

    # Get user info including role from True Tracking
    user_info = get_user_role(firebase_token)

    # Store user in session
    session['user'] = {
        'uid': decoded.get('uid'),
        'email': decoded.get('email'),
        'name': user_info.get('name') if user_info else decoded.get('name', ''),
        'role': user_info.get('role') if user_info else 'guest',
        'customerId': user_info.get('customerId') if user_info else None,
    }

    return True, None


def logout_user():
    """Log out the current user by clearing the session."""
    session.pop('user', None)
