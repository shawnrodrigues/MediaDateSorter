# Media Date Sorter

A small Windows-friendly desktop application that copies photos and videos into year/month folders.

## Folder layout

```text
Sorted Media/
├── 2024/
│   ├── 01/
│   ├── 02/
│   └── ...
├── 2026/
│   ├── 01/
│   ├── 02/
│   └── ...
└── Not Sorted/
```

## Date detection order

1. Date found in the filename (preferred, as requested).
2. Embedded media metadata via ExifTool, if installed.
3. Photo EXIF metadata via Pillow for supported image formats.
4. If no reliable date is found, copy to `Not Sorted`.

The application deliberately does **not** use the file's downloaded/modified date as a fallback, because that date may be misleading.

## Run on Windows

1. Install Python 3.10+ from https://www.python.org/downloads/ and enable **Add Python to PATH** during setup.
2. Extract this ZIP to a folder.
3. Double-click `run_windows.bat`.

Pillow is optional. The app runs without it, but installing it improves EXIF date reading:
```bat
py -m pip install Pillow
```

For broader photo/video metadata support, install ExifTool from https://exiftool.org/ and make sure `exiftool.exe` is available on PATH. The app automatically uses it when present.

## Use

1. Choose the source folder containing your downloaded photos/videos.
2. Choose a different destination folder (for example, a new empty folder on your M.2 drive). The app creates the year/month folders directly inside this selected folder.
3. Keep **Include subfolders** checked if media may be inside subfolders.
4. Click **Preview scan** first to review the detected dates and destinations.
5. Click **Copy and sort files** to create the copies.

The selected destination folder is used as the output root; the app creates `YYYY/MM` and `Not Sorted` folders inside it. Originals are never moved or deleted. If a filename already exists in the destination, the app adds ` (1)`, ` (2)`, etc. Supported file types are listed in `media_date_sorter.py`.

## Important date-format note

Filename parsing handles common formats such as `IMG-20261014-WA0001`, `VID_20261014_...`, `2026-10-14`, `2026_10_14`, `20261014`, and `14-10-2026`. If a file has no recognizable filename date and lacks readable metadata, it goes to `Not Sorted` rather than guessing.
