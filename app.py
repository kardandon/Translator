import os
import sys

# --- CRITICAL STABILITY FIXES ---
# These must be set BEFORE importing argostranslate/ctranslate2 to prevent
# Segmentation Faults or "Remote Disconnected" errors on some systems.
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['CT2_VERBOSE'] = '1' # Helps debug if it crashes

from flask import Flask, request, jsonify
import logging

# --- IMPORT SAFETY CHECK ---
try:
    import argostranslate.package
    import argostranslate.translate
except Exception as e:
    print("\n" + "="*50)
    print("CRITICAL ERROR DURING IMPORT")
    print("="*50)
    print(f"Error details: {e}")
    if "numpy" in str(e).lower():
        print("\n[SOLUTION]: Your NumPy version is incompatible.")
        print("Please run: pip install -r requirements.txt --force-reinstall")
    print("="*50 + "\n")
    sys.exit(1)

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global cache to store loaded translation models
# Key: (source_code, target_code), Value: translation_object
LOADED_MODELS = {}

def load_model_logic(source_lang, target_lang):
    """
    Helper to load a model into memory, warm it up, and cache it.
    """
    # 1. Check Cache
    if (source_lang, target_lang) in LOADED_MODELS:
        return LOADED_MODELS[(source_lang, target_lang)]

    logger.info(f"Loading model {source_lang} -> {target_lang}...")
    
    # 2. Find installed package
    installed_languages = argostranslate.translate.get_installed_languages()
    from_lang = next((lang for lang in installed_languages if lang.code == source_lang), None)
    to_lang = next((lang for lang in installed_languages if lang.code == target_lang), None)

    if not from_lang or not to_lang:
        return None

    # 3. Get translation object
    translation = from_lang.get_translation(to_lang)
    
    if translation:
        # 4. Warmup: Run a dummy translation to force CTranslate2 to load weights into RAM
        translation.translate("warmup")
        LOADED_MODELS[(source_lang, target_lang)] = translation
        logger.info(f"Model {source_lang} -> {target_lang} loaded and warmed up.")
    
    return translation

@app.route('/', methods=['GET'])
def index():
    """
    Root endpoint to check if API is running in browser.
    """
    return jsonify({
        "status": "online",
        "message": "Argos Translate Local API is running",
        "endpoints": ["/languages", "/translate", "/loadmodel"]
    })

@app.route('/languages', methods=['GET'])
def get_languages():
    """
    Returns a list of installed language pairs.
    """
    try:
        installed_packages = argostranslate.package.get_installed_packages()
        languages = []
        for pkg in installed_packages:
            languages.append({
                "source": pkg.from_code,
                "target": pkg.to_code,
                "name": str(pkg)
            })
        return jsonify({"count": len(languages), "languages": languages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/loadmodel', methods=['POST'])
def load_model_endpoint():
    """
    Endpoint to explicitly load a model into memory.
    JSON Body: { "source": "en", "target": "es" }
    """
    data = request.get_json()
    if not data or 'source' not in data or 'target' not in data:
        return jsonify({"error": "Missing source or target"}), 400
    
    source = data['source']
    target = data['target']
    
    try:
        translation = load_model_logic(source, target)
        
        if translation:
            return jsonify({"status": "success", "message": f"Model {source}->{target} loaded"})
        else:
            return jsonify({"error": f"Model {source}->{target} not installed"}), 404
            
    except Exception as e:
        logger.error(f"Load error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/translate', methods=['POST'])
def translate_text():
    """
    Main translation endpoint. Optimized to use cached models.
    """
    data = request.get_json()
    
    # Validation
    if not data or 'q' not in data or 'source' not in data or 'target' not in data:
        return jsonify({"error": "Missing required fields: q, source, target"}), 400

    q = data['q']
    source = data['source']
    target = data['target']

    try:
        # 1. Check Cache (Fast Path)
        translation = LOADED_MODELS.get((source, target))
        
        # 2. Fallback (Lazy Load if not pre-loaded)
        if not translation:
            logger.info("Model not in cache, lazy loading...")
            translation = load_model_logic(source, target)
            
        if not translation:
             return jsonify({"error": f"Language pair not installed: {source} -> {target}"}), 404
             
        # 3. Perform Translation
        translated_text = translation.translate(q)

        return jsonify({
            "translatedText": translated_text,
            "source": source,
            "target": target
        })

    except Exception as e:
        logger.error(f"Translation error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Flask Server on http://0.0.0.0:5000")
    # threaded=False can sometimes help stability with CTranslate2
    app.run(host='0.0.0.0', port=5000, threaded=True)