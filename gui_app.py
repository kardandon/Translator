import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import queue
import json
import os

# Import the backend class we just created
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
        self.title("eBook Translator GUI 💬📘")
        self.geometry("600x650") 
        self.resizable(False, False)
        
        self.settings = load_settings()
        self.queue = queue.Queue() # The bridge between Thread and GUI
        self.translator = None     # Store the backend instance so we can stop it
        
        self.create_widgets()

    def create_widgets(self):
        # --- INPUTS ---
        tk.Label(self, text="Input File:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(10, 0))
        frame_file = tk.Frame(self)
        frame_file.pack(fill="x", padx=10)
        self.file_path_var = tk.StringVar(value=self.settings.get("file_path", ""))
        tk.Entry(frame_file, textvariable=self.file_path_var, width=50).pack(side="left")
        tk.Button(frame_file, text="Browse", command=self.pick_file).pack(side="left", padx=5)

        tk.Label(self, text="Translation Source:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=10)
        self.source_var = tk.StringVar(value=self.settings.get("source", "google_free"))
        ttk.Combobox(self, textvariable=self.source_var, values=["google_free", "deepl", "gemini"], state="readonly", width=20).pack(anchor="w", padx=10)

        tk.Label(self, text="Target Language:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(15, 0))
        self.lang_var = tk.StringVar(value=self.settings.get("language", "tr"))
        tk.Entry(self, textvariable=self.lang_var, width=15).pack(anchor="w", padx=10)

        # --- KEYS ---
        tk.Label(self, text="DeepL API Key:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(15, 0))
        self.deepl_var = tk.StringVar(value=self.settings.get("deepl_key", ""))
        tk.Entry(self, textvariable=self.deepl_var, width=40, show="•").pack(anchor="w", padx=10)

        tk.Label(self, text="Gemini API Key:", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(15, 0))
        self.gemini_var = tk.StringVar(value=self.settings.get("gemini_key", ""))
        tk.Entry(self, textvariable=self.gemini_var, width=40, show="•").pack(anchor="w", padx=10)

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

    def pick_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("eBook Files", "*.epub *.mobi *.azw3")])
        if filepath: self.file_path_var.set(filepath)

    def run_translation(self):
        if not self.file_path_var.get().strip():
            messagebox.showerror("Error", "Please select a file.")
            return

        # 1. Gather Settings
        current_settings = {
            "file_path": self.file_path_var.get(),
            "source": self.source_var.get(),
            "language": self.lang_var.get(),
            "deepl_key": self.deepl_var.get(),
            "gemini_key": self.gemini_var.get(),
            "test_mode": self.test_mode_var.get(),
            "test_limit": self.test_limit_var.get(),
            "start_index": self.start_index_var.get()
        }
        save_settings(current_settings)

        # 2. Reset UI
        self.btn_run.config(state="disabled", text="Running...")
        self.btn_stop.config(state="normal") # Enable Terminate Button
        self.progress['value'] = 0
        
        # 3. Create Translator Instance Here (so we can stop it later)
        self.translator = BackendTranslator(update_callback=self.queue_update)
        
        # 4. Start Background Thread
        t = threading.Thread(target=self.translator.run_translation, args=(current_settings,))
        t.daemon = True
        t.start()
        
        # 5. Start listening for updates
        self.check_queue()

    def stop_translation(self):
        """Signals the backend to stop"""
        if self.translator:
            self.translator.stop_requested = True
            self.status_label.config(text="Stopping... Waiting for running threads to finish.")
            self.btn_stop.config(state="disabled") # Prevent double clicking

    def queue_update(self, percent, message):
        # Pass data from background thread to Main Thread via Queue
        self.queue.put((percent, message))

    def check_queue(self):
        """Updates UI based on queue messages"""
        try:
            while True:
                percent, msg = self.queue.get_nowait()
                self.progress['value'] = percent
                self.status_label.config(text=msg)
                
                # Check for completion, error, or stop
                if "Done!" in msg or "Error" in msg or "Stopped" in msg:
                    self.btn_run.config(state="normal", text="Run Translation 🚀")
                    self.btn_stop.config(state="disabled")
                    
                    if "Stopped" in msg:
                        messagebox.showwarning("Terminated", "Translation stopped by user. File saved partially.")
                    else:
                        messagebox.showinfo("Result", msg)
                    return 

        except queue.Empty:
            pass
        
        self.after(100, self.check_queue) # Check again in 100ms

if __name__ == "__main__":
    app = App()
    app.mainloop()