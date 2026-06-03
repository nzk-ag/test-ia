from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
import logging
import os

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
    
    # Sécurisation et alignement avec ta variable 'historique' du HTML
    contexte_mails = ""
    if 'historique' in globals() and historique:
        for item in historique:
            contexte_mails += f"- Sujet: {item['sujet']} | Résumé: {item['resume']}\n"
    else:
        contexte_mails = "Aucun e-mail dans la base de données pour le moment."
    
    # LE PROMPT RADICAL (Priorité absolue aux connaissances générales)
    prompt_complet = f"""Tu es une IA généraliste d'élite, ultra-compétente et totalement libre d'utiliser l'ensemble de tes connaissances mondiales (code, culture, logique, explications, etc.).

Tu as également accès à cette liste de mails de l'utilisateur à titre purement informatif :
--- DÉBUT DES MAILS ---
{contexte_mails}
--- FIN DES MAILS ---

CONSIGNE DE RÉPONSE :
Réponds à la demande de l'utilisateur ci-dessous. Utilise tes connaissances générales pour TOUT ce qui est code, questions générales ou requêtes hors-sujet. N'utilise les données de la section "MAILS" que si l'utilisateur y fait explicitement référence.

Demande de l'utilisateur : {message_utilisateur}
Réponse :"""
    
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
