import os
import json
import base64
import traceback
from email.message import EmailMessage
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

# PERMISSIONS GMAIL (Lecture + Envoi)
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

# Configuration initiale de l'API Google GenAI
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def appeler_gemini_resilient(prompt):
    """
    Tente d'appeler l'IA avec une liste de modèles triés par pertinence.
    Évite les crashs si un nom de modèle spécifique est rejeté par l'infrastructure.
    """
    modeles_candidats = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-2.0-flash-lite'
    ]
    derniere_erreur = None
    for nom_modele in modeles_candidats:
        try:
            model = genai.GenerativeModel(nom_modele)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            derniere_erreur = e
            continue
    raise derniere_erreur or Exception("Aucun modèle Gemini n'a pu répondre.")

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
    """Génère un résumé strict et propre via le moteur résilient."""
    try:
        prompt = f"""
        Tu es NZK_AGENT. Analyse l'e-mail suivant et fais-en un résumé en MAXIMUM 2 phrases claires.
        CONSIGNE ABSOLUE : Rédige obligatoirement en FRANÇAIS.

        DÉTAILS DE L'E-MAIL :
        - Expéditeur : {expediteur}
        - Sujet : {sujet}
        - Contenu brut : {corps_texte}

        RÉPONSE ATTENDUE : Uniquement ton résumé en français, sans fioritures.
        """
        return appeler_gemini_resilient(prompt).strip()
    except Exception as e:
        print(f"Erreur Résumé IA : {str(e)}")
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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

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
        return f"<h2>Erreur d'authentification</h2><pre>{traceback.format_exc()}</pre>", 500

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
                msg_detail = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
                payload = msg_detail.get('payload', {})
                headers = payload.get('headers', [])
                
                sujet, expediteur = "Sans sujet", "Inconnu"
                for header in headers:
                    if header['name'] == 'Subject': sujet = header['value']
                    if header['name'] == 'From': expediteur = header['value']
                
                texte_brut = msg_detail.get('snippet', '')
                if not texte_brut:
                    parts = payload.get('parts', [])
                    for part in parts:
                        if part['mimeType'] == 'text/plain':
                            data = part['body'].get('data', '')
                            texte_brut = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                            break
                
                historique_mails.append({
                    'sujet': sujet,
                    'resume': generer_resume_ia(sujet, expediteur, texte_brut)
                })
                
        return render_template('agent.html', authenticated=True, historique=historique_mails)
        
    except Exception as e:
        if "invalid_grant" in str(e).lower() or "expired" in str(e).lower() or "insufficient" in str(e).lower():
            session.clear()
            return redirect(url_for('login', _scheme='https', _external=True))
        return f"<h2>Erreur de traitement</h2><pre>{traceback.format_exc()}</pre>", 500


# --- CONFIGURATION CHAT IA ---
@app.route('/chat', methods=['POST'])
def chat_ia():
    try:
        data = request.get_json() or {}
        user_message = data.get('message', '')
        if not user_message:
            return jsonify({"reponse": "Le message est vide."}), 400

        # Récupération sécurisée des e-mails pour donner du contexte à la discussion
        contexte_emails = "Aucun e-mail récent accessible."
        try:
            service = get_gmail_service()
            recent = service.users().messages().list(userId='me', maxResults=5).execute().get('messages', [])
            details = []
            for i, m in enumerate(recent):
                d = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
                h = d.get('payload', {}).get('headers', [])
                frm = next((x['value'] for x in h if x['name'] == 'From'), 'Inconnu')
                sub = next((x['value'] for x in h if x['name'] == 'Subject'), 'Sans sujet')
                snip = d.get('snippet', '')
                details.append(f"E-mail #{i+1} :\n- Expéditeur : {frm}\n- Sujet : {sub}\n- Extrait : {snip}\n")
            if details:
                contexte_emails = "\n".join(details)
        except Exception:
            pass 

        prompt_systeme = f"""
        Tu es NZK_AGENT, un assistant personnel intelligent et technique. Tu as accès aux 5 derniers e-mails de l'utilisateur :
        {contexte_emails}

        L'utilisateur te dit : "{user_message}"

        CONSIGNES :
        1. Réponds de façon concise, polie et directement en français.
        2. SI l'utilisateur te demande de rédiger, générer, ou de répondre à un e-mail, formule ta réponse et génère IMPÉRATIVEMENT à la toute fin de ton message le bloc JSON structuré suivant délimité par <DRAFT> et </DRAFT>.
        3. Dans le champ "to", extrais proprement uniquement l'adresse e-mail (ex: "contact@lien.com").
        
        Format obligatoire (ne mets rien d'autre entre ces balises) :
        <DRAFT>
        {{"to": "adresse_destinataire@domaine.com", "subject": "Objet du mail", "body": "Texte complet du mail rédigé"}}
        </DRAFT>
        """
        
        reponse_texte = appeler_gemini_resilient(prompt_systeme)
        return jsonify({"reponse": reponse_texte})
        
    except Exception as e:
        print(f"!!! CRASH CHAT IA !!! : {str(e)}")
        return jsonify({"reponse": "Désolé, ma console rencontre une anomalie technique temporaire."}), 500


# --- ENVOI DE COMPTE DE MESSAGERIE ---
@app.route('/send_email', methods=['POST'])
def send_email_route():
    if 'credentials' not in session:
        return jsonify({"success": False, "error": "Session non authentifiée."}), 401
    
    data = request.get_json() or {}
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(data.get('body', ''))
        message['To'] = data.get('to', '')
        message['Subject'] = data.get('subject', '')

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        
        service.users().messages().send(userId="me", body=create_message).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
