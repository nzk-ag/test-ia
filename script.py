import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_secrete_tres_compl")

# Configuration OAuth (Utilise la variable d'env contenant le JSON)
CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON"))
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="https://test-ia-6i37.onrender.com/oauth2callback"
    )

# 1. Dans ta route /login
@app.route('/login')
def login():
    flow = get_flow() # Ta fonction qui crée le flow
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    session['state'] = state  # Sauvegarde pour vérification au retour
    return redirect(auth_url)

# 2. Dans ta route /oauth2callback
@app.route('/oauth2callback')
def oauth2callback():
    # Vérifie que la session est intacte
    if 'state' not in session:
        return "Session perdue, veuillez recommencer.", 400
        
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    
    # Stockage
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        # ... autres champs
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
