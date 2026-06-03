import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_tres_longue_et_fixe_a_ne_pas_changer_123456789")

# 2. CONFIGURATION DES COOKIES (CRUCIAL POUR RENDER)
# Render utilise HTTPS, donc le cookie doit être 'Secure' et 'Lax' pour passer 
# lors de la redirection depuis Google.
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax', 
)

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
import os
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json
# 1. IMPORTER PROXYFIX
from werkzeug.middleware.proxy_fix import ProxyFix

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
    if 'state' not in session:
        return "Session perdue, veuillez recommencer.", 400
        
    flow = get_flow()
    
    # 4. SÉCURITÉ SUPPLÉMENTAIRE
    # On s'assure de forcer le HTTPS dans l'URL de la requête, au cas où le proxy 
    # laisserait passer un "http://" qui ferait planter la vérification OAuth.
    authorization_response = request.url.replace('http://', 'https://')
    
    flow.fetch_token(authorization_response=authorization_response)
    
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
