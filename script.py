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

# Configuration Proxy et Cookies indispensable pour les sessions sur Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None', # Changé à 'None' pour autoriser le retour de Google
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
    # Si déjà connecté, on bascule directement sur l'agent
    if 'credentials' in session:
        return redirect(url_for('page_agent'))
    # Sinon, on affiche la page agent avec le bloc de connexion
    return render_template('agent.html', authenticated=False)

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
    # Si l'utilisateur n'est pas connecté, on montre l'écran d'accès sécurisé
    if 'credentials' not in session:
        return render_template('agent.html', authenticated=False)

    try:
        service = get_gmail_service()
        
        # Récupération des 10 derniers messages Gmail
        results = service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])
        
        historique_mails = []
        
        if messages:
            for msg in messages:
                # Cette fois, on demande le format 'full' pour avoir le corps du texte
                msg_detail = service.users().messages().get(
                    userId='me', 
                    id=msg['id'], 
                    format='full'
                ).execute()
                
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                
                sujet = "Sans sujet"
                expediteur = "Inconnu"
                
                for header in headers:
                    if header['name'] == 'Subject':
                        sujet = header['value']
                    if header['name'] == 'From':
                        expediteur = header['value']
                
                # --- RÉCUPÉRATION DU CONTENU TEXTE ---
                # Option 1 : On prend le "snippet" (l'aperçu textuel automatique de Google, super propre)
                texte_mail = msg_detail.get('snippet', '')
                
                # Option 2 (Sécurité) : Si le snippet est vide, on cherche dans les différentes parties du mail
                if not texte_mail:
                    parts = payload.get('parts', [])
                    if parts:
                        for part in parts:
                            if part['mimeType'] == 'text/plain':
                                data = part['body'].get('data', '')
                                texte_mail = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                break
                    else:
                        data = payload.get('body', {}).get('data', '')
                        if data:
                            texte_mail = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                # Si le mail est trop long, on le coupe proprement pour ton interface
                if len(texte_mail) > 300:
                    texte_mail = texte_mail[:300] + "..."
                        
                # On assemble le tout pour l'envoyer au template agent.html
                historique_mails.append({
                    'sujet': sujet,
                    'resume': f"De : {expediteur} \n\n Message : {texte_mail}"
                })
                
        return render_template('agent.html', authenticated=True, historique=historique_mails)
        
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "expired" in str(e).lower():
            session.pop('credentials', None)
            return redirect(url_for('login', _scheme='https', _external=True))
            
        print(f"!!! CRASH DANS PAGE_AGENT !!! : {str(e)}")
        erreur_complete = traceback.format_exc()
        return f"<h2>Erreur lors de la récupération du texte des mails :</h2><pre>{erreur_complete}</pre>", 500
@app.route('/chat', methods=['POST'])
def chat_ia():
    # Récupère le message envoyé depuis le terminal
    donnees = request.get_json()
    message_utilisateur = donnees.get('message', '')
    
    # Intègre ici ta logique d'IA. Pour l'instant, réponse automatique de test :
    reponse_ia = f"J'ai bien reçu votre commande : '{message_utilisateur}'. L'analyse de vos e-mails est fonctionnelle !"
    
    return jsonify({"reponse": reponse_ia})

if __name__ == '__main__':
    app.run(port=5000)
