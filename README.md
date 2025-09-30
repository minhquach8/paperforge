# Paperforge

Lightweight **Student ↔ Supervisor** workflow for manuscripts on Windows, designed for Word **and** LaTeX.
Two portable desktop apps:

* **Paperforge — Student**: snapshot, submit, track returns.
* **Paperforge — Supervisor**: review, annotate/comment, return.

No server, no database — Paperforge rides on your existing **OneDrive** folder sharing so you keep your own access control, history and backups.

---

## ✨ Highlights

* **Zero install (portable)**: unzip and run.
* **OneDrive-native exchange**: students submit into a shared root; supervisors return in place.
* **Word**: supervisor works in `working.docx` and returns `returned.docx`.
* **LaTeX**: bundled Tectonic build; optional `latexdiff`; returns a PDF (diff if available) and a friendly `returned.html` with comments.
* **Structured comments**: `comments.json` for machine-readability, with a human-readable preview.
* **History & restore**: local mini-repo per manuscript for safe checkpoints and restores.
* **Expected date**: students can set an expected revision date; overdue items are highlighted.
* **In-place updates**: built-in updater downloads from GitHub Releases and **verifies a minisign signature** against an embedded public key.

---

## 📁 How it works (on disk)

The shared **Students’ Root** (a OneDrive folder) contains per-student, per-manuscript subfolders:

```
Students’ Root/
  <Student Name>/
    <manuscript-slug>/
      submissions/
        <YYYYMMDDHHMMSS>/
          payload/                # files submitted by the Student
          manifest.json
      reviews/
        <submission-id>/
          working.docx            # Supervisor’s working copy (Word)
          compiled.pdf            # built TeX (if available)
          compiled_diff.pdf       # latexdiff PDF (if available)
          returned.docx           # returned Word file (Word workflow)
          returned.html           # returned LaTeX bundle
          comments.json           # structured comments
      events/                     # submitted_at / returned_at timestamps
```

> **Important (OneDrive):** on both machines, right-click the Students’ Root and choose **Always keep on this device** to avoid cloud-only placeholders that can cause “Access is denied” when returning.

---

## 🧰 System requirements

* **Windows 10 / 11 (64-bit)**
* **OneDrive** signed in and syncing
* To open Word returns: **Microsoft Word** (recommended) or LibreOffice
* *(Optional for LaTeX diff)* **TeX Live** or **MiKTeX** with `latexdiff` in `PATH`

---

## ⬇️ Download (portable builds)

Grab the latest zips from the repository **Releases** page:

* `Paperforge-Student-Portable-win64.zip`
* `Paperforge-Supervisor-Portable-win64.zip`

Extract each zip to a folder you control (e.g. `C:\Users\<you>\Paperforge\Student\`) and run the corresponding `.exe`.
No installer; the apps run **in place**.

---

## 🚀 Quick start

### Student

1. Run **Paperforge-Student**.
2. **New** or **Open** your manuscript folder.
3. **Set/Change Students’ Root…** and provide your **Student name** and **manuscript slug**.
4. Work as usual; **Commit** to checkpoint; **Submit** when ready.
5. Optionally set an **Expected date** for your revision.
6. Watch **Inbox** for returns; **Open** a review:

   * Word returns open `returned.docx` in Word.
   * LaTeX returns open a PDF (prefers `*_diff*.pdf`) or `returned.html`.
7. **Save a copy** to `received_reviews/<submission-id>/`:

   * Word → copy `returned.docx` + `comments.json` (if any).
   * LaTeX with PDF → copy the primary PDF + `comments.json`.
   * HTML-only → copy the **entire review folder** for offline viewing.

### Supervisor

1. Run **Paperforge-Supervisor**.
2. **Choose Students’ Root…** (shared OneDrive root), then **Scan**.
3. Double-click:

   * **Word**: opens a working copy `working.docx` in Word; **Return selected** creates `returned.docx`.
   * **LaTeX**: opens the workspace (editor, build, comments). Build PDF; optional `latexdiff`; **Return selected** writes PDF(s) and `returned.html`.

---

## 🔄 Updates & security

* Choose **Check for updates…** in either app.
* The updater downloads from GitHub Releases and **verifies a minisign signature** using a **public key embedded in the app**.
* If valid, the app stages an **in-place** replacement and asks to restart.
* If invalid/untrusted, the update is discarded; nothing changes.

---

## 🧪 Developing from source

```bash
# 1) Clone
git clone <this-repo>
cd paperforge

# 2) Python (3.12+ recommended) & deps
python -m venv .venv
. .venv/Scripts/activate   # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3) Run apps
python apps/student_app/main.py
python apps/supervisor_app/main.py

# 4) Tests
pytest -q
```

### Packaging (Windows portable)

PyInstaller specs are provided:

* `packaging/win_student.spec`
* `packaging/win_supervisor.spec`

Typical flow:

```bash
pyinstaller packaging/win_student.spec
pyinstaller packaging/win_supervisor.spec
# Zip dist/ folders as:
#   Paperforge-Student-Portable-win64.zip
#   Paperforge-Supervisor-Portable-win64.zip
# Sign each zip with minisign and attach zips + .minisig to the GitHub release.
```

The Windows bundles include:

* **Tectonic** (portable TeX engine)
* **minisign.exe** (used for update verification)

---

## 🧩 Known behaviours / tips

* **Word vs LaTeX opening** (Student → Inbox → Open):
  opens **`returned.docx`/`.doc`** for Word submissions; for LaTeX, opens a **PDF** if present (prefers diff), otherwise **`returned.html`** in your browser.
* **HTML returns offline**: use **Save a copy** so the entire folder is copied; open the local `returned.html`.
* **OneDrive sync delay**: allow a short delay for upload/download on both sides; press **Refresh** in the apps.
* **“Access is denied” when returning (Supervisor)**: ensure the Students’ Root is **Always keep on this device** and that Word/PDF viewers are not locking files.

---

## 🤝 Contributing

Issues and pull requests are welcome. Please keep PRs small and focused; add tests where practical (`tests/`).

---

## 📜 Licence

MIT License © 2025 Minh Quach

---

## 🙏 Acknowledgements

* **PySide6** for the UI
* **Tectonic** for LaTeX builds
* **latexdiff** for change highlighting (optional)
* **minisign** for release signing and update verification

---
