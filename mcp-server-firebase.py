# Import necessary libraries
import json
import datetime
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from firebase_admin import credentials, firestore, initialize_app, auth
from typing import Dict, Any, List

# --- Firebase Initialization and Globals ---
# These are provided by the canvas environment.
firebase_config = json.loads(typeof
__firebase_config != = 'undefined' ? __firebase_config: '{}')
initial_auth_token = typeof
__initial_auth_token != = 'undefined' ? __initial_auth_token: None

# Check if a valid Firebase config is available before initializing the app
if firebase_config and 'projectId' in firebase_config:
    try:
        # Initialize Firebase Admin SDK
        firebase_app = initialize_app(credentials.Certificate(firebase_config))
        db = firestore.client()
        print("Firebase successfully initialized.")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        db = None
else:
    print("Firebase configuration not found. Running in a non-persistent, read-only mode.")
    db = None

# Initialize the Flask application
app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing for API access

# --- Data Store (Fallback) ---
# Using a simple dictionary as an in-memory database if Firestore is not available.
# This ensures the app can still run for demonstration purposes.
in_memory_contexts = {}


# --- User and Authentication Utility ---
def get_user_id() -> str | None:
    """
    Retrieves the user ID from the authentication token.
    In a production app, you'd use a more robust authentication system.
    This function uses a provided custom token for demonstration purposes.
    """
    try:
        # In a real-world app, you'd verify a token from the request header,
        # e.g., auth.verify_id_token(request.headers.get('Authorization')).
        # Here, we use the custom token provided by the environment.
        if initial_auth_token:
            decoded_token = auth.verify_id_token(initial_auth_token)
            return decoded_token['uid']
    except Exception as e:
        print(f"Error decoding token: {e}")
    return None


def get_db_client():
    """Returns the Firestore client or None if not initialized."""
    return db


# --- API Endpoints ---
@app.route('/create_project', methods=['POST'])
def create_project():
    """
    Creates a new project document in Firestore.
    Requires authentication to link the project to a user.
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication failed. User ID not found."}), 401

    data = request.json
    project_name = data.get('project_name')
    if not project_name:
        return jsonify({"error": "Project name is required"}), 400

    db_client = get_db_client()
    if not db_client:
        return jsonify({"error": "Database not available. Please check configuration."}), 503

    try:
        # Reference the user's projects collection
        user_projects_ref = db_client.collection('users').document(user_id).collection('projects')

        # Check if a project with the same name already exists for this user
        existing_projects = user_projects_ref.where('project_name', '==', project_name).stream()
        for doc in existing_projects:
            # If a project with this name exists, return its ID
            return jsonify({
                "message": "Project already exists",
                "project_id": doc.id
            }), 200

        # If it doesn't exist, create a new document with an auto-generated ID
        new_project = user_projects_ref.document()
        new_project.set({
            "project_name": project_name,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "context": {}
        })

        return jsonify({"message": "Project created successfully", "project_id": new_project.id}), 201

    except Exception as e:
        return jsonify({"error": f"Failed to create project: {e}"}), 500


@app.route('/get_context/<project_id>', methods=['GET'])
def get_context(project_id):
    """
    Retrieves the context data for a given project ID.
    Requires authentication to ensure access to the correct user's data.
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication failed. User ID not found."}), 401

    db_client = get_db_client()
    if not db_client:
        return jsonify({"error": "Database not available. Please check configuration."}), 503

    try:
        project_ref = db_client.collection('users').document(user_id).collection('projects').document(project_id)
        project_doc = project_ref.get()

        if not project_doc.exists:
            return jsonify({"error": "Project not found"}), 404

        return jsonify(project_doc.to_dict().get("context", {})), 200

    except Exception as e:
        return jsonify({"error": f"Failed to retrieve context: {e}"}), 500


@app.route('/update_context/<project_id>', methods=['PATCH'])
def update_context(project_id):
    """
    Updates a specific project's context data using a partial update.
    Requires authentication.
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication failed. User ID not found."}), 401

    db_client = get_db_client()
    if not db_client:
        return jsonify({"error": "Database not available. Please check configuration."}), 503

    update_data = request.json
    if not update_data or not isinstance(update_data, dict):
        return jsonify({"error": "Invalid JSON payload. Expected a dictionary."}), 400

    try:
        project_ref = db_client.collection('users').document(user_id).collection('projects').document(project_id)

        # Use a transaction to ensure a consistent read and write
        @firestore.transactional
        def update_in_transaction(transaction, project_ref):
            project_doc = project_ref.get(transaction=transaction)
            if not project_doc.exists:
                raise ValueError("Project not found")

            current_context = project_doc.to_dict().get('context', {})

            # Merge the new data with the existing context
            def merge_dicts(source, new_data):
                for key, value in new_data.items():
                    if isinstance(value, dict) and key in source and isinstance(source[key], dict):
                        merge_dicts(source[key], value)
                    else:
                        source[key] = value

            merge_dicts(current_context, update_data)

            transaction.update(project_ref, {
                'context': current_context,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return True

        update_in_transaction(db_client.transaction(), project_ref)
        return jsonify({"message": "Context updated successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to update context: {e}"}), 500


@app.route('/delete_project/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """
    Deletes a project by its ID. Requires authentication.
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication failed. User ID not found."}), 401

    db_client = get_db_client()
    if not db_client:
        return jsonify({"error": "Database not available. Please check configuration."}), 503

    try:
        project_ref = db_client.collection('users').document(user_id).collection('projects').document(project_id)
        project_doc = project_ref.get()

        if not project_doc.exists:
            return jsonify({"error": "Project not found"}), 404

        project_ref.delete()
        return jsonify({"message": "Project deleted successfully"}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to delete project: {e}"}), 500


# Simple homepage for the API.
@app.route('/')
def home():
    return render_template_string("<h1>WaiKao MCP Server</h1><p>The Model Context Protocol server is running!</p>")


if __name__ == '__main__':
    # Running in debug mode is for development only.
    # For production, use a WSGI server like Gunicorn or uWSGI.
    app.run(debug=True, host='0.0.0.0', port=5000)
