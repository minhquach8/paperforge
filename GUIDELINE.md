# Paperforge — User Guide (Student & Supervisor)
---

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
  - [Good practice \& tips](#good-practice--tips)

---

## System requirements

* **Windows 10 / 11 (64-bit)**.
* A user-writable folder (e.g. `C:\Users\<you>\Paperforge\`).
* For LaTeX diff (optional): **TeX Live** or **MiKTeX** with `latexdiff` in `PATH`.
* A working **OneDrive** connection for student ↔ supervisor exchange.

---

## Installation (portable builds)

1. Download the latest portable zip(s):

   * `Paperforge-Student-Portable-win64.zip`
   * `Paperforge-Supervisor-Portable-win64.zip`
2. **Extract** each zip to a folder you control, e.g.:

   ```
   C:\Users\<you>\Paperforge\Student\
   C:\Users\<you>\Paperforge\Supervisor\
   ```
3. Run the app:

   * `Paperforge-Student.exe` or `Paperforge-Supervisor.exe`.
4. No system-wide installation is performed. The app runs **in-place** from the folder you extracted.

> **Note:** When **updating**, the app replaces itself **in the same folder**; it does *not* relocate into AppData. See [Updates & security](#updates--security).

---

## Common concepts

### Folder layout on disk

Paperforge uses a simple folder structure on your shared **Students’ Root** (typically a OneDrive folder):

```
Students’ Root/
  <Student Name>/
    <manuscript-slug>/
      submissions/
        <YYYYMMDDHHMMSS>/
          payload/                # files submitted by Student
          manifest.json
      reviews/
        <submission-id>/
          working.docx            # supervisor working copy (Word)
          compiled.pdf            # compiled TeX (if built)
          compiled_diff.pdf       # TeX latexdiff PDF (if available)
          returned.docx           # returned Word file
          returned.html           # returned LaTeX review bundle
          comments.json           # structured comments
      events/
        ...                       # submitted_at / returned_at timestamps
```

### Submissions, reviews, and events

* **Submission**: a timestamped snapshot of the Student’s work copied to `submissions/<id>/payload/`.
* **Review**: all Supervisor output for that submission, under `reviews/<id>/` (working copy, compiled PDFs, comments).
* **Events**: lightweight markers for “submitted” and “returned” used for status and timelines.

### Updates & security

* Both apps can **check for updates**:

  * A **silent** check is performed once shortly after you open the app.
  * A **manual** check is available via **“Check for updates”**.
* If you select **Yes** to update, the app:

  1. Downloads the new build from the official GitHub Releases.
  2. **Verifies a digital signature** (minisign) against a public key embedded in the app.
  3. If valid, the update is **staged** and the app asks to restart; the executable is replaced **in place** (no move to AppData).
  4. If invalid or untrusted, the update is **rejected** and nothing changes.

> If you select **No** when prompted, **nothing is downloaded** and the app continues as is.

### OneDrive behaviour & performance

Paperforge deliberately uses your existing **OneDrive** for file exchange. This gives you version history, access control, and backups — but it also means:

* **Delivery speed depends on OneDrive.** After the Student submits, OneDrive must **upload**; the Supervisor sees it **after download** completes; the same applies in reverse for returns.
* You may see a **delay** (usually seconds to a few minutes) depending on network conditions and OneDrive’s sync schedule.

**Recommendations:**

* Ensure OneDrive is **signed in** and syncing: check the tray icon.
* Prefer **shorter paths** (avoid very deep directory hierarchies).
* Use “**Always keep on this device**” for your Students’ Root to reduce “cloud placeholder” delays.
* If in doubt, right-click the OneDrive icon → **Sync** or **Pause/Resume** to nudge it.

---

## Paperforge — Student

### First run (Student)

1. Launch `Paperforge-Student.exe`.
2. Either:

   * **New** → create a manuscript folder (the app initialises an internal repository and writes a minimal `paper.yaml`), or
   * **Open** → select an existing manuscript folder (the app offers to initialise a repository if missing).
3. **Set/Change Students’ Root…**: point the app to your **class OneDrive root** supplied by your supervisor. Provide:

   * **Student name** as shown to Supervisor,
   * **Manuscript slug** (auto-suggested from folder name; lowercase, no spaces).

### Daily workflow (Student)

1. **Work normally** in your manuscript folder.
2. **Commit** (Ctrl+S) when you want to checkpoint your state (write a short message).
3. **Submit** (Ctrl+Enter) when ready for review:

   * The app creates `submissions/<timestamp>/payload/…` under your mapped Students’ Root.
   * It writes `manifest.json` and a submission event.
   * OneDrive syncs the new files.
4. Await the supervisor’s **return**; watch the **Inbox** panel (refresh with **F5**).

### Inbox & reviews

* Each returned review appears in the **Inbox** with the submission id and status.
* Actions:

  * **Open selected review**: opens `returned.docx` (Word) or `returned.html` (LaTeX).
  * **Save a copy to working folder**: copies the returned file (and `comments.json` if present) into:

    ```
    <your manuscript>\received_reviews\<submission-id>\
    ```

    You’ll be offered to create a **checkpoint commit** for traceability.
* **Comments preview** (right-hand side) shows `comments.json` in a readable text form.

### Keyboard shortcuts (Student)

* **New**: Ctrl+N
* **Open**: Ctrl+O
* **Commit**: Ctrl+S
* **Submit**: Ctrl+Enter
* **Refresh history**: Shift+F5
* **Refresh inbox**: F5
* **Restore…**: Ctrl+R

### Troubleshooting (Student)

* **I don’t see my supervisor’s return in Inbox.**
  Check your mapping (Students’ Root / name / slug), click **Refresh inbox**, and confirm OneDrive has finished syncing on both sides.
* **Restore failed or files locked.**
  Close apps that may be holding files open (Word, PDF viewers, editors), then retry **Restore**.
* **Update prompt keeps appearing or seems slow.**
  Choose **No** to skip. If you choose **Yes**, the app verifies and stages the update; once it asks to restart and closes, simply open the app again. If it reports “signature invalid”, the download is discarded.
* **LaTeX in Inbox shows only `returned.html`.**
  That’s expected for LaTeX: the Supervisor may return an HTML page that links an embedded or adjacent PDF (compiled or diffed).

---

## Paperforge — Supervisor

### First run (Supervisor)

1. Launch `Paperforge-Supervisor.exe`.
2. **Choose Students’ Root…** and select the shared OneDrive root.
3. Press **Scan** to populate the tree. You can filter by **Status** (New/In review/Returned), **Type** (Word/LaTeX), or **Search** by Student/Title/Journal/Submission ID.
4. Enable **Auto-rescan** (every 90s) if you want the list to refresh automatically.

### Reviewing Word submissions

1. Double-click a **Word** submission.
2. The app copies the submitted `.docx`/`.doc` to `reviews/<id>/working.docx` (or `.doc`) and **opens it** with the system default (usually MS Word).
3. Save changes in Word as usual. When ready, use **Return selected**:

   * The app copies `working.docx` → `returned.docx`.
   * If no `comments.json` exists, it writes a small default one.
   * A **returned event** is recorded.

### Reviewing LaTeX submissions

1. Double-click a **LaTeX** submission to open the **LaTeX Review Workspace**.
2. **File list** (left), **editor** (centre), **comments** (right):

   * **Save file** to persist edits in the workspace.
   * **Build PDF** compiles with Tectonic (bundled) and shows the log.
   * **Add comment from selection** sets the line range automatically from your selection (no selection = current line).
   * **Save comments** writes `comments.json`.
3. When returning:

   * If `latexdiff` is available in `PATH`, the app generates a highlighted diff and builds `compiled_diff.pdf`.
   * Otherwise, it builds a normal PDF.
   * It then creates a friendly `returned.html` that links the PDF and lists your comments.

### Returning work

* Select one or more submissions → **Return selected**.
* The app writes the appropriate outputs under `reviews/<id>/…` and records a returned event.
* OneDrive syncs the results back to the Student.

### Troubleshooting (Supervisor)

* **PDF build fails (LaTeX).**
  Check the **build log** in the workspace. Ensure the correct main `.tex` is open/saved; missing packages will be reported. If necessary, open the log in a separate editor for searching.
* **No diff produced.**
  Install TeX Live or MiKTeX and ensure `latexdiff` is in `PATH`. Without it, the app still returns a standard compiled PDF.
* **Update dialog blocks the app.**
  Use the **manual** “Check for updates” button rather than waiting for the silent check. If you choose **Yes**, let it finish staging; the app will close and be ready to relaunch. If you prefer to postpone, choose **No**.

---

## Frequently asked questions

### When I restore, where do “deleted” files go?

It depends on the restore mode you choose:

* **Clean restore**: the app **removes files that are not part of the restored snapshot** from your working folder (e.g. temporary or newly added files outside the repository history).

  * These files are deleted from disk by the operating system. Paperforge does **not** maintain its own recycle bin.
  * If you rely on **OneDrive Version History**, **Windows File History**, or backups, you may still be able to recover earlier versions.

* **Overlay restore**: the app **overwrites tracked files** with the contents from the chosen commit and **keeps untracked files** in place. Nothing is purposely deleted.

**Recommendation:** if you’re unsure, choose **Overlay**. Use **Clean** only when you know you want a pristine copy of exactly what was tracked in that commit.

### My submission/return is not showing up. Why?

Because the exchange runs over **OneDrive**, there’s an inherent sync delay:

* Student → OneDrive **upload** → Supervisor **download**
* Supervisor return → OneDrive **upload** → Student **download**
  Check that both ends are signed in to OneDrive and that the tray icon shows a completed sync. You can also trigger a manual **Sync** from the OneDrive menu.

### Will the app move itself into AppData when updating?

No. Updates are **in-place**: the executable in your chosen folder is replaced with the new signed build. The app does **not** relocate itself to AppData.

### What happens if an update is tampered with?

Every official release is **digitally signed**. The app verifies the signature against a **public key embedded in the application**. If the signature is invalid, the update is **discarded** and the current version continues to run.

### Can I use the apps without Internet?

You can work locally (editing, committing, restoring) without Internet. Submissions/returns require **OneDrive sync**, so sharing will pause until you’re back online.

### Where are my preferences stored?

Per-user application settings (window geometry, recent folders, etc.) are stored using the operating system’s standard user settings mechanism (on Windows, via the registry under your user profile).

---

## Good practice & tips

* **Keep path lengths modest.** Deeply nested directories can cause issues with Windows path limits and slow down sync.
* **Name consistently.** Use clear student names and slugs (lowercase; hyphens instead of spaces).
* **Commit often.** Small, meaningful checkpoints make **Restore** safer and more predictable.
* **Use Auto-rescan** during marking sessions (Supervisor) to reduce manual refreshes.
* **For LaTeX reviewers:** save before build, and consider installing `latexdiff` for richer feedback.
* **For Students:** when pulling a returned review, accept the prompt to create a commit to anchor that feedback in your history.