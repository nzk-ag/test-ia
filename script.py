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
def chat_ia():
    data = request.get_json()
    message_utilisateur = data.get('message')
    
    # On prépare toujours le contexte
    contexte_mails = "Aucun e-mail récent."
    if historique_resumes:
        contexte_mails = ""
        for item in historique_resumes:
            contexte_mails += f"- Sujet: {item['sujet']} | Résumé: {item['resume']}\n"
    
    # LE NOUVEAU SUPER PROMPT (Beaucoup plus polyvalent)
    prompt_complet = f"""Tu es NZK_AGENT, une intelligence artificielle polyvalente et experte.

RÈGLES DE TON SYSTÈME :
1. Tu es capable de répondre à n'importe quelle question (code, culture générale, rédaction, mathématiques, etc.) en utilisant tes propres connaissances.
2. Tu disposes également d'une "mémoire" temporaire contenant les derniers e-mails de l'utilisateur.

MÉMOIRE TEMPORAIRE (E-mails récents) :
{contexte_mails}

INSTRUCTION :
L'utilisateur te demande : "{message_utilisateur}"

Si la demande concerne les e-mails, utilise la MÉMOIRE TEMPORAIRE pour répondre.
Si la demande porte sur n'importe quel autre sujet, ignore les e-mails et utilise tes connaissances générales pour fournir la meilleure réponse possible.
"""
    
    try:
        # On interroge Gemini avec ces nouvelles règles strictes
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
