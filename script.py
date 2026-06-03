from flask import Flask, request, jsonify, render_template
import google.generativeai as genai
import logging

app = Flask(__name__)

historique_resumes = []
    
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
# Optionnel : désactiver totalement les logs
logging.getLogger('werkzeug').disabled = True

# 1. Configuration de l'API
GOOGLE_API_KEY = "AQ.Ab8RN6JvbcaIBWcRs6O-OtIuNPmp6ngoTPJSZrddyE1ghFuwzA" # Remplace par ta vraie clé
genai.configure(api_key=GOOGLE_API_KEY)

# 2. Initialisation du modèle
model = genai.GenerativeModel('gemini-2.5-flash-lite')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/agent')
def page_agent():
    # On affiche une nouvelle page HTML en lui passant notre mémoire Python
    return render_template('agent.html', historique=historique_resumes)

@app.route('/chat', methods=['POST'])
@app.route('/chat', methods=['POST'])
def chat_ia():
    data = request.get_json()
    message_utilisateur = data.get('message')
    
    # Préparation propre du contexte des e-mails
    contexte_mails = "Aucun e-mail récent dans la base de données."
    if historique_resumes:  # Modifie par 'historique' si c'est le nom de ta liste globale
        contexte_mails = ""
        for item in historique_resumes:
            contexte_mails += f"- Sujet: {item['sujet']} | Résumé: {item['resume']}\n"
    
    # LE PROMPT ULTRA-DIRECT (Aiguillage forcé)
    prompt_complet = f"""Tu es NZK_AGENT, un assistant d'élite ultra-polyvalent. Tu es un expert absolu en développement, en infrastructure, en culture générale et en assistance business.

Tu as deux sources d'informations distinctes :
1. Ta propre base de connaissances globale (tu sais TOUT faire, coder, expliquer, inventer).
2. Les données internes de l'utilisateur isolées dans la balise ci-dessous.

<emails_recents>
{contexte_mails}
</emails_recents>

CONSIGNE CRITIQUE : 
- Si la question de l'utilisateur concerne ses e-mails, utilise les données de la balise <emails_recents>.
- Si la question porte sur N'IMPORTE QUEL AUTRE SUJET (demande de code, question générale, blague, etc.), ignore complètement la balise <emails_recents> et réponds en utilisant ton intelligence générale. Ne dis JAMAIS que tu n'as pas l'information dans les e-mails si la question n'a rien à voir avec eux.

Exécute la commande suivante reçue sur ton terminal :
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
