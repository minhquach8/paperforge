# Paperforge — User Guide (Student & Supervisor)

## Contents

- [Paperforge — User Guide (Student \& Supervisor)](#paperforge--user-guide-student--supervisor)
  - [Contents](#contents)
  - [System requirements](#system-requirements)
  - [Installation (portable builds)](#installation-portable-builds)
  - [Common concepts](#common-concepts)
    - [Folder layout on disk](#folder-layout-on-disk)
    - [Submissions, reviews, and events](#submissions-reviews-and-events)
    - [Updates \& security](#updates--security)
    - [OneDrive behaviour \& performance](#onedrive-behaviour--performance)
  - [Paperforge — Student](#paperforge--student)
    - [First run (Student)](#first-run-student)
    - [Daily workflow (Student)](#daily-workflow-student)
    - [Inbox \& reviews](#inbox--reviews)
    - [Keyboard shortcuts (Student)](#keyboard-shortcuts-student)
    - [Troubleshooting (Student)](#troubleshooting-student)
  - [Paperforge — Supervisor](#paperforge--supervisor)
    - [First run (Supervisor)](#first-run-supervisor)
    - [Reviewing Word submissions](#reviewing-word-submissions)
    - [Reviewing LaTeX submissions](#reviewing-latex-submissions)
    - [Returning work](#returning-work)
    - [Troubleshooting (Supervisor)](#troubleshooting-supervisor)
  - [Frequently asked questions](#frequently-asked-questions)
    - [When I restore, where do “deleted” files go?](#when-i-restore-where-do-deleted-files-go)
    - [My submission/return is not showing up. Why?](#my-submissionreturn-is-not-showing-up-why)
    - [Will the app move itself into AppData when updating?](#will-the-app-move-itself-into-appdata-when-updating)
    - [What happens if an update is tampered with?](#what-happens-if-an-update-is-tampered-with)
    - [Can I use the apps without Internet?](#can-i-use-the-apps-without-internet)
    - [Where are my preferences stored?](#where-are-my-preferences-stored)
    - [Why do I see “Access is denied” on return?](#why-do-i-see-access-is-denied-on-return)
  - [Good practice \& tips](#good-practice--tips)

---

## System requirements

* **Windows 10 / 11 (64-bit)**.
* A user-writable folder (e.g. `C:\Users\<you>\Paperforge\`).
* A working **OneDrive** connection for Student ↔ Supervisor exchange.
* To open Word documents: **Microsoft Word** (recommended) or **LibreOffice**.
* *(Optional, for nicer LaTeX diffs)* **TeX Live** or **MiKTeX** with `latexdiff` in `PATH`.

---

## Installation (portable builds)

1. Download the latest portable zips:

   * `Paperforge-Student-Portable-win64.zip`
   * `Paperforge-Supervisor-Portable-win64.zip`
2. **Extract** each zip into a folder you control, e.g.

   ```
   C:\Users\<you>\Paperforge\Student\
   C:\Users\<you>\Paperforge\Supervisor\
   ```
3. Run `Paperforge-Student.exe` or `Paperforge-Supervisor.exe`.
4. No system-wide installation is performed; the app runs **in place** from the extracted folder.

> **Note:** During updates, the app replaces itself **in the same folder**; it does **not** move into AppData. See [Updates & security](#updates--security).

---

## Common concepts

### Folder layout on disk

Paperforge uses a simple structure under the shared **Students’ Root** (typically a OneDrive folder):

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
          compiled.pdf            # compiled TeX (if built)
          compiled_diff.pdf       # TeX latexdiff PDF (if available)
          returned.docx           # returned Word file
          returned.html           # returned LaTeX review bundle
          comments.json           # structured comments
      events/
        ...                       # submitted_at / returned_at timestamps
```

### Submissions, reviews, and events

* **Submission** — a timestamped snapshot of the Student’s work, copied to `submissions/<id>/payload/`.
* **Review** — all Supervisor outputs for that submission under `reviews/<id>/`.
* **Events** — lightweight markers for “submitted” and “returned” used for status and timelines.

### Updates & security

* Both apps provide **Check for updates…** (manual).
* If you choose to update, the app:

  1. Downloads the new build from the official GitHub Releases.
  2. **Verifies a digital signature** (minisign) against a **public key embedded in the app**.
  3. If valid, the update is **staged** and the app requests a restart; the executable is replaced **in place**.
  4. If invalid or untrusted, the update is **rejected**; nothing changes.

> If you select **No**, nothing is downloaded and the app continues as is.

### OneDrive behaviour & performance

Because Paperforge rides on your existing **OneDrive**:

* Delivery speed depends on OneDrive: Student **uploads**, Supervisor **downloads**, and vice versa.
* Expect a short **delay** (seconds to a few minutes), depending on network and OneDrive’s schedule.

**Recommendations**

* Ensure OneDrive is **signed in** and syncing (check the tray icon).
* Prefer **shorter paths** (avoid very deep directory hierarchies).
* Right-click the Students’ Root → **Always keep on this device** to avoid “cloud placeholder” issues and speed things up.
* If in doubt, open the OneDrive menu and press **Sync** or **Pause/Resume** to nudge it.

---

## Paperforge — Student

### First run (Student)

1. Launch `Paperforge-Student.exe`.
2. Either:

   * **New** → create a manuscript folder (the app initialises an internal repository and writes a minimal `paper.yaml`), or
   * **Open** → select an existing manuscript folder (the app offers to initialise a repository if missing).
3. **Set/Change Students’ Root…** and provide:

   * **Student name** (as seen by the Supervisor),
   * **Manuscript slug** (auto-suggested from the folder name; lowercase, no spaces).

### Daily workflow (Student)

1. Work normally in your manuscript folder.
2. **Commit** (Ctrl+S) to checkpoint your state (short message encouraged).
3. **Submit** (Ctrl+Enter) when ready:

   * The app creates `submissions/<timestamp>/payload/…` in your mapped Students’ Root,
   * Writes `manifest.json` and a submission event,
   * OneDrive syncs the files.
4. **(Optional)** set your **Expected date** (your anticipated date to send the revision). Overdue expected dates are shown **in red** in the Inbox.
5. Watch the **Inbox** for returns (press **F5** to refresh).

### Inbox & reviews

* Each return appears in the **Inbox** with submission id and status.
* **Open selected review**:

  * If a **`returned.docx`/`.doc`** exists → the app opens it in your system’s default Word processor.
  * For **LaTeX** with a **PDF** → the in-app viewer opens the PDF (prefers `*_diff*.pdf` if available).
  * If only **`returned.html`** exists → your web browser opens it (the dialog still shows comments).
* **Save a copy to working folder** stores the return under:

  ```
  <your manuscript>\received_reviews\<submission-id>\
  ```

  Save rules:

  * **Word return** → copy **`returned.docx`/`.doc`** and `comments.json` (if present).
  * **LaTeX with PDF(s)** → copy the **primary PDF** (diff if present, otherwise compiled) and `comments.json`.
  * **HTML return only** → copy the **entire review folder** so the HTML works **offline** with its assets.
    You’ll be offered to create a **checkpoint commit** for traceability.

### Keyboard shortcuts (Student)

* **New**: Ctrl+N
* **Open**: Ctrl+O
* **Commit**: Ctrl+S
* **Submit**: Ctrl+Enter
* **Refresh history**: Shift+F5
* **Refresh inbox**: F5
* **Restore…**: Ctrl+R

### Troubleshooting (Student)

* **I can’t see my Supervisor’s return in the Inbox.**
  Check your mapping (Students’ Root / name / slug), press **Refresh**, and confirm OneDrive has finished syncing on both sides.
* **Opening the review doesn’t launch Word.**
  Ensure the review folder actually contains `returned.docx`/`.doc`. If it is a LaTeX return, the app will open a PDF or `returned.html` instead.
* **HTML review shows missing assets offline.**
  Use **Save a copy…** (the app copies the **whole review folder**), then open the HTML from your local copy.
* **Restore failed or files are locked.**
  Close Word/PDF viewers/editors that may be holding files open, then retry **Restore**.

---

## Paperforge — Supervisor

### First run (Supervisor)

1. Launch `Paperforge-Supervisor.exe`.
2. **Choose Students’ Root…** → select the shared OneDrive root.
3. Press **Scan** to populate the list; filter by **Status** (New / In review / Returned), **Type** (Word / LaTeX), or **Search** by Student / Title / Journal / Submission ID.
4. Enable **Auto-rescan** (every ~90s) if you want automatic refresh.

> **Important for OneDrive:** For any shared Students’ Root coming from students, right-click the folder and choose **Always keep on this device**. This prevents write failures when OneDrive leaves items as cloud-only placeholders.

### Reviewing Word submissions

1. Double-click a **Word** submission.
2. The app copies the submitted `.docx`/`.doc` to `reviews/<id>/working.docx` (or `.doc`) and **opens it** with your system default (usually Microsoft Word).
3. Edit and save in Word as usual. When ready, use **Return selected**:

   * The app copies `working.docx` → `returned.docx`,
   * Writes a minimal `comments.json` if none exists,
   * Records a **returned event**.

### Reviewing LaTeX submissions

1. Double-click a **LaTeX** submission to open the **LaTeX Review Workspace**.
2. Within the workspace:

   * **Save file** to persist edits,
   * **Build PDF** (bundled Tectonic) and review the build log,
   * **Add comment from selection** (uses your selection to set the line range; no selection → current line),
   * **Save comments** to write `comments.json`.
3. On return:

   * If `latexdiff` is found in `PATH`, the app produces `compiled_diff.pdf`,
   * Otherwise, it builds a standard `compiled.pdf`,
   * It then generates a reader-friendly **`returned.html`** that links the PDF and lists your comments.

### Returning work

* Select one or more submissions → **Return selected**.
* Outputs are written under `reviews/<id>/…` and a returned event is recorded.
* OneDrive syncs the results back to the Student.

### Troubleshooting (Supervisor)

* **LaTeX PDF build fails.**
  Check the workspace’s **build log**. Ensure the correct main `.tex` is open/saved; missing packages will be listed.
* **No diff produced.**
  Install TeX Live or MiKTeX and ensure `latexdiff` is on `PATH`. Without it, the app still returns a standard compiled PDF.
* **“Access is denied” when returning.**
  Set the relevant OneDrive folder to **Always keep on this device**. Also ensure no other app is locking files.

---

## Frequently asked questions

### When I restore, where do “deleted” files go?

* **Clean restore** — removes files **not** in the snapshot from your working folder (the OS deletes them; Paperforge does not maintain its own recycle bin). You may still recover via OneDrive Version History / Windows File History / backups.
* **Overlay restore** — overwrites tracked files from the snapshot and **keeps untracked files**.

**Recommendation:** If unsure, choose **Overlay**. Use **Clean** only when you need a pristine snapshot.

### My submission/return is not showing up. Why?

OneDrive introduces inherent sync delay:

* Student → OneDrive **upload** → Supervisor **download**
* Supervisor → OneDrive **upload** → Student **download**

Ensure both sides are signed in and fully synced; verify your Students’ Root mapping and refresh the list.

### Will the app move itself into AppData when updating?

No. Updates are **in-place**: the executable in your chosen folder is replaced with the new signed build. The app does **not** relocate into AppData.

### What happens if an update is tampered with?

Every official release is **digitally signed**. The app verifies against a **public key embedded in the application**. If the signature is invalid, the download is **discarded** and the current version continues to run.

### Can I use the apps without Internet?

You can work locally (editing, committing, restoring). Submissions/returns require **OneDrive sync**, so sharing pauses until you are back online.

### Where are my preferences stored?

Per-user settings (window geometry, recent folders, etc.) are stored using the OS’s standard mechanism (on Windows, the user registry).

### Why do I see “Access is denied” on return?

This typically occurs when OneDrive has left a cloud-only placeholder. Right-click the relevant Students’ Root (and/or subfolders) → **Always keep on this device**. Also ensure Word/PDF viewers are not holding locks.

---

## Good practice & tips

* **Keep path lengths modest** to avoid Windows path limits and to speed up syncing.
* **Name consistently** (slug in lowercase; use hyphens instead of spaces).
* **Commit little and often** with clear messages.
* **Enable Auto-rescan** during marking sessions (Supervisor).
* **For LaTeX reviewers:** save before building; install `latexdiff` for richer feedback.
* **For Students:** when saving a return locally, accept the prompt to create a checkpoint so feedback is anchored in your history.

---
