import os
import json
import traceback
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from werkzeug.middleware.proxy_fix import ProxyFix

# Forcer la tolérance du HTTP interne pour le proxy de Render
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_tres_longue_et_fixe_a_ne_pas_changer_123456789")

# Configuration indispensable pour les sessions derrière le proxy Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None', 
)

CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON", "{}"))
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="https://test-ia-6i37.onrender.com/oauth2callback"
    )

def get_gmail_service():
    if 'credentials' not in session:
        raise Exception("Non authentifié")
    creds = Credentials(**session['credentials'])
    return build('gmail', 'v1', credentials=creds)

@app.route('/')
def home():
    # Si l'utilisateur est déjà connecté, on le redirige directement vers l'agent
    if 'credentials' in session:
        return redirect(url_for('page_agent'))
    
    # Sinon, on affiche la page d'accueil avec le bouton "Se connecter"
    return render_template('index.html', connecte=False)

@app.route('/login')
def login():
    flow = get_flow()
    auth_url, state = flow.authorization_url(prompt='consent', access_type='offline')
    
    session['state'] = state
    if hasattr(flow, 'code_verifier'):
        session['code_verifier'] = flow.code_verifier
        
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    if 'state' not in session:
        return "Session perdue, veuillez recommencer.", 400
        
    try:
        flow = get_flow()
        authorization_response = request.url.replace('http://', 'https://')
        
        kwargs = {}
        if 'code_verifier' in session:
            kwargs['code_verifier'] = session['code_verifier']
        
        flow.fetch_token(authorization_response=authorization_response, **kwargs)
        
        session.pop('code_verifier', None)
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        return redirect(url_for('page_agent', _scheme='https', _external=True))
        
    except Exception as e:
        print(f"!!! CRASH OAUTH !!! : {str(e)}")
        erreur_complete = traceback.format_exc()
        return f"<h2>Le code a planté dans OAuth ! Voici pourquoi :</h2><pre>{erreur_complete}</pre>", 500

@app.route('/agent')
def page_agent():
    # Si pas connecté, direction le login Google
    if 'credentials' not in session:
        return redirect(url_for('login', _scheme='https', _external=True))

    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])
        
        mails_a_afficher = []
        if messages:
            for msg in messages:
                msg_detail = service.users().messages().get(
                    userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From']
                ).execute()
                
                headers = msg_detail.get('payload', {}).get('headers', [])
                sujet = "Sans sujet"
                expediteur = "Inconnu"
                for header in headers:
                    if header['name'] == 'Subject': sujet = header['value']
                    if header['name'] == 'From': expediteur = header['value']
                        
                mails_a_afficher.append({'sujet': sujet, 'expediteur': expediteur})
                
        # Crucial : On passe "connecte=True" et la liste des mails au template
        return render_template('index.html', connecte=True, historique=[], mails=mails_a_afficher)
        
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "expired" in str(e).lower():
            session.pop('credentials', None)
            return redirect(url_for('login', _scheme='https', _external=True))
        return f"<h2>Erreur : {str(e)}</h2>", 500

@app.route('/chat', methods=['POST'])
def chat_ia():
    return jsonify({"reponse": "Message reçu"})

if __name__ == '__main__':
    app.run(port=5000)
