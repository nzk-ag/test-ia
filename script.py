import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

# --- CONFIGURATION ---
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_secrete_tres_complexe")

# Configuration Gemini
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-flash')

# Configuration Gmail (Chargée depuis les variables d'environnement)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON"))

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        # On va chercher la valeur dans les variables d'environnement
        redirect_uri=os.environ.get("REDIRECT_URI") 
    )

def get_gmail_service():
    """Crée le service Gmail à partir du token en variable d'environnement."""
    token_data = json.loads(os.environ.get("GOOGLE_TOKEN_JSON"))
    creds = Credentials.from_authorized_user_info(token_data)
    return build('gmail', 'v1', credentials=creds)

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    flow = get_flow()
    auth_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    # Après connexion, Google renvoie ici. 
    # Note : Sur Render, tu devras récupérer le token généré et le mettre dans GOOGLE_TOKEN_JSON
    return "Authentification reçue. Copiez le code de retour pour valider votre token."

@app.route('/agent')
def page_agent():
    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', maxResults=5).execute()
        messages = results.get('messages', [])
        
        historique = []
        for msg in messages:
            m = service.users().messages().get(userId='me', id=msg['id']).execute()
            sujet = next((h['value'] for h in m['payload']['headers'] if h['name'] == 'Subject'), "Sans objet")
            historique.append({'sujet': sujet, 'resume': m.get('snippet', '')})
        
        return render_template('agent.html', authenticated=True, historique=historique)
    except Exception:
        return render_template('agent.html', authenticated=False, historique=[])

@app.route('/chat', methods=['POST'])
def chat_ia():
    message_utilisateur = request.json.get('message')
    prompt = f"Date: {datetime.now().strftime('%d/%m/%Y')}. Question: {message_utilisateur}"
    response = model.generate_content(prompt)
    return jsonify({"reponse": response.text})

if __name__ == '__main__':
    app.run(port=5000)
