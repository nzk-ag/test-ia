import os
from flask import Flask, request, jsonify, render_template, redirect, session, url_for
import google.generativeai as genai
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_secrete_aleatoire")

# Configuration Gemini
genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# Configuration OAuth2
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON"))

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=os.environ.get("REDIRECT_URI")
    )

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    flow = get_flow()
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    session['state'] = state
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }
    return redirect(url_for('page_agent'))

@app.route('/agent')
def page_agent():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    
    # Construction du service Gmail avec les creds en session
    from google.oauth2.credentials import Credentials
    creds = Credentials(**session['credentials'])
    service = build('gmail', 'v1', credentials=creds)
    
    # Récupération mails (ton ancienne logique)
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    # ... (Ajoute ta logique de récupération ici) ...
    
    return render_template('agent.html', historique=[]) 

@app.route('/chat', methods=['POST'])
def chat_ia():
    # ... (Ton code actuel) ...
    return jsonify({"reponse": "..."})

if __name__ == '__main__':
    app.run(port=5000)
