from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
import logging
import os
from datetime import datetime # <-- AJOUTE CETTE LIGNE

app = Flask(__name__)

historique_resumes = []
    
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
# Optionnel : désactiver totalement les logs
logging.getLogger('werkzeug').disabled = True

# 1. Configuration de l'API
# 1. Configuration de l'API
# Python va chercher la variable 'GOOGLE_API_KEY' directement dans l'environnement de Render
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY") 
genai.configure(api_key=GOOGLE_API_KEY)

# 2. Initialisation du modèle
model = genai.GenerativeModel('gemini-2.5-flash')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/agent')
def page_agent():
    # On affiche une nouvelle page HTML en lui passant notre mémoire Python
    return render_template('agent.html', historique=historique_resumes)

@app.route('/chat', methods=['POST'])
def chat_ia():
    data = request.get_json()
    message_utilisateur = data.get('message')
    
    # 1. Date dynamique pour éviter le blocage en 2024
    date_du_jour = datetime.now().strftime("%d/%m/%Y")
    
    # 2. CORRECTION DU BUG : On utilise la vraie variable 'historique_resumes'
    contexte_mails = ""
    if historique_resumes:  # <-- C'est ce nom exact qu'il fallait utiliser !
        for item in historique_resumes:
            contexte_mails += f"- Sujet: {item['sujet']} | Résumé: {item['resume']}\n"
    else:
        contexte_mails = "Aucun e-mail dans la base de données pour le moment."

    # 3. LE PROMPT INFAILLIBLE
    prompt_complet = f"""Tu es NZK_AGENT, une intelligence artificielle généraliste et ultra-compétente.
La date d'aujourd'hui est le {date_du_jour}.

RÈGLE 1 : LES CONNAISSANCES GÉNÉRALES
Tu as accès à toutes tes connaissances mondiales (code, culture, etc.). Réponds directement aux questions de l'utilisateur. Si une question concerne un événement trop récent en 2026 que tu ne connais pas, dis simplement "Je n'ai pas cette information", mais ne parle JAMAIS de la base d'e-mails pour te justifier.

RÈGLE 2 : LES E-MAILS DE L'UTILISATEUR
Tu as accès aux e-mails extraits ci-dessous. Utilise-les UNIQUEMENT si l'utilisateur te pose une question sur ses messages, sur les personnes qui lui ont écrit (comme LonniSaint), ou sur son actualité récente.
<emails_recents>
{contexte_mails}
</emails_recents>

QUESTION DE L'UTILISATEUR :
{message_utilisateur}"""
    
    try:
        reponse = model.generate_content(prompt_complet)
        return jsonify({"reponse": reponse.text}), 200
        
    except Exception as e:
        return jsonify({"erreur": str(e)}), 500

@app.route('/recevoir-mail', methods=['POST'])
def recevoir_mail():
    sujet = request.form.get('sujet')
    contenu = request.form.get('contenu')
    
    if not sujet or not contenu:
        return jsonify({"erreur": "Données manquantes"}), 400

    # 3. Appel de l'IA avec l'objet 'model' correctement
    try:
        prompt = f"Résume ce mail de manière concise. En sachant que le destinataire c'est moi et que les gens qui envoient des mails je ne les connais pas et que tu me parles comme un assistant du quotidien. Sujet: {sujet}. Contenu: {contenu}"
        reponse = model.generate_content(prompt) # Utilisation directe de model

        historique_resumes.append({
            "sujet": sujet,
            "resume": reponse.text
        })
        
        print(f"--- Résumé généré ---")
        print(reponse.text)
        
        return jsonify({"resume": reponse.text}), 200
    except Exception as e:
        print(f"Erreur : {e}")
        return jsonify({"erreur": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)
