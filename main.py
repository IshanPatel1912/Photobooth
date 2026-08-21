import customtkinter as ctk
from tkinter import filedialog, messagebox
import face_recognition
import cv2
import os
import pickle
import numpy as np
from PIL import Image, ImageTk
import concurrent.futures
import threading
import shutil
import multiprocessing

# --- Configuration ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Worker Function (CPU Heavy) ---
def process_image_file(file_data):
    path, filename = file_data
    try:
        image = face_recognition.load_image_file(path)
        h, w = image.shape[:2]
        
        # Optimization: Resize huge images
        if w > 1200:
            scale = 1200 / w
            small_img = cv2.resize(image, (0, 0), fx=scale, fy=scale)
        else:
            small_img = image

        boxes = face_recognition.face_locations(small_img, model="hog")
        if not boxes: return None
        
        # Scale boxes back up
        if w > 1200:
            scale_factor = w / 1200
            real_boxes = []
            for (top, right, bottom, left) in boxes:
                real_boxes.append((
                    int(top * scale_factor),
                    int(right * scale_factor),
                    int(bottom * scale_factor),
                    int(left * scale_factor)
                ))
            boxes = real_boxes

        encodings = face_recognition.face_encodings(image, boxes)
        return {"path": path, "encodings": encodings, "boxes": boxes}
        
    except Exception:
        return None

# --- FIXED: Photo Viewer with Instant Focus ---
class ImageViewerWindow(ctk.CTkToplevel):
    def __init__(self, photo_list, start_index, master=None):
        super().__init__(master)
        
        self.photo_list = photo_list
        self.current_index = start_index
        self.cache = {} 
        self.current_load_id = None
        
        # Window Setup
        self.title(f"Photo Viewer")
        self.geometry("1000x800")
        self.state('zoomed') 
        self.configure(fg_color="black")
        
        # UI Elements
        self.img_label = ctk.CTkLabel(self, text="Loading...", font=("Arial", 20))
        self.img_label.pack(expand=True, fill="both")
        
        # --- FIX 2: Keyboard Focus Logic ---
        # 1. Force window to top
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))
        
        # 2. Force keyboard focus immediately
        self.focus_force()
        self.after(200, lambda: self.focus_set()) # Double check focus after 0.2s
        
        # 3. Bind Keys
        self.bind("<Right>", self.next_photo)
        self.bind("<Left>", self.prev_photo)
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Button-1>", lambda e: self.focus_set()) # Clicking forces focus too

        # Show first image
        self.update_image()

    def update_image(self):
        self.title(f"Photo {self.current_index + 1} of {len(self.photo_list)}")
        path = self.photo_list[self.current_index]

        if path in self.cache:
            self.img_label.configure(image=self.cache[path], text="")
            self.preload_next()
            return

        self.img_label.configure(image=None, text="Loading...")
        self.current_load_id = path 
        threading.Thread(target=self.background_loader, args=(path,), daemon=True).start()

    def background_loader(self, path):
        try:
            img = Image.open(path)
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            
            ratio = min(screen_w/img.width, screen_h/img.height)
            new_size = (int(img.width * ratio * 0.95), int(img.height * ratio * 0.95))
            
            img = img.resize(new_size, Image.Resampling.BILINEAR)
            ctk_img = ctk.CTkImage(img, size=new_size)
            
            self.cache[path] = ctk_img
            
            if self.current_load_id == path:
                # Use after() to safely update UI from thread
                self.after(0, lambda: self.img_label.configure(image=ctk_img, text=""))
                self.preload_next()
        except: pass

    def preload_next(self):
        next_idx = self.current_index + 1
        if next_idx < len(self.photo_list):
            next_path = self.photo_list[next_idx]
            if next_path not in self.cache:
                threading.Thread(target=self.background_loader_silent, args=(next_path,), daemon=True).start()

    def background_loader_silent(self, path):
        try:
            img = Image.open(path)
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            ratio = min(screen_w/img.width, screen_h/img.height)
            new_size = (int(img.width * ratio * 0.95), int(img.height * ratio * 0.95))
            img = img.resize(new_size, Image.Resampling.BILINEAR)
            self.cache[path] = ctk.CTkImage(img, size=new_size)
        except: pass

    def next_photo(self, event=None):
        if self.current_index < len(self.photo_list) - 1:
            self.current_index += 1
            self.update_image()

    def prev_photo(self, event=None):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_image()


class UltimateGalleryPerfect(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Gallery: Perfect Edition")
        self.geometry("1300x850")
        
        self.face_groups = [] 
        self.all_scanned_data = [] 
        self.current_view_photos = [] 
        self.cancel_loading = False 

        self._setup_ui()

    def _setup_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        ctk.CTkLabel(self.sidebar, text="Gallery Perfect", font=("Arial", 24, "bold")).pack(pady=(30,20))

        self.btn_open = ctk.CTkButton(self.sidebar, text="1. Open Folder", command=self.open_folder, height=40)
        self.btn_open.pack(pady=15, padx=30, fill="x")

        # Camera
        ctk.CTkLabel(self.sidebar, text="Camera Source:", anchor="w").pack(pady=(20,5), padx=30, anchor="w")
        self.cam_option = ctk.CTkOptionMenu(self.sidebar, values=["Laptop Webcam", "IP Webcam (Phone)"], 
                                            command=self.toggle_cam_input)
        self.cam_option.pack(pady=5, padx=30, fill="x")
        
        self.ip_entry = ctk.CTkEntry(self.sidebar, placeholder_text="http://192.168.X.X:8080/video")
        self.ip_entry.pack(pady=5, padx=30, fill="x")
        self.ip_entry.pack_forget() 

        self.btn_cam = ctk.CTkButton(self.sidebar, text="2. Scan My Face", command=self.open_webcam_window, fg_color="green", height=40)
        self.btn_cam.pack(pady=15, padx=30, fill="x")
        
        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Status: Idle", text_color="gray", wraplength=250)
        self.lbl_status.pack(pady=20, padx=20)

        self.progress_bar = ctk.CTkProgressBar(self.sidebar)
        self.progress_bar.pack(pady=10, padx=30, fill="x")
        self.progress_bar.set(0)

        self.btn_save_group = ctk.CTkButton(self.sidebar, text="Save This Person", command=self.save_current_view, state="disabled", fg_color="orange", height=40)
        self.btn_save_group.pack(pady=(40,20), padx=30, fill="x")

        # Main Area
        self.tab_view = ctk.CTkTabview(self)
        self.tab_view.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.tab_people = self.tab_view.add("People Found")
        self.tab_photos = self.tab_view.add("Photos View")
        
        self.people_frame = ctk.CTkScrollableFrame(self.tab_people, label_text="Select a Person")
        self.people_frame.pack(fill="both", expand=True)

        self.photos_frame = ctk.CTkScrollableFrame(self.tab_photos, label_text="Gallery (Click to open Pro Viewer)")
        self.photos_frame.pack(fill="both", expand=True)

        for i in range(8):
            self.people_frame.grid_columnconfigure(i, weight=1)
            self.photos_frame.grid_columnconfigure(i, weight=1)

    def toggle_cam_input(self, choice):
        if choice == "IP Webcam (Phone)":
            self.ip_entry.pack(after=self.cam_option, pady=5, padx=30, fill="x")
        else:
            self.ip_entry.pack_forget()

    def open_folder(self):
        folder = filedialog.askdirectory()
        if not folder: return
        
        # Note: Cache name changed to v4 to force refresh with new logic
        cache_path = os.path.join(folder, "face_index_v4.pkl")
        if os.path.exists(cache_path):
            if messagebox.askyesno("Index Found", "Load previous scan instantly?"):
                self.load_from_cache(cache_path)
                return
        self.start_deep_scan(folder)

    def start_deep_scan(self, folder):
        self.lbl_status.configure(text="Scanning... (First time takes longer)")
        threading.Thread(target=self.run_multiprocess_scan, args=(folder,), daemon=True).start()

    def run_multiprocess_scan(self, folder):
        valid_exts = ('.jpg', '.jpeg', '.png')
        files = []
        for f in os.listdir(folder):
            if f.lower().endswith(valid_exts):
                files.append((os.path.join(folder, f), f))

        total = len(files)
        results = []
        
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {executor.submit(process_image_file, f): f for f in files}
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                data = future.result()
                if data: results.append(data)
                completed += 1
                self.progress_bar.set(completed / total if total > 0 else 0)
                self.lbl_status.configure(text=f"Scanning: {completed}/{total}")
        
        self.all_scanned_data = results
        cache_path = os.path.join(folder, "face_index_v4.pkl")
        with open(cache_path, 'wb') as f: pickle.dump(results, f)
        self.cluster_faces()

    def load_from_cache(self, path):
        self.lbl_status.configure(text="Loading cache...")
        with open(path, 'rb') as f: self.all_scanned_data = pickle.load(f)
        self.cluster_faces()

    # --- FIX 1 & 3: No Duplicates + Higher Accuracy ---
    def cluster_faces(self):
        self.lbl_status.configure(text="Grouping faces...")
        self.face_groups = [] 
        
        # Lower Tolerance = MORE STRICT (Better accuracy)
        # 0.6 is default (loose). 0.45 is strict.
        TOLERANCE = 0.48 
        
        for item in self.all_scanned_data:
            path = item['path']
            encodings = item['encodings']
            boxes = item['boxes']
            
            for i, enc in enumerate(encodings):
                found_match = False
                box = boxes[i]
                
                # Check existing groups
                for group in self.face_groups:
                    match = face_recognition.compare_faces([group['encoding']], enc, tolerance=TOLERANCE)
                    if match[0]:
                        # --- FIX: Prevent Duplicate Photos in One Group ---
                        if path not in group['photos']: 
                            group['photos'].append(path)
                        found_match = True
                        break
                
                if not found_match:
                    self.face_groups.append({
                        'encoding': enc,
                        'photos': [path],
                        'preview_path': path,
                        'preview_box': box
                    })

        self.face_groups.sort(key=lambda x: len(x['photos']), reverse=True)
        self.after(0, self.display_people_gallery)

    def display_people_gallery(self):
        for w in self.people_frame.winfo_children(): w.destroy()
        self.lbl_status.configure(text=f"Found {len(self.face_groups)} unique people.")
        self.tab_view.set("People Found")
        threading.Thread(target=self.background_load_people_thumbnails, daemon=True).start()

    def background_load_people_thumbnails(self):
        row, col = 0, 0
        max_cols = 6 

        for idx, group in enumerate(self.face_groups):
            try:
                img = Image.open(group['preview_path'])
                top, right, bottom, left = group['preview_box']
                face_height = bottom - top
                pad = int(face_height * 0.5) 
                img_w, img_h = img.size
                crop_box = (
                    max(0, left - pad), max(0, top - pad),
                    min(img_w, right + pad), min(img_h, bottom + pad)
                )
                face_crop = img.crop(crop_box)
                ctk_face = ctk.CTkImage(face_crop, size=(130, 130))
                
                self.after(0, self.add_person_btn, ctk_face, idx, len(group['photos']), row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            except: continue

    def add_person_btn(self, img, idx, count, r, c):
        text = f"Person {idx+1}\n({count})"
        btn = ctk.CTkButton(self.people_frame, image=img, text=text,
                            compound="top", fg_color="transparent", border_width=2, border_color="#333333",
                            command=lambda i=idx: self.show_person_photos(i))
        btn.grid(row=r, column=c, padx=10, pady=15, sticky="ew")

    def show_person_photos(self, group_index):
        self.cancel_loading = True 
        group = self.face_groups[group_index]
        self.current_view_photos = group['photos'] 
        
        for w in self.photos_frame.winfo_children(): w.destroy()
        
        self.tab_view.set("Photos View")
        self.btn_save_group.configure(state="normal", text=f"Save {len(group['photos'])} Photos")

        self.cancel_loading = False
        threading.Thread(target=self.background_load_photos, args=(group['photos'],), daemon=True).start()

    def background_load_photos(self, photo_paths):
        row, col = 0, 0
        max_cols = 5 
        
        for index, path in enumerate(photo_paths):
            if self.cancel_loading: return

            try:
                img = Image.open(path)
                img.thumbnail((250, 250)) 
                ctk_img = ctk.CTkImage(img, size=img.size) 
                
                self.after(0, self.add_photo_btn, ctk_img, index, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            except: pass

    def add_photo_btn(self, img, index, r, c):
        btn = ctk.CTkButton(self.photos_frame, image=img, text="",
                            fg_color="transparent", hover_color="#444444", corner_radius=0,
                            command=lambda i=index: self.open_pro_viewer(i))
        btn.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")

    def open_pro_viewer(self, start_index):
        ImageViewerWindow(self.current_view_photos, start_index, self)

    # --- Webcam Logic ---
    def open_webcam_window(self):
        source = 0
        if self.cam_option.get() == "IP Webcam (Phone)":
            url = self.ip_entry.get().strip()
            if not url:
                messagebox.showerror("Error", "Enter Phone IP")
                return
            source = url

        self.top = ctk.CTkToplevel(self)
        self.top.title("Scan Your Face")
        self.top.geometry("600x500")
        
        self.top.lift()
        self.top.attributes('-topmost', True)
        self.top.after(100, lambda: self.top.attributes('-topmost', False))
        self.top.focus_force()

        self.cam_lbl = ctk.CTkLabel(self.top, text="Connecting...")
        self.cam_lbl.pack(pady=10)
        self.btn_capture = ctk.CTkButton(self.top, text="CAPTURE", command=self.capture_and_match)
        self.btn_capture.pack(pady=10)

        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Could not connect to camera.")
            self.top.destroy()
            return
            
        self.update_webcam_feed()

    def update_webcam_feed(self):
        if self.cap and self.top.winfo_exists():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (500, 375))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb)
                imgtk = ctk.CTkImage(img, size=(500, 375))
                self.cam_lbl.configure(image=imgtk, text="")
            self.top.after(10, self.update_webcam_feed)

    def capture_and_match(self):
        ret, frame = self.cap.read()
        self.cap.release()
        self.top.destroy()
        if ret:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
            encs = face_recognition.face_encodings(rgb)
            if encs:
                self.find_person_by_face(encs[0])
            else:
                messagebox.showerror("Error", "No face seen!")

    def find_person_by_face(self, target_encoding):
        best_match_idx = -1
        best_distance = 1.0 
        for idx, group in enumerate(self.face_groups):
            dist = face_recognition.face_distance([group['encoding']], target_encoding)[0]
            if dist < 0.6 and dist < best_distance:
                best_distance = dist
                best_match_idx = idx
        
        if best_match_idx != -1:
            self.show_person_photos(best_match_idx)
        else:
            messagebox.showwarning("No Match", "Face not found in this folder.")

    def save_current_view(self):
        dest = filedialog.askdirectory()
        if dest:
            for path in self.current_view_photos:
                try: shutil.copy(path, dest)
                except: pass
            messagebox.showinfo("Success", "Photos copied!")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = UltimateGalleryPerfect()
    app.mainloop()