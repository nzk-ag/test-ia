import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_secrete_tres_complexe")

# Configuration OAuth (Utilise la variable d'env contenant le JSON)
CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON"))
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="https://test-ia-6i37.onrender.com/oauth2callback"
    )

@app.route('/login')
def login():
    flow = get_flow()
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    # 1. Vérifier si l'état (state) existe dans la session
    if 'state' not in session:
        return "Erreur : Session expirée ou inexistante. Veuillez réessayer.", 400

    # 2. Reconstruire le flow avec le redirect_uri configuré
    flow = get_flow()
    
    # 3. Récupérer le token (c'est ici que le code verifier est utilisé)
    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception as e:
        return f"Erreur lors de la récupération du token : {str(e)}", 500

    credentials = flow.credentials
    # Stocker les infos en session
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return redirect(url_for('page_agent'))

def get_gmail_service():
    if 'credentials' not in session:
        raise Exception("Non authentifié")
    creds = Credentials(**session['credentials'])
    return build('gmail', 'v1', credentials=creds)

@app.route('/agent')
def page_agent():
    try:
        service = get_gmail_service()
        # Ta logique existante ici...
        return render_template('agent.html', historique=[])
    except Exception as e:
        return redirect(url_for('login'))

# ... le reste de ton code (chat_ia, etc.) reste identique ...

@app.route('/chat', methods=['POST'])
def chat_ia():
    # ... (Ton code actuel) ...
    return jsonify({"reponse": "..."})

if __name__ == '__main__':
    app.run(port=5000)
