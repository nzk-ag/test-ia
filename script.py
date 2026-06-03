import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json
# 1. IMPORTER PROXYFIX
from werkzeug.middleware.proxy_fix import ProxyFix

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_tres_longue_et_fixe_a_ne_pas_changer_123456789")

# 2. APPLIQUER PROXYFIX À L'APPLICATION
# Cela indique à Flask qu'il est derrière le proxy de Render et qu'il doit 
# traiter les requêtes comme étant en HTTPS.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# 3. METTRE À JOUR LA CONFIGURATION DES COOKIES
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    # Changer 'Lax' en 'None' pour autoriser le cookie lors du retour depuis Google
    SESSION_COOKIE_SAMESITE='None', 
)

@app.route('/')
def home():
    return render_template('index.html')

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
    
    # 1. On sauvegarde le state ET le code_verifier s'il existe
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
        
        # 2. On récupère le code_verifier stocké pour le transmettre à fetch_token
        kwargs = {}
        if 'code_verifier' in session:
            kwargs['code_verifier'] = session['code_verifier']
        
        # On passe les arguments dynamiquement à fetch_token
        flow.fetch_token(authorization_response=authorization_response, **kwargs)
        
        # 3. Nettoyage de la session après succès
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
        return redirect(url_for('page_agent'))
        
    except Exception as e:
        print(f"!!! CRASH OAUTH !!! : {str(e)}")
        erreur_complete = traceback.format_exc()
        return f"<h2>Le code a planté ! Voici pourquoi :</h2><pre>{erreur_complete}</pre>", 500

# ... Le reste de votre code (get_gmail_service, page_agent, chat_ia) ...


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
