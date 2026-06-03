import os
import json
import base64
import traceback
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from werkzeug.middleware.proxy_fix import ProxyFix
import google.generativeai as genai

# Forcer la tolérance du HTTP interne pour le proxy de Render
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "une_cle_tres_longue_et_fixe_a_ne_pas_changer_123456789")

# Configuration Proxy et Cookies pour Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None', 
)

CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON", "{}"))
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Initialisation de l'IA Google Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model_ia = genai.GenerativeModel('gemini-1.5-flash')

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

def generer_resume_ia(sujet, expediteur, corps_texte):
    """Demande à l'IA de nettoyer le texte et de générer un résumé strict en 2 phrases."""
    try:
        prompt = f"""
        Tu es NZK_AGENT. Analyse l'e-mail suivant et fais-en un résumé en exactement 2 phrases claires et structurées.
        Élimine tout le bruit inutile (liens, signatures, codes d'erreur bruts) pour ne garder que l'intention réelle du message.

        DÉTAILS DE L'E-MAIL :
        - Expéditeur : {expediteur}
        - Sujet : {sujet}
        - Contenu brut : {corps_texte}

        RÉPONSE ATTENDUE : Uniquement les 2 phrases de résumé.
        """
        response = model_ia.generate_content(prompt)
        return response.text.strip()
    except Exception as ia_error:
        print(f"Erreur Résumé IA : {str(ia_error)}")
        return corps_texte[:150] + "..."

@app.route('/')
def home():
    if 'credentials' in session:
        return redirect(url_for('page_agent', _scheme='https', _external=True))
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
        # CORRECTION DE LA PARENTHÈSE ICI
        return redirect(url_for('page_agent', _scheme='https', _external=True))
        
    except Exception as e:
        print(f"!!! CRASH OAUTH !!! : {str(e)}")
        return f"<h2>Erreur OAuth !</h2><pre>{traceback.format_exc()}</pre>", 500

@app.route('/agent')
def page_agent():
    if 'credentials' not in session:
        return render_template('agent.html', authenticated=False)

    try:
        service = get_gmail_service()
        results = service.users().messages().list(userId='me', maxResults=10).execute()
        messages = results.get('messages', [])
        
        historique_mails = []
        
        if messages:
            for msg in messages:
                msg_detail = service.users().messages().get(
                    userId='me', id=msg['id'], format='full'
                ).execute()
                
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                
                sujet = "Sans sujet"
                expediteur = "Inconnu"
                
                for header in headers:
                    if header['name'] == 'Subject': sujet = header['value']
                    if header['name'] == 'From': expediteur = header['value']
                
                texte_brut = msg_detail.get('snippet', '')
                if not texte_brut:
                    parts = payload.get('parts', [])
                    if parts:
                        for part in parts:
                            if part['mimeType'] == 'text/plain':
                                data = part['body'].get('data', '')
                                texte_brut = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                break
                
                # Appel du résumé
                resume_ia = generer_resume_ia(sujet, expediteur, texte_brut)
                        
                historique_mails.append({
                    'sujet': sujet,
                    'resume': resume_ia
                })
                
        return render_template('agent.html', authenticated=True, historique=historique_mails)
        
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "expired" in str(e).lower():
            session.pop('credentials', None)
            return redirect(url_for('login', _scheme='https', _external=True))
            
        print(f"!!! CRASH DANS PAGE_AGENT !!! : {str(e)}")
        return f"<h2>Erreur de traitement des e-mails</h2><pre>{traceback.format_exc()}</pre>", 500


# --- NOUVELLE LOGIQUE DU CHAT IA ---
@app.route('/chat', methods=['POST'])
def chat_ia():
    donnees = request.get_json()
    message_utilisateur = donnees.get('message', '')
    
    try:
        # Prompt système pour donner un caractère à l'IA
        contexte = f"""
        Tu es NZK_AGENT, l'intelligence artificielle personnelle d'Ange (alias Nzk).
        Ange est étudiant en BTS SIO SISR (réseaux et systèmes) et également artiste rap.
        Ton rôle est de l'assister de manière précise, technique, mais avec un style direct et efficace.
        Réponds directement à sa requête ci-dessous sans t'étaler, de façon stylée.
        
        Requête de Ange : {message_utilisateur}
        """
        
        response = model_ia.generate_content(contexte)
        reponse_ia = response.text.strip()
        
    except Exception as e:
        print(f"Erreur API Chat : {str(e)}")
        reponse_ia = "Erreur système. Connexion au réseau neuronal interrompue."
        
    return jsonify({"reponse": reponse_ia})

if __name__ == '__main__':
    app.run(port=5000)
