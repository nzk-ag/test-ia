import os
import json
import base64
import html
import traceback
from email.message import EmailMessage
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from werkzeug.middleware.proxy_fix import ProxyFix
import google.generativeai as genai

# Forcer la tolérance du HTTP interne pour le reverse-proxy de Render
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "nzk_agent_ultra_secure_key_987654321")

# Paramètres de session et Proxy pour maintenir l'état sur Render
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.config.update(
    SESSION_COOKIE_SECURE=True,    
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None', 
)

CLIENT_CONFIG = json.loads(os.environ.get("GOOGLE_CLIENT_SECRET_JSON", "{}"))

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

def executer_appel_gemini(prompt):
    """
    Exécute un appel résilient vers l'API Gemini en testant plusieurs clés d'API 
    et plusieurs versions de modèles pour garantir une continuité de service absolue.
    """
    # Détection automatique de la clé d'API (multi-variable pour Render)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise Exception("Clé d'API introuvable. Configurez GEMINI_API_KEY ou GOOGLE_API_KEY sur Render.")
        
    genai.configure(api_key=api_key)
    
    # Liste ordonnée de modèles récents et stables
    modeles = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash', 'gemini-3-flash-preview']
    derniere_erreur = None
    
    for nom_modele in modeles:
        try:
            model = genai.GenerativeModel(nom_modele)
            response = model.generate_content(prompt)
            
            if response:
                try:
                    if response.text:
                        return response.text
                except ValueError:
                    # Sécurité : Si le texte brut est inaccessible à cause des filtres,
                    # on extrait de manière sécurisée la première structure textuelle valide disponible.
                    if hasattr(response, 'candidates') and response.candidates:
                        candidate = response.candidates[0]
                        if hasattr(candidate, 'content') and candidate.content.parts:
                            part = candidate.content.parts[0]
                            if hasattr(part, 'text') and part.text:
                                return part.text
            continue
        except Exception as e:
            derniere_erreur = e
            continue
            
    raise derniere_erreur or Exception("Aucun modèle de l'écosystème Gemini n'a pu traiter la demande.")

def get_flow():
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri="https://test-ia-6i37.onrender.com/oauth2callback"
    )

def get_gmail_service():
    if 'credentials' not in session:
        raise Exception("Utilisateur non connecté à Google.")
    creds = Credentials(**session['credentials'])
    return build('gmail', 'v1', credentials=creds)

def generer_resume_ia(sujet, expediteur, corps_texte):
    """Génère un résumé court ou renvoie un extrait propre en cas d'indisponibilité de l'IA."""
    try:
        prompt = f"""
        Tu es NZK_AGENT. Analyse cet e-mail et rédige un résumé clair en MAXIMUM 2 sentences en FRANÇAIS.
        Expéditeur : {expediteur}
        Sujet : {sujet}
        Contenu : {corps_texte}
        """
        return executer_appel_gemini(prompt).strip()
    except Exception as e:
        print(f"[LOG RESUME] Utilisation du fallback textuel : {str(e)}")
        return html.unescape(corps_texte[:140]) + "..."

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
        return "Session expirée.", 400
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
        return f"Erreur d'authentification : {str(e)}", 500

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
                
                sujet, expediteur = "Sans objet", "Inconnu"
                for h_item in headers:
                    if h_item['name'] == 'Subject': sujet = h_item['value']
                    if h_item['name'] == 'From': expediteur = h_item['value']
                
                texte_brut = msg_detail.get('snippet', '')
                if not texte_brut:
                    parts = payload.get('parts', [])
                    for part in parts:
                        if part['mimeType'] == 'text/plain':
                            data = part['body'].get('data', '')
                            texte_brut = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                            break
                
                historique_mails.append({
                    'sujet': html.unescape(sujet),
                    'resume': generer_resume_ia(sujet, expediteur, texte_brut)
                })
        return render_template('agent.html', authenticated=True, historique=historique_mails)
    except Exception as e:
        if any(x in str(e).lower() for x in ["invalid_grant", "expired", "insufficient"]):
            session.clear()
            return redirect(url_for('login', _scheme='https', _external=True))
        return f"Erreur serveur : {str(e)}", 500

@app.route('/chat', methods=['POST'])
def chat_ia():
    try:
        data = request.get_json() or {}
        user_message = data.get('message', '')
        if not user_message:
            return jsonify({"reponse": "Le message envoyé est vide."}), 400

        # Récupération dynamique des 5 derniers e-mails pour fournir un contexte à l'IA
        contexte_emails = "Aucun e-mail disponible actuellement."
        try:
            service = get_gmail_service()
            recent = service.users().messages().list(userId='me', maxResults=5).execute().get('messages', [])
            details = []
            for idx, m in enumerate(recent):
                d = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
                h = d.get('payload', {}).get('headers', [])
                frm = next((x['value'] for x in h if x['name'] == 'From'), 'Inconnu')
                sub = next((x['value'] for x in h if x['name'] == 'Subject'), 'Sans objet')
                snip = d.get('snippet', '')
                details.append(f"E-mail #{idx+1} :\n- De : {frm}\n- Objet : {sub}\n- Extrait : {snip}\n")
            if details:
                contexte_emails = "\n".join(details)
        except Exception:
            pass

        prompt_systeme = f"""
        Tu es NZK_AGENT, un assistant d'exploitation connecté aux e-mails de l'utilisateur. 
        Voici ses 5 derniers messages reçus :
        {contexte_emails}

        Demande de l'utilisateur : "{user_message}"

        CONSIGNES OBLIGATOIRES :
        1. Réponds brièvement, de manière professionnelle et en français.
        2. Si l'utilisateur demande d'écrire, de générer ou de répondre à un mail, rédige ton texte explicatif normalement, puis intègre STRUCTURELLEMENT à la toute fin de ton message le bloc JSON exact délimité par <DRAFT> et </DRAFT>.
        3. Nettoie rigoureusement le champ "to" pour n'inclure que l'adresse e-mail pure (ex: "nom@domaine.com").
        
        Format attendu pour le bloc draft :
        <DRAFT>
        {{"to": "destinataire@domaine.com", "subject": "Sujet du message", "body": "Contenu intégral du mail rédigé"}}
        </DRAFT>
        """
        
        reponse_texte = executer_appel_gemini(prompt_systeme)
        return jsonify({"reponse": reponse_texte})
        
    except Exception as e:
        print(f"!!! ERREUR REQUÊTE CHAT !!! : {str(e)}")
        return jsonify({"reponse": f"Une erreur technique est survenue sur le serveur de l'IA : {str(e)}"}), 500

@app.route('/send_email', methods=['POST'])
def send_email_route():
    if 'credentials' not in session:
        return jsonify({"success": False, "error": "Non authentifié"}), 401
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
