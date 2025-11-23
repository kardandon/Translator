import os
import time
import zipfile
import html
import re
import threading
import shutil
import subprocess
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- IMPORT ARGOS DIRECTLY ---
try:
    import argostranslate.package
    import argostranslate.translate
except ImportError:
    print("Argos Translate not found. Please install requirements.")

class BackendTranslator:
    def __init__(self, update_callback=None):
        self.callback = update_callback
        self.stop_requested = False
        self.counter_lock = threading.Lock()
        self.total_translated_count = 0
        self.argos_model = None # Stores the loaded model

    def log(self, percent, message):
        if self.callback:
            self.callback(percent, message)
        else:
            print(f"[{percent:.1f}%] {message}")

    def setup_argos_model(self, source_code, target_code):
        """
        Handles the full lifecycle of the local model:
        1. Checks if installed (updates index if needed).
        2. Installs if missing.
        3. Loads into memory (warmup).
        """
        self.log(0, f"Initializing Local Model ({source_code}->{target_code})...")

        # 1. Check if package is installed
        installed = False
        try:
            installed_packages = argostranslate.package.get_installed_packages()
            for pkg in installed_packages:
                if pkg.from_code == source_code and pkg.to_code == target_code:
                    installed = True
                    break
        except Exception:
            pass

        # 2. Install if missing
        if not installed:
            self.log(0, "Updating package index...")
            argostranslate.package.update_package_index()
            
            self.log(0, f"Downloading model {source_code}->{target_code} (this may take a while)...")
            available_packages = argostranslate.package.get_available_packages()
            package_to_install = next(
                (pkg for pkg in available_packages 
                 if pkg.from_code == source_code and pkg.to_code == target_code), 
                None
            )
            
            if package_to_install:
                download_path = package_to_install.download()
                argostranslate.package.install_from_path(download_path)
                self.log(0, "Model installed successfully.")
            else:
                raise Exception(f"No model found for {source_code}->{target_code}")

        # 3. Load Model
        self.log(0, "Loading model into memory...")
        installed_languages = argostranslate.translate.get_installed_languages()
        from_lang = next((lang for lang in installed_languages if lang.code == source_code), None)
        to_lang = next((lang for lang in installed_languages if lang.code == target_code), None)

        if from_lang and to_lang:
            self.argos_model = from_lang.get_translation(to_lang)
            # Warmup
            self.argos_model.translate("warmup")
            self.log(0, "Model loaded and ready.")
        else:
            raise Exception("Failed to load translation model after installation.")

    def translate_text_api(self, text, cfg):
        """Routes text to the correct API"""
        if not text: return None
        
        source = cfg.get("source", "google_free")
        target_lang = cfg.get("language", "tr")

        try:
            # --- OPTION 1: LOCAL (DIRECT) ---
            if source == "local":
                if self.argos_model:
                    return self.argos_model.translate(text)
                else:
                    return "[Error: Model not loaded]"

            # --- OPTION 2: DEEPL ---
            elif source == "deepl":
                import deepl
                translator = deepl.Translator(cfg["deepl_key"])
                result = translator.translate_text(text, target_lang=target_lang, preserve_formatting=True)
                return result.text
            
            # --- OPTION 3: GEMINI ---
            elif source == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=cfg["gemini_key"])
                model = genai.GenerativeModel("gemini-pro")
                response = model.generate_content(f"Translate to {target_lang}. Output only text: {text}")
                time.sleep(0.5) 
                return response.text.strip() if response.text else None
            
            # --- OPTION 4: GOOGLE FREE ---
            elif source == "google_free":
                from deep_translator import GoogleTranslator
                for _ in range(3):
                    try:
                        return GoogleTranslator(source='auto', target=target_lang).translate(text)
                    except:
                        time.sleep(1)
                raise Exception("Connection timeout")
                
        except Exception as e:
            return f"[Error: {str(e)[:20]}...]"
        return text

    def _process_single_file(self, filename, raw_data, settings):
        """Worker function"""
        if self.stop_requested: return filename, raw_data, False
        if 'toc' in filename.lower() or 'nav' in filename.lower(): return filename, raw_data, False

        try:
            content = raw_data.decode('utf-8')
        except:
            content = raw_data.decode('latin-1', errors='ignore')

        soup = BeautifulSoup(content, 'html.parser')
        primary_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'blockquote']
        elements = soup.find_all(primary_tags)
        
        modified = False
        test_mode = settings.get("test_mode", False)
        test_limit = int(settings.get("test_limit", 50))

        for el in elements:
            if self.stop_requested: break
            
            if test_mode:
                with self.counter_lock:
                    if self.total_translated_count >= test_limit: break

            if el.find_parent('a') or "translation-text" in el.get('class', []): continue
            
            original_text = el.get_text().strip()
            if len(original_text) > 2 and re.search('[a-zA-Z]', original_text):
                
                trans_text = self.translate_text_api(original_text, settings)
                
                if trans_text and not trans_text.startswith("[Error"):
                    if test_mode:
                        with self.counter_lock: self.total_translated_count += 1
                    
                    modified = True
                    br = soup.new_tag("br")
                    el.append(br)
                    span = soup.new_tag("span")
                    span.string = trans_text
                    span['class'] = "translation-text"
                    span['style'] = "color: #555; font-size: 90%; background-color: #f4f4f4; display: block; margin-top: 4px; padding: 4px; border-radius: 4px;"
                    el.append(span)

        if modified:
            return filename, soup.decode(formatter='minimal').encode('utf-8'), True
        return filename, raw_data, False

    def run_translation(self, settings):
        input_path = settings["file_path"]
        if not os.path.exists(input_path):
            self.log(0, "Error: File not found.")
            return
            
        # --- PHASE 0: SETUP LOCAL MODEL ---
        if settings.get("source") == "local":
            try:
                self.setup_argos_model(settings.get("source_lang", "en"), settings.get("language", "tr"))
            except Exception as e:
                self.log(0, f"Error initializing local model: {e}")
                return

        self.total_translated_count = 0
        root, ext = os.path.splitext(input_path)
        output_path = f"{root}_translated_{settings['language']}.epub"
        
        # Helper for mobi conversion
        if ext.lower() in ['.mobi', '.azw3']:
            self.log(0, f"Converting {ext} to EPUB...")
            temp_epub = f"{root}_temp_converted.epub"
            try:
                subprocess.run(["ebook-convert", input_path, temp_epub], check=True, capture_output=True)
                input_path = temp_epub
            except:
                self.log(0, "Error: Calibre ebook-convert not found.")
                return

        # --- CONCURRENCY SETTING ---
        # Direct local model inference in threads is safe but resource heavy. 
        # We limit to 4 threads for local to prevent CPU thrashing.
        source = settings.get("source")
        if source == "local":
            max_workers = 1
        elif source == "deepl":
            max_workers = 16
        else:
            max_workers = 4

        try:
            with zipfile.ZipFile(input_path, 'r') as zin:
                file_list = [n for n in zin.namelist() if n.endswith(('.html', '.xhtml'))]
                total_files = len(file_list)
                
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                    
                    # Copy non-html
                    for item in zin.infolist():
                        if not item.filename.endswith(('.html', '.xhtml')):
                            zout.writestr(item, zin.read(item.filename))
                    
                    # Process HTML
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        future_map = {}
                        for fname in file_list:
                            data = zin.read(fname)
                            future = executor.submit(self._process_single_file, fname, data, settings)
                            future_map[future] = fname
                        
                        completed = 0
                        for future in as_completed(future_map):
                            if self.stop_requested: break
                            fname, data, mod = future.result()
                            zout.writestr(fname, data)
                            completed += 1
                            self.log((completed/total_files)*100, f"Processed {fname}...")

            if not self.stop_requested:
                self.log(100, f"Done! Saved to {os.path.basename(output_path)}")
            else:
                self.log(0, "Stopped by user.")
                
            if ext.lower() in ['.mobi', '.azw3'] and os.path.exists(input_path):
                os.remove(input_path)

        except zipfile.BadZipFile:
            self.log(0, "Error: Invalid EPUB file.")
        except Exception as e:
            self.log(0, f"Critical Error: {e}")