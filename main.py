import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
import queue
import cv2
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

COLORS = {
    "bg": "#1e1e2e",
    "fg": "#cdd6f4",
    "accent": "#89b4fa",
    "surface": "#313244",
    "surface_hover": "#45475a",
    "canvas_bg": "#11111b",
    "status_bg": "#181825",
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_DEFAULTS = {
    "save_folder": os.path.join(os.path.expanduser("~"), "Pictures", "FrameExtractor"),
    "save_format": "png",
    "jpg_quality": 95,
    "recent_files": [],
}
config = {}


def load_config():
    global config
    config = dict(_DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            config.update(data)
        except Exception:
            pass


def save_config():
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


load_config()

cap = None
current_frame = None
current_frame_num = 0
total_frames = 0
bookmarks = []
video_fps = 0
video_w = 0
video_h = 0
photo_image = None
is_playing = False
play_after_id = None
slider_updating = False
video_path = None
frame_cache = {}
cache_lock = threading.Lock()
cache_radius = 5
deferred_seek_id = None

preload_queue = queue.Queue(maxsize=1)
preloader_stop_event = threading.Event()

def preloader_worker():
    local_cap = None
    local_video_path = None
    while not preloader_stop_event.is_set():
        try:
            center = preload_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if center is None:
            continue
        if video_path != local_video_path:
            if local_cap is not None:
                local_cap.release()
            local_cap = cv2.VideoCapture(video_path) if video_path else None
            local_video_path = video_path
        if local_cap is None or not local_cap.isOpened():
            continue
        start = max(0, center - cache_radius)
        end = min(total_frames - 1, center + cache_radius)
        for fn in range(start, end + 1):
            if preloader_stop_event.is_set():
                break
            with cache_lock:
                if fn in frame_cache:
                    continue
            local_cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
            ret, frame = local_cap.read()
            if ret:
                with cache_lock:
                    frame_cache[fn] = frame.copy()
        lower = max(0, center - cache_radius * 2)
        upper = min(total_frames - 1, center + cache_radius * 2)
        with cache_lock:
            for key in list(frame_cache.keys()):
                if key < lower or key > upper:
                    del frame_cache[key]
    if local_cap is not None:
        local_cap.release()

root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
root.title("Frame Extractor")
root.geometry("960x680")
root.minsize(800, 550)
root.configure(bg=COLORS["bg"])

# Setup window icon
icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
if os.path.exists(icon_path):
    try:
        root.iconbitmap(icon_path)
    except Exception:
        pass

# Load GUI Icons
icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
gui_icons = {}

def load_gui_icon(name):
    if name in gui_icons:
        return gui_icons[name]
    path = os.path.join(icons_dir, f"{name}.png")
    if os.path.exists(path):
        try:
            img = Image.open(path)
            gui_icons[name] = ImageTk.PhotoImage(img)
            return gui_icons[name]
        except Exception:
            pass
    return ""

if os.path.exists(icons_dir):
    for f in os.listdir(icons_dir):
        if f.endswith(".png"):
            load_gui_icon(f[:-4])



style = ttk.Style(root)
style.theme_use("clam")

style.configure("Dark.TFrame", background=COLORS["bg"])
style.configure("Surface.TFrame", background=COLORS["surface"])

style.configure(
    "Dark.TButton",
    background=COLORS["surface"],
    foreground=COLORS["fg"],
    borderwidth=0,
    padding=(12, 6),
    font=("Segoe UI", 9),
)
style.map(
    "Dark.TButton",
    background=[("active", COLORS["surface_hover"]), ("pressed", COLORS["surface_hover"])],
    foreground=[("active", COLORS["accent"])],
)

style.configure(
    "Accent.TButton",
    background=COLORS["accent"],
    foreground=COLORS["bg"],
    borderwidth=0,
    padding=(12, 6),
    font=("Segoe UI", 9, "bold"),
)
style.map(
    "Accent.TButton",
    background=[("active", COLORS["surface_hover"]), ("pressed", COLORS["surface_hover"])],
)

style.configure(
    "Dark.TLabel",
    background=COLORS["bg"],
    foreground=COLORS["fg"],
    font=("Segoe UI", 9),
)
style.configure(
    "Info.TLabel",
    background=COLORS["bg"],
    foreground=COLORS["accent"],
    font=("Segoe UI", 9),
)

style.configure(
    "Dark.Horizontal.TScale",
    background=COLORS["bg"],
    foreground=COLORS["fg"],
    troughcolor=COLORS["surface"],
    sliderthickness=12,
)

style.configure(
    "Status.TFrame",
    background=COLORS["status_bg"],
)
style.configure(
    "Status.TLabel",
    background=COLORS["status_bg"],
    foreground=COLORS["fg"],
    font=("Segoe UI", 9),
)

def open_settings():
    settings_win = tk.Toplevel(root)
    settings_win.title("Configuracion")
    settings_win.configure(bg="#1e1e2e")
    settings_win.resizable(False, False)
    settings_win.transient(root)
    settings_win.grab_set()

    settings_win.update_idletasks()
    rw = root.winfo_width()
    rh = root.winfo_height()
    rx = root.winfo_x()
    ry = root.winfo_y()
    sw, sh = 450, 350
    x = rx + (rw - sw) // 2
    y = ry + (rh - sh) // 2
    settings_win.geometry(f"{sw}x{sh}+{x}+{y}")

    folder_var = tk.StringVar(value=config.get("save_folder", ""))

    tk.Label(settings_win, text="Carpeta de guardado", bg="#1e1e2e", fg="#cdd6f4",
             font=("Segoe UI", 9)).pack(anchor=tk.W, padx=12, pady=(12, 2))

    folder_frame = tk.Frame(settings_win, bg="#1e1e2e")
    folder_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

    folder_entry = tk.Entry(folder_frame, textvariable=folder_var, bg="#313244", fg="#cdd6f4",
                            insertbackground="#cdd6f4", relief=tk.FLAT, font=("Segoe UI", 9))
    folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)

    def browse_folder():
        path = filedialog.askdirectory()
        if path:
            folder_var.set(path)

    tk.Button(folder_frame, text="Examinar...", bg="#313244", fg="#cdd6f4",
              activebackground="#45475a", activeforeground="#89b4fa", relief=tk.FLAT,
              command=browse_folder, font=("Segoe UI", 9), padx=8).pack(side=tk.LEFT, padx=(6, 0))

    format_var = tk.StringVar(value=config.get("save_format", "png"))

    tk.Label(settings_win, text="Formato", bg="#1e1e2e", fg="#cdd6f4",
             font=("Segoe UI", 9)).pack(anchor=tk.W, padx=12, pady=(0, 2))

    radio_frame = tk.Frame(settings_win, bg="#1e1e2e")
    radio_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

    tk.Radiobutton(radio_frame, text="PNG", variable=format_var, value="png",
                   bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244",
                   activebackground="#1e1e2e", activeforeground="#89b4fa",
                   font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 16))
    tk.Radiobutton(radio_frame, text="JPG", variable=format_var, value="jpg",
                   bg="#1e1e2e", fg="#cdd6f4", selectcolor="#313244",
                   activebackground="#1e1e2e", activeforeground="#89b4fa",
                   font=("Segoe UI", 9)).pack(side=tk.LEFT)

    quality_label = tk.Label(settings_win, text="Calidad JPG", bg="#1e1e2e", fg="#cdd6f4",
                             font=("Segoe UI", 9))
    quality_scale = tk.Scale(settings_win, from_=1, to=100, orient=tk.HORIZONTAL,
                             bg="#1e1e2e", fg="#cdd6f4", troughcolor="#313244",
                             highlightthickness=0, font=("Segoe UI", 9))
    quality_scale.set(config.get("jpg_quality", 95))

    def toggle_quality(*args):
        if format_var.get() == "jpg":
            quality_label.pack(anchor=tk.W, padx=12, pady=(0, 2))
            quality_scale.pack(fill=tk.X, padx=12, pady=(0, 12))
        else:
            quality_label.pack_forget()
            quality_scale.pack_forget()

    toggle_quality()
    format_var.trace_add("write", toggle_quality)

    btn_frame = tk.Frame(settings_win, bg="#1e1e2e")
    btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=12)

    def save_settings():
        config["save_folder"] = folder_var.get()
        config["save_format"] = format_var.get()
        config["jpg_quality"] = quality_scale.get()
        save_config()
        settings_win.destroy()

    tk.Button(btn_frame, text="Guardar", bg="#89b4fa", fg="#1e1e2e",
              activebackground="#45475a", relief=tk.FLAT, command=save_settings,
              font=("Segoe UI", 9, "bold"), padx=16, pady=4).pack(side=tk.RIGHT, padx=(6, 0))
    tk.Button(btn_frame, text="Cancelar", bg="#313244", fg="#cdd6f4",
              activebackground="#45475a", activeforeground="#89b4fa", relief=tk.FLAT,
              command=settings_win.destroy, font=("Segoe UI", 9), padx=16, pady=4).pack(side=tk.RIGHT)


# ── TOP BAR ───────────────────────────────────────────────────────
top_bar = ttk.Frame(root, style="Dark.TFrame", padding=(8, 6))
top_bar.pack(side=tk.TOP, fill=tk.X)

def preload_cache(center):
    if video_path is None:
        return
    try:
        preload_queue.get_nowait()
    except queue.Empty:
        pass
    try:
        preload_queue.put_nowait(center)
    except queue.Full:
        pass


def show_on_canvas(frame):
    global photo_image
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    cw = canvas.winfo_width()
    ch = canvas.winfo_height()
    if cw < 2 or ch < 2:
        return
    h, w = frame_rgb.shape[:2]
    scale = min(cw / w, ch / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    if new_w < 1 or new_h < 1:
        return
    resized = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
    img = Image.fromarray(resized)
    photo_image = ImageTk.PhotoImage(img)
    canvas.delete("all")
    canvas.create_image(cw // 2, ch // 2, image=photo_image, anchor=tk.CENTER)

_dnd_overlay_id = None


def on_drop(event):
    global _dnd_overlay_id
    if _dnd_overlay_id is not None:
        canvas.delete(_dnd_overlay_id)
        _dnd_overlay_id = None
    raw = event.data
    path = raw.strip("{}")
    open_video(path)


def _on_drag_enter(event):
    global _dnd_overlay_id
    if _dnd_overlay_id is not None:
        return
    cw = canvas.winfo_width()
    ch = canvas.winfo_height()
    _dnd_overlay_id = canvas.create_text(
        cw // 2, ch // 2,
        text="Suelta el video aquí",
        fill=COLORS["accent"],
        font=("Segoe UI", 18, "bold"),
        anchor=tk.CENTER,
    )


def _on_drag_leave(event):
    global _dnd_overlay_id
    if _dnd_overlay_id is not None:
        canvas.delete(_dnd_overlay_id)
        _dnd_overlay_id = None


def update_bookmark_button_state():
    if 'bookmark_btn' in globals() and bookmark_btn.winfo_exists():
        bookmark_btn.config(
            text=f" ({len(bookmarks)})",
            image=gui_icons.get("bookmark_active" if current_frame_num in bookmarks else "bookmark", "")
        )

def display_frame_at(frame_num):
    global current_frame, current_frame_num
    # try cache first
    with cache_lock:
        cached = frame_cache.get(frame_num)
    if cached is not None:
        current_frame = cached.copy()
        current_frame_num = frame_num
        show_on_canvas(cached)
    else:
        if cap.get(cv2.CAP_PROP_POS_FRAMES) != frame_num:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            return
        current_frame = frame.copy()
        current_frame_num = frame_num
        show_on_canvas(frame)
    # queue this frame for background caching (only when not playing)
    if not is_playing:
        preload_cache(frame_num)
    update_filmstrip_highlight()
    update_bookmark_button_state()

# ── RECENT MENU ───────────────────────────────────────────────────
recent_menu = tk.Menu(root, tearoff=0, bg=COLORS['surface'], fg=COLORS['fg'],
                      activebackground=COLORS['surface_hover'], activeforeground=COLORS['accent'])

def update_recent_menu():
    recent_menu.delete(0, tk.END)
    recent = config.get('recent_files', [])
    if recent:
        for p in recent:
            recent_menu.add_command(label=os.path.basename(p), command=lambda path=p: open_video(path))
    else:
        recent_menu.add_command(label='No hay recientes', state=tk.DISABLED)

def show_recent_menu(event):
    recent_menu.tk_popup(event.x_root, event.y_root)

def open_video(path=None):
    global cap, total_frames, video_fps, video_w, video_h, current_frame, current_frame_num
    global video_path, frame_cache
    if path is None:
        path = filedialog.askopenfilename(
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("All Files", "*.*")]
        )
    if not path:
        return
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return
    video_path = path
    abs_path = os.path.abspath(path)
    recent = config.get('recent_files', [])
    if abs_path in recent:
        recent.remove(abs_path)
    recent.insert(0, abs_path)
    config['recent_files'] = recent[:8]
    save_config()
    update_recent_menu()
    # clear frame cache for new video
    with cache_lock:
        frame_cache.clear()
    bookmarks.clear()
    update_bookmark_button_state()
    draw_bookmarks()
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    video_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    video_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    current_frame_num = 0
    file_label.config(text=f"Archivo: {os.path.basename(path)}")
    res_label.config(text=f"Res.: {video_w}×{video_h}")
    fps_label.config(text=f"FPS: {video_fps:.2f}")
    slider.config(to=total_frames - 1 if total_frames > 1 else 0)
    display_frame_at(0)
    update_frame_label(0)
    update_time_label(0)
    generate_filmstrip()
    enable_controls()

def update_frame_label(n):
    frame_label.config(text=f"Frame: {n}/{total_frames - 1}" if total_frames > 0 else "Frame: —")


def format_time(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def update_time_label(frame_number):
    if video_fps > 0 and total_frames > 0:
        current_time = frame_number / video_fps
        total_time = total_frames / video_fps
        time_label.config(text=f"{format_time(current_time)} / {format_time(total_time)}")
    else:
        time_label.config(text="00:00:00 / 00:00:00")


def on_slider_change(value):
    global slider_updating, deferred_seek_id
    if slider_updating:
        return
    frame_num = int(float(value))
    if is_playing:
        stop_playback()
    if cap is None:
        return
    with cache_lock:
        cached = frame_cache.get(frame_num)
    if cached is not None:
        display_frame_at(frame_num)
        update_frame_label(frame_num)
        update_time_label(frame_num)
        return
    if deferred_seek_id is not None:
        root.after_cancel(deferred_seek_id)
    deferred_seek_id = root.after(30, perform_deferred_seek, frame_num)


def perform_deferred_seek(frame_num):
    global deferred_seek_id
    deferred_seek_id = None
    if is_playing:
        stop_playback()
    display_frame_at(frame_num)
    update_frame_label(frame_num)
    update_time_label(frame_num)


def play_loop():
    global is_playing, play_after_id, slider_updating, current_frame_num
    if not is_playing or cap is None:
        return
    pos = current_frame_num
    if pos >= total_frames - 1:
        is_playing = False
        btn_play.config(image=gui_icons.get("play", ""))
        return
    display_frame_at(pos)
    slider_updating = True
    slider.set(pos)
    slider_updating = False
    update_frame_label(pos)
    update_time_label(pos)
    current_frame_num = min(total_frames - 1, current_frame_num + 1)
    delay = int(1000 / video_fps) if video_fps > 0 else 33
    play_after_id = root.after(delay, play_loop)

def play_pause():
    global is_playing, play_after_id
    if is_playing:
        is_playing = False
        btn_play.config(image=gui_icons.get("play", ""))
        if play_after_id is not None:
            root.after_cancel(play_after_id)
            play_after_id = None
    else:
        is_playing = True
        btn_play.config(image=gui_icons.get("pause", ""))
        play_loop()

def stop_playback():
    global is_playing, play_after_id
    if is_playing:
        is_playing = False
        btn_play.config(image=gui_icons.get("play", ""))
        if play_after_id is not None:
            root.after_cancel(play_after_id)
            play_after_id = None

def go_first():
    stop_playback()
    if cap is not None:
        display_frame_at(0)
        slider.set(0)
        update_frame_label(0)
        update_time_label(0)

def go_last():
    stop_playback()
    if cap is not None:
        last = total_frames - 1
        display_frame_at(last)
        slider.set(last)
        update_frame_label(last)
        update_time_label(last)

def prev_frame():
    stop_playback()
    if cap is not None:
        pos = max(0, current_frame_num - 1)
        display_frame_at(pos)
        slider.set(pos)
        update_frame_label(pos)
        update_time_label(pos)

def next_frame():
    stop_playback()
    if cap is not None:
        pos = min(total_frames - 1, current_frame_num + 1)
        display_frame_at(pos)
        slider.set(pos)
        update_frame_label(pos)
        update_time_label(pos)

def skip_back():
    stop_playback()
    if cap is not None:
        pos = max(0, current_frame_num - 10)
        display_frame_at(pos)
        slider.set(pos)
        update_frame_label(pos)
        update_time_label(pos)

def skip_forward():
    stop_playback()
    if cap is not None:
        pos = min(total_frames - 1, current_frame_num + 10)
        display_frame_at(pos)
        slider.set(pos)
        update_frame_label(pos)
        update_time_label(pos)

def open_save_folder():
    save_folder = config.get("save_folder", "")
    if os.path.isdir(save_folder):
        os.startfile(save_folder)
    else:
        messagebox.showwarning("Carpeta no encontrada", f"La carpeta no existe:\n{save_folder}")

def toggle_bookmark(event=None):
    global bookmarks
    if cap is None:
        return
    if current_frame_num in bookmarks:
        bookmarks.remove(current_frame_num)
    else:
        bookmarks.append(current_frame_num)
    update_bookmark_button_state()
    draw_bookmarks()

def draw_bookmarks(event=None):
    bookmarks_canvas.delete("all")
    if total_frames <= 1:
        return
    cw = bookmarks_canvas.winfo_width()
    ch = bookmarks_canvas.winfo_height()
    for frame in bookmarks:
        x = int((frame / (total_frames - 1)) * cw)
        bookmarks_canvas.create_rectangle(x - 2, 0, x + 2, ch, fill=COLORS["accent"], outline="")

def export_bookmarks():
    if not bookmarks:
        messagebox.showinfo("Marcadores", "No hay frames marcados.")
        return
    
    fmt = config["save_format"]
    ext = fmt
    quality = config["jpg_quality"]
    save_folder = config["save_folder"]
    os.makedirs(save_folder, exist_ok=True)
    
    saved = 0
    for frame_num in bookmarks:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if not ret:
            continue
        filename = f"frame_{frame_num:05d}.{ext}"
        full_path = os.path.join(save_folder, filename)
        if fmt == "jpg":
            cv2.imwrite(full_path, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        else:
            cv2.imwrite(full_path, frame)
        saved += 1
    messagebox.showinfo("Completado", f"Se exportaron {saved} frames a:\n{save_folder}")

filmstrip_labels = []
filmstrip_images = []
filmstrip_frames = []

def generate_filmstrip():
    global filmstrip_labels, filmstrip_images, filmstrip_frames
    for lbl in filmstrip_labels:
        lbl.destroy()
    filmstrip_labels.clear()
    filmstrip_images.clear()
    filmstrip_frames.clear()
    
    if total_frames <= 1 or video_path is None:
        return
        
    num_thumbs = min(20, max(5, int(root.winfo_width() / 90)))
    step = max(1, total_frames // num_thumbs)
    
    def worker():
        local_cap = cv2.VideoCapture(video_path)
        if not local_cap.isOpened():
            return
        
        for i in range(num_thumbs):
            fn = min(total_frames - 1, i * step)
            local_cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
            ret, frame = local_cap.read()
            if not ret:
                break
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w = frame_rgb.shape[:2]
            scale = min(80/w, 45/h)
            new_w, new_h = max(1, int(w*scale)), max(1, int(h*scale))
            resized = cv2.resize(frame_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
            
            def update_ui(img_arr=resized, frame_idx=fn):
                img = Image.fromarray(img_arr)
                pimg = ImageTk.PhotoImage(img)
                filmstrip_images.append(pimg)
                filmstrip_frames.append(frame_idx)
                
                lbl = tk.Label(filmstrip_inner, image=pimg, bg=COLORS["canvas_bg"], bd=2, relief=tk.FLAT)
                lbl.pack(side=tk.LEFT, padx=2, pady=2)
                lbl.bind("<Button-1>", lambda e, f=frame_idx: [stop_playback(), display_frame_at(f), slider.set(f), update_frame_label(f), update_time_label(f)])
                filmstrip_labels.append(lbl)
                update_filmstrip_highlight()
                
            root.after(0, update_ui)
        local_cap.release()
        
    threading.Thread(target=worker, daemon=True).start()

def update_filmstrip_highlight():
    if not filmstrip_frames:
        return
    closest_idx = 0
    min_dist = float('inf')
    for i, f in enumerate(filmstrip_frames):
        d = abs(f - current_frame_num)
        if d < min_dist:
            min_dist = d
            closest_idx = i
            
    for i, lbl in enumerate(filmstrip_labels):
        if i == closest_idx:
            lbl.config(bg=COLORS["accent"], relief=tk.SOLID)
        else:
            lbl.config(bg=COLORS["canvas_bg"], relief=tk.FLAT)

def enable_controls():
    btn_first.config(state=tk.NORMAL)
    btn_prev.config(state=tk.NORMAL)
    btn_play.config(state=tk.NORMAL)
    btn_next.config(state=tk.NORMAL)
    btn_last.config(state=tk.NORMAL)
    save_btn.config(state=tk.NORMAL)
    open_folder_btn.config(state=tk.NORMAL)
    batch_btn.config(state=tk.NORMAL)
    bookmark_btn.config(state=tk.NORMAL)
    export_bookmarks_btn.config(state=tk.NORMAL)

def save_frame():
    if current_frame is None:
        messagebox.showwarning("Sin Frame", "No hay ningún frame para guardar.")
        return

    fmt = config["save_format"]
    ext = fmt
    quality = config["jpg_quality"]

    save_folder = config["save_folder"]
    os.makedirs(save_folder, exist_ok=True)

    filename = f"frame_{current_frame_num:05d}.{ext}"
    full_path = os.path.join(save_folder, filename)

    if fmt == "jpg":
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        ret, buffer = cv2.imencode(".jpg", current_frame, encode_params)
    else:
        ret, buffer = cv2.imencode(".png", current_frame)

    if ret:
        size_bytes = len(buffer)
        if size_bytes >= 1024 * 1024:
            size_val = size_bytes / (1024 * 1024)
            size_unit = "MB"
        else:
            size_val = size_bytes / 1024
            size_unit = "KB"
    else:
        size_val = 0
        size_unit = "KB"

    status_label.config(text=f"Guardando... (~{size_val:.1f} {size_unit}, {fmt.upper()})")

    if fmt == "jpg":
        cv2.imwrite(full_path, current_frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:
        cv2.imwrite(full_path, current_frame)

    status_label.config(text=f"\u2713 Frame guardado: {filename} ({size_val:.1f} {size_unit})")
    root.after(4000, lambda: status_label.config(text="Listo"))

def open_batch_dialog():
    stop_playback()

    modal = tk.Toplevel(root)
    modal.title("Extraccion por Lotes")
    modal.configure(bg=COLORS["bg"])
    modal.resizable(False, False)
    modal.transient(root)
    modal.grab_set()

    modal.update_idletasks()
    rw = root.winfo_width()
    rh = root.winfo_height()
    rx = root.winfo_x()
    ry = root.winfo_y()
    dw, dh = 380, 180
    x = rx + (rw - dw) // 2
    y = ry + (rh - dh) // 2
    modal.geometry(f"{dw}x{dh}+{x}+{y}")

    tk.Label(
        modal, text="Extraer 1 frame cada N frames:", bg=COLORS["bg"], fg=COLORS["fg"],
        font=("Segoe UI", 9)
    ).pack(anchor=tk.W, padx=12, pady=(12, 4))

    n_var = tk.IntVar(value=30)
    spinbox = tk.Spinbox(
        modal, from_=1, to=10000, textvariable=n_var, bg=COLORS["surface"], fg=COLORS["fg"],
        buttonbackground=COLORS["surface"], insertbackground=COLORS["fg"], relief=tk.FLAT,
        font=("Segoe UI", 9)
    )
    spinbox.pack(fill=tk.X, padx=12, pady=(0, 8))

    progress = ttk.Progressbar(modal, mode="determinate", style="Dark.Horizontal.TScale")
    progress.pack(fill=tk.X, padx=12, pady=(0, 4))

    status_lbl = tk.Label(
        modal, text="Listo", bg=COLORS["bg"], fg=COLORS["fg"],
        font=("Segoe UI", 9)
    )
    status_lbl.pack(anchor=tk.W, padx=12, pady=(0, 12))

    def run_batch_extraction(n):
        global total_frames
        ext = config["save_format"]
        save_folder = config["save_folder"]
        os.makedirs(save_folder, exist_ok=True)

        saved = 0
        for i in range(0, total_frames, n):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ret, frame = cap.read()
            if not ret:
                continue
            filename = f"frame_{i:05d}.{ext}"
            full_path = os.path.join(save_folder, filename)
            if ext == "jpg":
                cv2.imwrite(full_path, frame, [cv2.IMWRITE_JPEG_QUALITY, config["jpg_quality"]])
            else:
                cv2.imwrite(full_path, frame)
            saved += 1
            pct = int((i + n) / total_frames * 100)

            def _update(p=pct, s=saved, idx=i):
                progress["value"] = min(p, 100)
                status_lbl.config(text=f"Guardados: {s}  ({idx}/{total_frames - 1})")
                display_frame_at(idx)

            root.after(0, _update)

        def _done():
            progress["value"] = 100
            messagebox.showinfo("Completado", f"Extraccion finalizada.\n{saved} frames guardados en:\n{save_folder}")
            modal.destroy()

        root.after(0, _done)

    def start_batch():
        if cap is None:
            return
        n = n_var.get()
        if n < 1:
            return
        spinbox.config(state=tk.DISABLED)
        start_btn.config(state=tk.DISABLED)
        cancel_btn.config(state=tk.DISABLED)
        progress["value"] = 0
        threading.Thread(target=run_batch_extraction, args=(n,), daemon=True).start()

    def cancel_batch():
        modal.destroy()

    btn_frame = tk.Frame(modal, bg=COLORS["bg"])
    btn_frame.pack(fill=tk.X, padx=12, pady=(0, 12))

    cancel_btn = tk.Button(
        btn_frame, text="Cancelar", bg=COLORS["surface"], fg=COLORS["fg"],
        activebackground=COLORS["surface_hover"], activeforeground=COLORS["accent"],
        relief=tk.FLAT, command=cancel_batch, font=("Segoe UI", 9), padx=16, pady=4
    )
    cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))

    start_btn = tk.Button(
        btn_frame, text="Iniciar", bg=COLORS["accent"], fg=COLORS["bg"],
        activebackground=COLORS["surface_hover"], relief=tk.FLAT,
        command=start_batch, font=("Segoe UI", 9, "bold"), padx=16, pady=4
    )
    start_btn.pack(side=tk.RIGHT)

open_btn = ttk.Button(top_bar, text=" Abrir Video", image=load_gui_icon("open"), compound="left", style="Accent.TButton", command=open_video)
open_btn.pack(side=tk.LEFT)

settings_btn = ttk.Button(top_bar, image=load_gui_icon("settings"), style="Dark.TButton", command=open_settings)
settings_btn.pack(side=tk.LEFT, padx=(4, 0))

recent_btn = ttk.Button(top_bar, image=load_gui_icon("recent"), style="Dark.TButton")
recent_btn.pack(side=tk.LEFT, padx=(4, 0))
recent_btn.bind('<Button-1>', show_recent_menu)

batch_btn = ttk.Button(top_bar, image=load_gui_icon("batch"), style="Dark.TButton", state=tk.DISABLED, command=open_batch_dialog)
batch_btn.pack(side=tk.LEFT, padx=(4, 0))

info_frame = ttk.Frame(top_bar, style="Dark.TFrame")
info_frame.pack(side=tk.RIGHT)

file_label = ttk.Label(info_frame, text="Archivo: —", style="Info.TLabel")
file_label.pack(side=tk.RIGHT, padx=(12, 0))

res_label = ttk.Label(info_frame, text="Res.: —", style="Dark.TLabel")
res_label.pack(side=tk.RIGHT, padx=(12, 0))

fps_label = ttk.Label(info_frame, text="FPS: —", style="Dark.TLabel")
fps_label.pack(side=tk.RIGHT, padx=(12, 0))

frame_label = ttk.Label(info_frame, text="Frame: —", style="Dark.TLabel")
frame_label.pack(side=tk.RIGHT, padx=(12, 0))

time_label = ttk.Label(info_frame, text="00:00:00 / 00:00:00", style="Dark.TLabel")
time_label.pack(side=tk.RIGHT, padx=(12, 0))

# ── CENTER: Canvas Preview ────────────────────────────────────────
canvas = tk.Canvas(root, bg=COLORS["canvas_bg"], highlightthickness=0)
canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(4, 0))
canvas.bind("<Configure>", lambda e: show_on_canvas(current_frame) if current_frame is not None else None)

if HAS_DND:
    canvas.drop_target_register(DND_FILES)
    canvas.bind("<<Drop>>", on_drop)
    canvas.bind("<<DragEnter>>", _on_drag_enter)
    canvas.bind("<<DragLeave>>", _on_drag_leave)

# ── SLIDER ────────────────────────────────────────────────────────
slider = ttk.Scale(
    root,
    from_=0,
    to=100,
    orient=tk.HORIZONTAL,
    style="Dark.Horizontal.TScale",
    command=on_slider_change,
)
slider.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(4, 2))

# ── BOOKMARKS CANVAS ─────────────────────────────────────────────
bookmarks_canvas = tk.Canvas(root, bg=COLORS['bg'], highlightthickness=0, height=12)
bookmarks_canvas.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 2))
bookmarks_canvas.bind('<Configure>', lambda e: draw_bookmarks())

# ── FILMSTRIP ─────────────────────────────────────────────────────
filmstrip_frame = tk.Frame(root, bg=COLORS["canvas_bg"], height=55)
filmstrip_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(0, 4))
filmstrip_frame.pack_propagate(False)

filmstrip_inner = tk.Frame(filmstrip_frame, bg=COLORS["canvas_bg"])
filmstrip_inner.pack(side=tk.TOP, anchor=tk.CENTER, fill=tk.Y, expand=True)

def hex_to_rgb(h):
    return tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(r, g, b):
    return f'#{int(r):02x}{int(g):02x}{int(b):02x}'

def animate_color(widget, prop, from_color, to_color, duration_ms, steps=5):
    c1 = hex_to_rgb(from_color)
    c2 = hex_to_rgb(to_color)
    delay = duration_ms // steps
    
    def step_anim(step):
        if not widget.winfo_exists(): return
        r = c1[0] + (c2[0] - c1[0]) * step / steps
        g = c1[1] + (c2[1] - c1[1]) * step / steps
        b = c1[2] + (c2[2] - c1[2]) * step / steps
        color = rgb_to_hex(r, g, b)
        if prop == "bg":
            try:
                widget.config(bg=color, activebackground=color)
            except tk.TclError:
                pass
        
        if step < steps:
            root.after(delay, lambda: step_anim(step + 1))
            
    step_anim(1)

def on_enter_btn(e):
    if e.widget['state'] != tk.DISABLED:
        animate_color(e.widget, "bg", COLORS["surface"], COLORS["surface_hover"], 150)
def on_leave_btn(e):
    if e.widget['state'] != tk.DISABLED:
        animate_color(e.widget, "bg", e.widget.cget('bg'), COLORS["surface"], 150)

# ── BOTTOM BAR ────────────────────────────────────────────────────
bottom_bar = tk.Frame(root, bg=COLORS["surface"])
bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)

controls_frame = tk.Frame(bottom_bar, bg=COLORS["surface"])
controls_frame.pack(side=tk.LEFT, padx=8, pady=6)

def create_playback_btn(parent, icon_name, command):
    img = load_gui_icon(icon_name)
    btn = tk.Button(parent, image=img, bg=COLORS["surface"], fg=COLORS["fg"],
                    activebackground=COLORS["surface_hover"], activeforeground=COLORS["accent"],
                    relief=tk.FLAT, bd=0, padx=6, pady=4,
                    command=command, state=tk.DISABLED)
    btn.pack(side=tk.LEFT, padx=1)
    btn.bind("<Enter>", on_enter_btn)
    btn.bind("<Leave>", on_leave_btn)
    return btn

btn_first = create_playback_btn(controls_frame, "first", go_first)
btn_prev = create_playback_btn(controls_frame, "prev", prev_frame)
btn_play = create_playback_btn(controls_frame, "play", play_pause)
btn_next = create_playback_btn(controls_frame, "next", next_frame)
btn_last = create_playback_btn(controls_frame, "last", go_last)

bookmark_btn = ttk.Button(bottom_bar, text=" (0)", image=load_gui_icon("bookmark"), compound="left", style="Dark.TButton", command=toggle_bookmark, state=tk.DISABLED)
bookmark_btn.pack(side=tk.RIGHT, padx=2, pady=6)

export_bookmarks_btn = ttk.Button(bottom_bar, image=load_gui_icon("export"), style="Dark.TButton", command=export_bookmarks, state=tk.DISABLED)
export_bookmarks_btn.pack(side=tk.RIGHT, padx=2, pady=6)

open_folder_btn = ttk.Button(bottom_bar, text=" Abrir Carpeta", image=load_gui_icon("folder"), compound="left", style="Dark.TButton", command=open_save_folder, state=tk.DISABLED)
open_folder_btn.pack(side=tk.RIGHT, padx=8, pady=6)

save_btn = ttk.Button(bottom_bar, text=" Guardar Frame", image=load_gui_icon("save_btn"), compound="left", style="Accent.TButton", command=save_frame, state=tk.DISABLED)
save_btn.pack(side=tk.RIGHT, pady=6)

# ── STATUS BAR ────────────────────────────────────────────────────
status_bar = tk.Frame(root, bg=COLORS["status_bg"])
status_bar.pack(side=tk.BOTTOM, fill=tk.X)
status_label = tk.Label(status_bar, text="Listo", bg=COLORS["status_bg"], fg=COLORS["fg"], font=("Segoe UI", 9))
status_label.pack(side=tk.LEFT, padx=8, pady=4)

# ── KEYBOARD SHORTCUTS ───────────────────────────────────────────
root.bind("<space>", lambda e: play_pause())
root.bind("<Left>", lambda e: prev_frame())
root.bind("<Right>", lambda e: next_frame())
root.bind("<Shift-Left>", lambda e: skip_back())
root.bind("<Shift-Right>", lambda e: skip_forward())
root.bind("<Control-s>", lambda e: save_frame())
root.bind("<Control-o>", lambda e: open_video())
root.bind("<m>", lambda e: toggle_bookmark())
root.bind("<Control-e>", lambda e: open_save_folder())
root.bind("<Home>", lambda e: go_first())
root.bind("<End>", lambda e: go_last())
root.bind("<m>", lambda e: toggle_bookmark())

# ── WM_DELETE_WINDOW ─────────────────────────────────────────────
def on_close():
    global cap
    preloader_stop_event.set()
    if cap is not None:
        cap.release()
    save_config()
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

update_recent_menu()
threading.Thread(target=preloader_worker, daemon=True).start()
root.mainloop()
