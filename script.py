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

# Initialisation de l'IA Google Gemini (Unifié strictement sous 'model_ia')
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model_ia = genai.GenerativeModel('gemini-2.5-flash')

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
    """Demande à l'IA de nettoyer le texte et de générer un résumé strict en 2 phrases max, en français."""
    try:
        prompt = f"""
        Tu es NZK_AGENT. Analyse l'e-mail suivant et fais-en un résumé en MAXIMUM 2 phrases claires et structurées.
        
        CONSIGNE ABSOLUE : Tu dois OBLIGATOIREMENT rédiger le résumé en FRANÇAIS, même si l'e-mail d'origine est en anglais.
        Élimine le bruit (liens, signatures, codes) pour ne garder que l'intention réelle.

        DÉTAILS DE L'E-MAIL :
        - Expéditeur : {expediteur}
        - Sujet : {sujet}
        - Contenu brut : {corps_texte}

        RÉPONSE ATTENDUE : Uniquement ton résumé en français, rien d'autre.
        """
        # Utilisation de model_ia corrigée ici
        response = model_ia.generate_content(prompt)
        return response.text.strip()
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
        return f"<h2>Erreur OAuth ! Vérifiez vos clés.</h2><pre>{traceback.format_exc()}</pre>", 500

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


# --- ROUTE DU CHAT IA (Avec contexte des e-mails) ---
@app.route('/chat', methods=['POST'])
def chat_ia():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        if not user_message:
            return jsonify({"reponse": "Tu n'as rien écrit !"}), 400

        # Récupération discrète des 5 derniers e-mails pour donner du contexte à l'IA
        contexte_emails = "Aucun e-mail récent trouvé."
        try:
            service = get_gmail_service()
            recent = service.users().messages().list(userId='me', maxResults=5).execute().get('messages', [])
            details = []
            for m in recent:
                d = service.users().messages().get(userId='me', id=m['id'], format='full').execute()
                h = d.get('payload', {}).get('headers', [])
                frm = next((x['value'] for x in h if x['name'] == 'From'), 'Inconnu')
                sub = next((x['value'] for x in h if x['name'] == 'Subject'), 'Sans sujet')
                snip = d.get('snippet', '')
                details.append(f"- De: {frm} | Sujet: {sub} | Extrait: {snip}")
            contexte_emails = "\n".join(details)
        except Exception:
            pass # Si erreur, l'IA répondra sans contexte

        prompt_systeme = f"""
        Tu es NZK_AGENT, un assistant personnel intelligent. Voici les 5 derniers e-mails reçus par l'utilisateur :
        {contexte_emails}

        L'utilisateur te demande : "{user_message}"

        RÈGLES D'ACTION :
        1. Réponds en français, de manière concise. Tu peux renseigner l'utilisateur sur ses e-mails.
        2. SI l'utilisateur te demande de rédiger ou de générer une réponse à un de ces e-mails, rédige le message naturellement. 
        3. CRITIQUE : Si tu as rédigé un brouillon d'e-mail à envoyer, tu DOIS ABSOLUMENT inclure à la TOUTE FIN de ta réponse le bloc JSON suivant, exactement formaté et entouré des balises <DRAFT> et </DRAFT> (sans markdown autour) :
        <DRAFT>
        {{"to": "email_de_la_personne@domaine.com", "subject": "Re: Sujet du mail d'origine", "body": "Le texte exact de l'e-mail à envoyer, sans formules de politesse de l'IA"}}
        </DRAFT>
        """
        
        # Utilisation de model_ia corrigée ici
        response = model_ia.generate_content(prompt_systeme)
        return jsonify({"reponse": response.text})
        
    except Exception as e:
        print(f"ERREUR IA CHAT : {str(e)}")
        return jsonify({"reponse": "Désolé, le réseau neuronal est temporairement indisponible."}), 500

# --- ROUTE D'ENVOI D'E-MAIL ---
@app.route('/send_email', methods=['POST'])
def send_email_route():
    if 'credentials' not in session:
        return jsonify({"success": False, "error": "Session expirée, veuillez vous reconnecter."}), 401
    
    data = request.get_json()
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
    
