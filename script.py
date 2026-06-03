from flask import Flask, request, jsonify, render_template, redirect, url_for, session
# ... (garde tes autres imports)
from google_auth_oauthlib.flow import Flow

app = Flask(__name__)
app.secret_key = 'une_cle_secrete_au_hasard' # Nécessaire pour la session

# Configuration du flux OAuth
CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_flow():
    return Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri='http://localhost:5000/oauth2callback'
    )

@app.route('/login')
def login():
    flow = get_flow()
    authorization_url, state = flow.authorization_url(access_type='offline', include_granted_scopes='true')
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    state = session['state']
    flow = get_flow()
    flow.fetch_token(authorization_response=request.url)
    
    # Sauvegarde des credentials
    creds = flow.credentials
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        
    return redirect(url_for('page_agent'))

@app.route('/agent')
def page_agent():
    if not os.path.exists('token.json'):
        return render_template('agent.html', authenticated=False)
    
    # Si token existe, on affiche les mails
    try:
        service = get_gmail_service() # (Utilise ta fonction existante)
        emails = get_latest_emails(service)
        return render_template('agent.html', authenticated=True, historique=emails)
    except Exception:
        return render_template('agent.html', authenticated=False)
