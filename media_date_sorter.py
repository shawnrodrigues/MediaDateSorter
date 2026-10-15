import os
import re
import shutil
import subprocess
import threading
import queue
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Media Date Sorter"
MEDIA_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".heic", ".heif", ".dng", ".raw", ".cr2", ".nef", ".arw", ".orf",
    ".rw2", ".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".3gp",
    ".mts", ".m2ts", ".mpg", ".mpeg", ".webm", ".vob"
}

# Date patterns are intentionally checked in the filename before metadata.
DATE_PATTERNS = [
    # YYYY-MM-DD, YYYY_MM_DD, YYYY.MM.DD
    re.compile(r"(?<!\d)(20\d{2})[-_. ](0?[1-9]|1[0-2])[-_. ](0?[1-9]|[12]\d|3[01])(?!\d)"),
    # YYYYMMDD
    re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)"),
    # Common phone exports: IMG-20261014-WA0001, VID_20261014_...
    re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?=\\D|$)"),
    # DD-MM-YYYY or DD_MM_YYYY (only when year is explicit)
    re.compile(r"(?<!\d)(0?[1-9]|[12]\d|3[01])[-_. ](0?[1-9]|1[0-2])[-_. ](20\d{2})(?!\d)"),
]

def valid_date(y, m, d):
    try:
        return datetime(int(y), int(m), int(d)).date()
    except (ValueError, TypeError):
        return None

def date_from_filename(filename):
    stem = Path(filename).stem
    # First try year-first patterns.
    for pattern in DATE_PATTERNS[:3]:
        match = pattern.search(stem)
        if match:
            groups = match.groups()
            result = valid_date(*groups[:3])
            if result:
                return result, "filename"
    # Then day-first date pattern.
    match = DATE_PATTERNS[3].search(stem)
    if match:
        d, m, y = match.groups()
        result = valid_date(y, m, d)
        if result:
            return result, "filename"
    return None, None

def exiftool_date(path):
    """Use ExifTool when installed; it can read many image and video formats."""
    executable = shutil.which("exiftool")
    if not executable:
        return None
    tags = [
        "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate",
        "-TrackCreateDate", "-CreationDate", "-FileCreateDate"
    ]
    try:
        result = subprocess.run(
            [executable, "-s3", *tags, str(path)],
            capture_output=True, text=True, timeout=15, check=False
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            # Typical ExifTool formats: 2026:10:14 13:24:00 or ISO-like dates.
            match = re.search(r"(20\d{2})[:\-](\d{2})[:\-](\d{2})", line)
            if match:
                parsed = valid_date(*match.groups())
                if parsed:
                    return parsed
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None

def pillow_exif_date(path):
    try:
        from PIL import Image
        with Image.open(path) as image:
            exif = image.getexif()
            # EXIF DateTimeOriginal (36867), DateTimeDigitized (36868), DateTime (306)
            for tag in (36867, 36868, 306):
                value = exif.get(tag)
                if value:
                    match = re.search(r"(20\d{2})[:\-](\d{2})[:\-](\d{2})", str(value))
                    if match:
                        parsed = valid_date(*match.groups())
                        if parsed:
                            return parsed
    except Exception:
        pass
    return None

def media_date(path):
    found, source = date_from_filename(path.name)
    if found:
        return found, source
    found = exiftool_date(path)
    if found:
        return found, "metadata (ExifTool)"
    if path.suffix.lower() in {".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".heic", ".heif"}:
        found = pillow_exif_date(path)
        if found:
            return found, "photo EXIF"
    return None, None

def unique_destination(path):
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1

class MediaDateSorter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("850x650")
        self.minsize(740, 560)
        self.events = queue.Queue()
        self.running = False
        self._build_ui()
        self.after(100, self._poll_events)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Media Date Sorter", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Copies photos and videos into folders created inside your selected destination: YYYY / MM. Filename dates are preferred; metadata is a fallback.",
            wraplength=800
        ).pack(anchor="w", pady=(4, 14))

        paths = ttk.LabelFrame(outer, text="Folders", padding=12)
        paths.pack(fill="x")
        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self._path_row(paths, 0, "Source folder", self.source_var, self.pick_source)
        self._path_row(paths, 1, "Destination folder", self.dest_var, self.pick_dest)

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=10)
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="Include subfolders", variable=self.recursive_var).pack(side="left")
        ttk.Label(options, text="Unrecognized dates → Not Sorted").pack(side="right")

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 10))
        self.preview_btn = ttk.Button(actions, text="Preview scan", command=self.preview)
        self.preview_btn.pack(side="left")
        self.run_btn = ttk.Button(actions, text="Copy and sort files", command=self.start_sort)
        self.run_btn.pack(side="left", padx=(8, 0))
        self.clear_btn = ttk.Button(actions, text="Clear log", command=self.clear_log)
        self.clear_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 8))
        self.status_var = tk.StringVar(value="Choose a source folder and a destination folder to begin.")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(0, 8))

        log_frame = ttk.LabelFrame(outer, text="Activity log", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, wrap="word", height=18, state="disabled", font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(
            outer,
            text="Safety: originals are never moved or deleted. Existing destination filenames are preserved; duplicates get a numbered suffix.",
            wraplength=800
        ).pack(anchor="w", pady=(10, 0))

    def _path_row(self, parent, row, label, variable, command):
        ttk.Label(parent, text=label, width=17).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=5)
        ttk.Button(parent, text="Browse…", command=command).grid(row=row, column=2, pady=5)
        parent.columnconfigure(1, weight=1)

    def pick_source(self):
        chosen = filedialog.askdirectory(title="Choose folder containing photos and videos")
        if chosen:
            self.source_var.set(chosen)

    def pick_dest(self):
        chosen = filedialog.askdirectory(title="Choose destination for sorted copies")
        if chosen:
            self.dest_var.set(chosen)

    def get_files(self):
        source = Path(self.source_var.get()).expanduser()
        dest_text = self.dest_var.get().strip()
        if not source.is_dir():
            raise ValueError("Please choose a valid source folder.")
        if not dest_text:
            raise ValueError("Please choose a destination folder.")
        dest = Path(dest_text).expanduser()
        source_resolved = source.resolve()
        dest_resolved = dest.resolve()
        if source_resolved == dest_resolved:
            raise ValueError("Source and destination folders must be different.")

        # Create the selected destination folder if it does not exist.
        # All generated YYYY/MM and Not Sorted folders are created underneath it.
        dest.mkdir(parents=True, exist_ok=True)
        dest_resolved = dest.resolve()

        iterator = source.rglob("*") if self.recursive_var.get() else source.iterdir()
        files = []
        for p in iterator:
            if not p.is_file() or p.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            try:
                p_resolved = p.resolve()
                # If destination is nested inside source, do not scan copies from
                # the destination on future runs.
                if p_resolved == dest_resolved or dest_resolved in p_resolved.parents:
                    continue
                # If source is nested inside destination, avoid treating unrelated
                # destination files as source inputs.
                if source_resolved not in p_resolved.parents:
                    continue
            except OSError:
                pass
            files.append(p)
        return source, dest, files

    def preview(self):
        try:
            source, dest, files = self.get_files()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        dated = 0
        unsorted = 0
        self.write_log(f"Preview: found {len(files)} supported media files.")
        for p in files[:5000]:
            dt, method = media_date(p)
            if dt:
                dated += 1
                target = dest / f"{dt.year:04d}" / f"{dt.month:02d}" / p.name
                self.write_log(f"[{method}] {p.name}  →  {dt.year:04d}/{dt.month:02d}/")
            else:
                unsorted += 1
                self.write_log(f"[no date] {p.name}  →  Not Sorted/")
        if len(files) > 5000:
            self.write_log("Preview limited to first 5,000 files.")
        self.status_var.set(f"Preview complete — {len(files)} files, {dated} dated, {unsorted} Not Sorted.")
        if not files:
            self.write_log("No supported photos/videos found. Check the source folder and file types.")

    def start_sort(self):
        if self.running:
            return
        try:
            source, dest, files = self.get_files()
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        if not files:
            messagebox.showinfo(APP_NAME, "No supported photos or videos were found in the source folder.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Copy {len(files)} media files into:\n{dest}\n\nOriginal files will not be changed or deleted. Continue?"
        ):
            return
        self.running = True
        self.run_btn.configure(state="disabled")
        self.preview_btn.configure(state="disabled")
        self.progress.configure(maximum=len(files), value=0)
        threading.Thread(target=self._sort_worker, args=(dest, files), daemon=True).start()

    def _sort_worker(self, dest, files):
        copied = dated_count = unsorted_count = errors = 0
        for index, src in enumerate(files, start=1):
            try:
                dt, method = media_date(src)
                if dt:
                    folder = dest / f"{dt.year:04d}" / f"{dt.month:02d}"
                    dated_count += 1
                    label = f"{dt.year:04d}/{dt.month:02d}"
                else:
                    folder = dest / "Not Sorted"
                    unsorted_count += 1
                    label = "Not Sorted"
                folder.mkdir(parents=True, exist_ok=True)
                target = unique_destination(folder / src.name)
                shutil.copy2(src, target)
                copied += 1
                self.events.put(("log", f"[{index}/{len(files)}] Copied: {src.name} → {label}/"))
            except Exception as exc:
                errors += 1
                self.events.put(("log", f"[ERROR] {src}: {exc}"))
            self.events.put(("progress", index, len(files)))
        self.events.put(("done", copied, dated_count, unsorted_count, errors))

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log":
                    self.write_log(event[1])
                elif event[0] == "progress":
                    self.progress.configure(value=event[1], maximum=event[2])
                    self.status_var.set(f"Processing {event[1]} of {event[2]}…")
                elif event[0] == "done":
                    _, copied, dated, unsorted, errors = event
                    self.running = False
                    self.run_btn.configure(state="normal")
                    self.preview_btn.configure(state="normal")
                    self.status_var.set(
                        f"Finished — {copied} copied; {dated} dated; {unsorted} in Not Sorted; {errors} errors."
                    )
                    self.write_log("\n" + self.status_var.get())
                    messagebox.showinfo(APP_NAME, self.status_var.get())
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

if __name__ == "__main__":
    app = MediaDateSorter()
    app.mainloop()
