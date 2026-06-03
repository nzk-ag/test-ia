import os
import logging
from datetime import datetime
import base64
from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# --- CONFIGURATION GMAIL ---
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Assure-toi que credentials.json est au bon endroit
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_latest_emails(service):
    results = service.users().messages().list(userId='me', maxResults=5).execute()
    messages = results.get('messages', [])
    liste_emails = []
    for msg in messages:
        message = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = message['payload']['headers']
        sujet = next((h['value'] for h in headers if h['name'] == 'Subject'), "Sans objet")
        snippet = message.get('snippet', 'Pas de contenu')
        liste_emails.append({'sujet': sujet, 'resume': snippet})
    return liste_emails

# --- APPLICATION FLASK ---
app = Flask(__name__)
historique_resumes = []

# Désactivation des logs Werkzeug pour plus de lisibilité
logging.getLogger('werkzeug').disabled = True

# Configuration Gemini
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") 
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash') # Utilise la version stable

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/agent')
def page_agent():
    global historique_resumes # Indispensable pour modifier la variable globale
    try:
        service = get_gmail_service()
        historique_resumes = get_latest_emails(service)
    except Exception as e:
        print(f"Erreur Gmail : {e}")
        historique_resumes = []
    return render_template('agent.html', historique=historique_resumes)

@app.route('/chat', methods=['POST'])
def chat_ia():
    data = request.get_json()
    message_utilisateur = data.get('message')
    date_du_jour = datetime.now().strftime("%d/%m/%Y")
    
    contexte_mails = ""
    if historique_resumes:
        for item in historique_resumes:
            contexte_mails += f"- Sujet: {item['sujet']} | Résumé: {item['resume']}\n"
    else:
        contexte_mails = "Aucun e-mail trouvé."

    prompt_complet = f"""Tu es NZK_AGENT. Date: {date_du_jour}.
    Voici les mails récents: {contexte_mails}
    Utilise-les si l'utilisateur pose une question dessus.
    Question: {message_utilisateur}"""
    
    try:
        reponse = model.generate_content(prompt_complet)
        return jsonify({"reponse": reponse.text}), 200
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
