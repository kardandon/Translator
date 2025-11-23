import os
import sys

# --- CRITICAL STABILITY FIXES ---
# Must be set BEFORE importing anything else that uses CTranslate2/NumPy
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
os.environ['CT2_VERBOSE'] = '1'

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import queue
import json

# Import the backend class
from translator_backend import BackendTranslator

CONFIG_FILE = "translator_config.json"

def save_settings(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("eBook Translator GUI (Local) 💬📘")
        self.geometry("600x650") # Reduced height as we removed URL fields
        self.resizable(False, False)
        
        self.settings = load_settings()
        self.queue = queue.Queue()
        self.translator = None
        
        self.create_widgets()
        
        # Simple cleanup on close
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        print("Shutting down...")
        if self.translator:
            self.translator.stop_requested = True
        self.destroy()
        sys.exit(0)

    def create_widgets(self):
        # --- INPUTS ---
        tk.Label(self, text="Input File:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(10, 0))
        frame_file = tk.Frame(self)
        frame_file.pack(fill="x", padx=10)
        self.file_path_var = tk.StringVar(value=self.settings.get("file_path", ""))
        tk.Entry(frame_file, textvariable=self.file_path_var, width=50).pack(side="left")
        tk.Button(frame_file, text="Browse", command=self.pick_file).pack(side="left", padx=5)

        # --- TRANSLATION SETTINGS ---
        tk.Label(self, text="Translation Source:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(15, 0))
        self.source_var = tk.StringVar(value=self.settings.get("source", "local"))
        
        # Removed "Local API URL" logic, merged into dropdown
        source_cb = ttk.Combobox(self, textvariable=self.source_var, 
                               values=["local", "google_free", "deepl", "gemini"], 
                               state="readonly", width=20)
        source_cb.pack(anchor="w", padx=10)
        source_cb.bind("<<ComboboxSelected>>", self.toggle_fields)

        # Frame for Languages
        frame_lang = tk.Frame(self)
        frame_lang.pack(fill="x", padx=10, pady=5)
        
        tk.Label(frame_lang, text="From (Code):").pack(side="left")
        self.source_lang_var = tk.StringVar(value=self.settings.get("source_lang", "en"))
        tk.Entry(frame_lang, textvariable=self.source_lang_var, width=5).pack(side="left", padx=(5, 15))

        tk.Label(frame_lang, text="To (Code):").pack(side="left")
        self.lang_var = tk.StringVar(value=self.settings.get("language", "tr"))
        tk.Entry(frame_lang, textvariable=self.lang_var, width=5).pack(side="left", padx=5)

        # --- API KEYS ---
        self.lbl_deepl = tk.Label(self, text="DeepL API Key:", font=("Arial", 10))
        self.deepl_var = tk.StringVar(value=self.settings.get("deepl_key", ""))
        self.entry_deepl = tk.Entry(self, textvariable=self.deepl_var, width=40, show="•")

        self.lbl_gemini = tk.Label(self, text="Gemini API Key:", font=("Arial", 10))
        self.gemini_var = tk.StringVar(value=self.settings.get("gemini_key", ""))
        self.entry_gemini = tk.Entry(self, textvariable=self.gemini_var, width=40, show="•")

        # --- SETTINGS ROW ---
        frame_opts = tk.Frame(self)
        frame_opts.pack(fill="x", padx=10, pady=15)

        self.test_mode_var = tk.BooleanVar(value=self.settings.get("test_mode", True))
        tk.Checkbutton(frame_opts, text="Test Mode", variable=self.test_mode_var).pack(side="left")
        
        tk.Label(frame_opts, text="Limit:").pack(side="left", padx=(10,2))
        self.test_limit_var = tk.IntVar(value=self.settings.get("test_limit", 5))
        tk.Entry(frame_opts, textvariable=self.test_limit_var, width=5).pack(side="left")

        # Start Index Control
        tk.Label(frame_opts, text="Start Ch:").pack(side="left", padx=(15,2))
        self.start_index_var = tk.IntVar(value=self.settings.get("start_index", 0))
        tk.Entry(frame_opts, textvariable=self.start_index_var, width=5).pack(side="left")

        # --- PROGRESS AREA ---
        self.status_label = tk.Label(self, text="Ready", font=("Arial", 10), anchor="w")
        self.status_label.pack(fill="x", padx=10, pady=(10, 0))

        self.progress = ttk.Progressbar(self, orient="horizontal", length=100, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=5)

        # --- BUTTONS FRAME ---
        frame_btns = tk.Frame(self)
        frame_btns.pack(pady=15)

        self.btn_run = tk.Button(frame_btns, text="Run Translation 🚀", font=("Arial", 14), bg="#4CAF50", fg="white", command=self.run_translation)
        self.btn_run.pack(side="left", padx=10)

        self.btn_stop = tk.Button(frame_btns, text="Terminate 🛑", font=("Arial", 14), bg="#f44336", fg="white", state="disabled", command=self.stop_translation)
        self.btn_stop.pack(side="left", padx=10)
        
        self.toggle_fields()

    def toggle_fields(self, event=None):
        mode = self.source_var.get()
        # Hide optional fields
        for w in [self.lbl_deepl, self.entry_deepl, self.lbl_gemini, self.entry_gemini]:
            w.pack_forget()
            
        if mode == "deepl":
            self.lbl_deepl.pack(anchor="w", padx=10)
            self.entry_deepl.pack(anchor="w", padx=10)
        elif mode == "gemini":
            self.lbl_gemini.pack(anchor="w", padx=10)
            self.entry_gemini.pack(anchor="w", padx=10)

    def pick_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("eBook Files", "*.epub *.mobi *.azw3")])
        if filepath: self.file_path_var.set(filepath)

    def run_translation(self):
        if not self.file_path_var.get().strip():
            messagebox.showerror("Error", "Please select a file.")
            return

        current_settings = {
            "file_path": self.file_path_var.get(),
            "source": self.source_var.get(),
            "source_lang": self.source_lang_var.get(),
            "language": self.lang_var.get(),
            # No URL needed anymore
            "deepl_key": self.deepl_var.get(),
            "gemini_key": self.gemini_var.get(),
            "test_mode": self.test_mode_var.get(),
            "test_limit": self.test_limit_var.get(),
            "start_index": self.start_index_var.get()
        }
        save_settings(current_settings)

        self.btn_run.config(state="disabled", text="Running...")
        self.btn_stop.config(state="normal")
        self.progress['value'] = 0
        
        # Instantiate backend
        self.translator = BackendTranslator(update_callback=self.queue_update)
        
        # Run everything in one thread (Backend handles setup + translation)
        t = threading.Thread(target=self.translator.run_translation, args=(current_settings,))
        t.daemon = True
        t.start()
        
        self.check_queue()

    def stop_translation(self):
        if self.translator:
            self.translator.stop_requested = True
            self.status_label.config(text="Stopping...")
            self.btn_stop.config(state="disabled")

    def queue_update(self, percent, message):
        self.queue.put((percent, message))

    def check_queue(self):
        try:
            while True:
                percent, msg = self.queue.get_nowait()
                self.progress['value'] = percent
                self.status_label.config(text=msg)
                
                if "Done!" in msg or "Error" in msg or "Stopped" in msg:
                    self.btn_run.config(state="normal", text="Run Translation 🚀")
                    self.btn_stop.config(state="disabled")
                    
                    if "Stopped" in msg:
                        messagebox.showwarning("Terminated", "Process stopped.")
                    elif "Error" in msg:
                        messagebox.showerror("Error", msg)
                    else:
                        messagebox.showinfo("Result", msg)
                    return 

        except queue.Empty:
            pass
        
        self.after(100, self.check_queue)

if __name__ == "__main__":
    app = App()
    app.mainloop()