import os
import json
import base64
import traceback
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from werkzeug.middleware.proxy_fix import ProxyFix

# --- IMPORT IA (Exemple avec Google Gemini, ajuste selon ton modèle) ---
# Si tu utilises OpenAI : import openai
# Si tu utilises Anthropic : import anthropic
from google import genai 

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

# Initialisation du client IA (Utilise ta clé API définie dans tes variables d'environnement)
# Assure-toi d'avoir ajouté GEMINI_API_KEY sur ton tableau de bord Render
client_ia = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

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
        Tu es un assistant IA d'élite intégré à un tableau de bord. 
        Analyse l'e-mail suivant et fais-en un résumé en exactement 2 phrases claires, professionnelles et bien structurées.
        Élimine tout le bruit inutile (liens système, signatures répétitives, codes d'erreur bruts de serveurs comme Make/Render) pour ne garder que l'intention réelle du message.

        DÉTAILS DE L'E-MAIL :
        - Expéditeur : {expediteur}
        - Sujet : {sujet}
        - Contenu brut : {corps_texte}

        RÉPONSE ATTENDUE : Uniquement les 2 phrases de résumé. Pas d'introduction, pas de fioritures.
        """
        
        # Appel de l'IA (Ici avec gemini-2.5-flash, ultra rapide pour ça)
        response = client_ia.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as ia_error:
        print(f"Erreur lors de la génération du résumé par l'IA : {str(ia_error)}")
        # En cas de panne de l'API IA, on retourne une version courte du texte de base pour ne pas faire crasher l'application
        return corps_texte[:150] + "..."

@app.route('/')
def home():
    if 'credentials' in session:
        return redirect(url_for('page_agent'))
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
                
                # Récupération du contenu brut pour l'envoyer à l'IA
                texte_brut = msg_detail.get('snippet', '')
                if not texte_brut:
                    parts = payload.get('parts', [])
                    if parts:
                        for part in parts:
                            if part['mimeType'] == 'text/plain':
                                data = part['body'].get('data', '')
                                texte_brut = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                break
                
                # APPEL DE L'IA POUR CRÉER LE RÉSUMÉ EN 2 PHRASES
                resume_ia = generer_resume_ia(sujet, expediteur, texte_brut)
                        
                historique_mails.append({
                    'sujet': sujet,
                    'resume': resume_ia  # Contient uniquement les 2 phrases propres
                })
                
        return render_template('agent.html', authenticated=True, historique=historique_mails)
        
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "expired" in str(e).lower():
            session.pop('credentials', None)
            return redirect(url_for('login', _scheme='https', _external
