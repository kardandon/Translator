import os
import sys
import time
import zipfile
import html
import re
from bs4 import BeautifulSoup

class BackendTranslator:
    def __init__(self, update_callback=None):
        """
        :param update_callback: A function that accepts (percentage, message_string)
        """
        self.callback = update_callback
        self.stop_requested = False

    def log(self, percent, message):
        if self.callback:
            self.callback(percent, message)
        else:
            print(f"[{percent}%] {message}")

    def translate_text_api(self, text, cfg):
        """Routes text to the correct API based on passed config"""
        if not text: return None
        
        source = cfg.get("source", "google_free")
        target_lang = cfg.get("language", "tr")

        try:
            if source == "deepl":
                import deepl
                # Use key passed in config, not global
                translator = deepl.Translator(cfg["deepl_key"])
                result = translator.translate_text(text, target_lang=target_lang, preserve_formatting=True)
                return result.text
            
            elif source == "gemini":
                import google.generativeai as genai
                genai.configure(api_key=cfg["gemini_key"])
                model = genai.GenerativeModel("gemini-pro")
                response = model.generate_content(f"Translate to {target_lang}. Output only text: {text}")
                time.sleep(0.5)
                return response.text.strip() if response.text else None
            
            elif source == "google_free":
                from deep_translator import GoogleTranslator
                for _ in range(5):
                    try:
                        return GoogleTranslator(source='auto', target=target_lang).translate(text)
                    except:
                        pass
                raise Exception(f"[Error: {e}]")
                
                
        except Exception as e:
            return f"[Error: {e}]"
        return text

    def get_reading_order(self, zin):
        opf_path = None
        for name in zin.namelist():
            if name.endswith('.opf'):
                opf_path = name
                break
        if not opf_path: return []

        try:
            soup = BeautifulSoup(zin.read(opf_path), 'xml')
        except:
            return []

        manifest = {}
        for item in soup.find_all('item'):
            href = item.get('href')
            if item.get('id') and href:
                folder = os.path.dirname(opf_path) if '/' in opf_path else ""
                manifest[item.get('id')] = f"{folder}/{href}" if folder else href

        ordered = []
        if soup.find('spine'):
            for itemref in soup.find('spine').find_all('itemref'):
                ref_id = itemref.get('idref')
                if ref_id in manifest: ordered.append(manifest[ref_id])
        return ordered

    def run_translation(self, settings):
        input_path = settings["file_path"]
        
        if not os.path.exists(input_path):
            self.log(0, "Error: Input file not found.")
            return False
        
       

        root, ext = os.path.splitext(input_path)
        output_path = f"{root}_translated_{settings['language']}.epub"
        
        if ext.lower() in ['.mobi', '.azw3']:
            import subprocess
            temp_epub = "temp_conversion.epub"
            subprocess.run(["ebook-convert", input_path, temp_epub], check=True)
            input_path = temp_epub

        # Load settings locally
        start_index = int(settings.get("start_index", 0))
        test_mode = settings.get("test_mode", False)
        test_limit = int(settings.get("test_limit", 50))

        try:
            with zipfile.ZipFile(input_path, 'r') as zin:
                reading_order = self.get_reading_order(zin)
                if not reading_order:
                    reading_order = [n for n in zin.namelist() if n.endswith(('.html', '.xhtml'))]
                
                total_files = len(reading_order)
                translated_count_in_file = 0
                
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
                    processed_files = set()

                    for idx, filename in enumerate(reading_order):
                        if self.stop_requested: 
                            self.log(0, "Stopped by user.")
                            break
                        
                        percent = (idx / total_files) * 100
                        self.log(percent, f"Processing {idx+1}/{total_files}: {os.path.basename(filename)}")
                        
                        processed_files.add(filename)

                        # Skip front matter based on user setting
                        if idx < start_index:
                            zout.writestr(filename, zin.read(filename))
                            continue

                        raw_data = zin.read(filename)
                        
                        # Skip ToC/Nav files
                        if 'toc' in filename.lower() or 'nav' in filename.lower():
                            zout.writestr(filename, raw_data)
                            continue

                        try:
                            content = raw_data.decode('utf-8')
                        except:
                            content = raw_data.decode('latin-1', errors='ignore')

                        content = html.unescape(content)
                        soup = BeautifulSoup(content, 'html.parser')

                        primary_tags = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote']
                        elements = soup.find_all(primary_tags)
                        
                        modified = False

                        for el in elements:
                            if test_mode and translated_count_in_file >= test_limit: break
                            
                            # Safety Checks
                            if el.find_parent('a'): continue 
                            if "translation-text" in el.get('class', []): continue
                            if el.find(primary_tags): continue 

                            original_text = el.get_text().strip()
                            has_letters = re.search('[a-zA-Z]', original_text)

                            if len(original_text) > 2 and not original_text.isdigit() and has_letters:
                                # Detailed progress update
                                self.log(percent, f"Translating: {original_text[:25]}...")
                                
                                # Pass 'settings' dictionary to translation function
                                trans_text = self.translate_text_api(original_text, settings)
                                
                                if trans_text:
                                    translated_count_in_file += 1
                                    modified = True
                                    
                                    br = soup.new_tag("br")
                                    el.append(br)
                                    span = soup.new_tag("span")
                                    span.string = trans_text
                                    span['class'] = "translation-text"
                                    span['style'] = "color: #555; font-size: 90%; background-color: #f4f4f4; display: block; margin-top: 4px; padding: 4px; border-radius: 4px; line-height: 1.4;"
                                    el.append(span)

                        if modified:
                            zout.writestr(filename, soup.decode(formatter='minimal').encode('utf-8'))
                        else:
                            zout.writestr(filename, raw_data)

                    # Copy remaining assets
                    self.log(98, "Finalizing file...")
                    for item in zin.infolist():
                        if item.filename not in processed_files:
                            zout.writestr(item, zin.read(item.filename))

            self.log(100, f"Done! Saved to {os.path.basename(output_path)}")
            return True

        except Exception as e:
            self.log(0, f"Critical Error: {str(e)}")
            return False