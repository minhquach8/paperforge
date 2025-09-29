# We'll generate a detailed British-English PDF user guide for Paperforge Student and Supervisor
# using matplotlib to render text over multiple A4 pages.

import math
import os
import textwrap

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Page and typography settings
PAGE_W_IN = 8.27  # A4 width in inches
PAGE_H_IN = 11.69 # A4 height in inches
MARGIN_IN = 0.75
BODY_FONTSIZE = 11
LINE_SPACING = 1.35  # line-height multiplier
H1_SIZE = 18
H2_SIZE = 14.5
H3_SIZE = 12.5
PARA_SPACING_LINES = 0.6  # extra blank space after paragraph

# Derived metrics
BODY_LINE_IN = (BODY_FONTSIZE / 72.0) * LINE_SPACING # line height in inches
USABLE_H_IN = PAGE_H_IN - 2 * MARGIN_IN
USABLE_W_IN = PAGE_W_IN - 2 * MARGIN_IN
LINES_PER_PAGE = int(USABLE_H_IN / BODY_LINE_IN)

# Approx character width heuristic for wrapping
# Roughly, average character width ~ 0.5 of font size in points when rendered in a sans font.
# Convert to inches: (BODY_FONTSIZE * 0.5) / 72 inches per char
AVG_CHAR_IN = (BODY_FONTSIZE * 0.5) / 72.0
CHARS_PER_LINE = max(60, int(USABLE_W_IN / AVG_CHAR_IN))

def wrap_paragraph(text, width=CHARS_PER_LINE):
    # Preserve bullet markers and numbering for nicer wrapping.
    bullets = ("- ", "* ")
    num_prefix = None
    bullet_prefix = None

    if any(text.startswith(b) for b in bullets):
        for b in bullets:
            if text.startswith(b):
                bullet_prefix = b
                break
        core = text[len(bullet_prefix):].strip()
        wrapped = textwrap.wrap(core, width=width - len(bullet_prefix))
        if not wrapped:
            return [bullet_prefix.strip()]
        out = [bullet_prefix + wrapped[0]]
        out += [(" " * len(bullet_prefix)) + w for w in wrapped[1:]]
        return out
    else:
        # numbered list like "1. " or "10. "
        import re
        m = re.match(r"^(\d+\.)(\s+)(.+)$", text)
        if m:
            num_prefix = m.group(1) + " "
            core = m.group(3)
            wrapped = textwrap.wrap(core, width=width - len(num_prefix))
            out = [num_prefix + wrapped[0]] if wrapped else [num_prefix.strip()]
            out += [(" " * len(num_prefix)) + w for w in wrapped[1:]]
            return out

    return textwrap.wrap(text, width=width) if text.strip() else [""]

# Minimal content builder with heading levels and paragraphs
class Doc:
    def __init__(self):
        self.blocks = []  # list of (type, text)
    def h1(self, t): self.blocks.append(("H1", t))
    def h2(self, t): self.blocks.append(("H2", t))
    def h3(self, t): self.blocks.append(("H3", t))
    def p(self, t=""): self.blocks.append(("P", t))
    def ul(self, items):
        for it in items:
            self.blocks.append(("P", f"- {it}"))
        # extra spacing after list
        self.blocks.append(("P", ""))

doc = Doc()

# Title
doc.h1("Paperforge Desktop Apps — User Guide")
doc.p("This document covers both the Student and Supervisor desktop applications for Paperforge. It explains installation, day-to-day workflows, the update mechanism, security, and frequently asked questions. Where relevant, Windows examples are given, because the reference builds currently target Windows 10/11 64-bit.")

# Overview
doc.h2("1. Overview")
doc.p("Paperforge provides a simple folder-based review workflow between students and supervisors. Submissions are packaged locally and synchronised via OneDrive into a shared “Students’ Root”. The Supervisor reviews Word or LaTeX projects and returns annotated results.")

doc.p("There are two companion applications:")
doc.ul([
    "Paperforge — Student: create/open a manuscript, commit snapshot history, submit to the Students’ Root, and receive returned reviews.",
    "Paperforge — Supervisor: browse the Students’ Root, open submissions (Word or LaTeX), add comments, compile PDFs (LaTeX), and return feedback."
])

# System requirements & installation
doc.h2("2. System requirements & installation")
doc.h3("2.1 Common requirements")
doc.ul([
    "Windows 10 or 11, 64-bit.",
    "A OneDrive account configured and signed in on the PC.",
    "Enough local disk space for manuscripts and PDFs."
])
doc.h3("2.2 Installing the Student app (portable)")
doc.ul([
    "Download the latest “Paperforge-Student-Portable-win64.zip” from the official GitHub Releases.",
    "Extract the ZIP to a location you control (e.g., “C:\\Users\\<you>\\Paperforge\\Student\\”).",
    "Run “Paperforge-Student.exe”. The app runs in place (no traditional installer)."
])
doc.h3("2.3 Installing the Supervisor app (portable)")
doc.ul([
    "Download “Paperforge-Supervisor-Portable-win64.zip” from the official GitHub Releases.",
    "Extract to a folder (e.g., “C:\\Users\\<you>\\Paperforge\\Supervisor\\”).",
    "Run “Paperforge-Supervisor.exe”. The app runs in place (no traditional installer)."
])

# Student app
doc.h2("3. Student app")
doc.h3("3.1 First-run and the toolbar")
doc.p("The top toolbar provides quick actions: New, Open, Commit, Submit, Set/Change Students’ Root…, Refresh history, Refresh inbox, Restore…, and Check for updates. Keyboard shortcuts are Mac-friendly and shown in tooltips (e.g., Ctrl+N for New, Ctrl+O for Open).")
doc.p("The header card shows the Working folder and current Remote mapping. The main area is split into History (top) and Inbox plus Comments preview (bottom).")

doc.h3("3.2 Typical workflow")
doc.p("A. Create a new manuscript")
doc.ul([
    "Click New → choose a parent directory for the manuscript.",
    "Enter a manuscript name (e.g., “Paper 1”) and, optionally, a target journal.",
    "Paperforge initialises a minimal project (with “paper.yaml”) and a internal snapshot history, then makes the first commit."
])
doc.p("B. Open an existing manuscript")
doc.ul([
    "Click Open → select the folder. If no repository is present, choose Initialise to start tracking history."
])
doc.p("C. Map to the Students’ Root (OneDrive)")
doc.ul([
    "Click Set/Change Students’ Root…",
    "Pick the shared OneDrive “Students’ Root” folder provided by your institution.",
    "Enter your display name and a manuscript slug (auto-suggested from the folder name).",
    "From now on, Submit will publish into that location for the Supervisor to pick up."
])
doc.p("D. Commit and Restore")
doc.ul([
    "Use Commit to record a checkpoint with a short message (e.g., “Fix introduction”).",
    "In History, select a commit and click Restore to revert the working copy. Select CLEAN to remove unrelated files first, or OVERLAY to keep them and overwrite tracked files."
])
doc.p("E. Submit for review")
doc.ul([
    "Optionally Commit one last time.",
    "Click Submit. Paperforge packages your working copy (excluding internal folders) into “submissions/<timestamp>/payload”, writes “manifest.json”, and logs a “submitted” event.",
    "Check Inbox later for returned feedback."
])
doc.p("F. Receive feedback")
doc.ul([
    "Inbox shows each returned item. Select and click Open selected review to launch the returned document (Word or HTML).",
    "Click Save a copy to working folder to copy the returned file to “received_reviews/<id>/…”. If a “comments.json” is present, it is copied alongside. You may create a checkpoint to record the receipt."
])

doc.h3("3.3 Updates & trust")
doc.ul([
    "On start, a one-off silent check runs. You can always use Check for updates manually.",
    "Updates are only applied if the downloaded archive passes signature verification against the public key embedded in the app.",
    "If you choose No when prompted, the update is skipped. If you choose Yes and an update is available, it is staged and the app restarts to complete the process.",
    "If the app is already up to date, a clear message is shown."
])

doc.h3("3.4 Troubleshooting (Student)")
doc.ul([
    "Review not appearing in Inbox: verify your mapping; confirm the Supervisor has “Returned” the work; ensure OneDrive has fully synced; click Refresh inbox.",
    "Restore failed: ensure files are not locked by other applications; close Word/IDE windows and try again.",
    "Update reports “signature invalid”: the file is not the official signed build; the app will refuse to update — contact your administrator."
])

# Supervisor app
doc.h2("4. Supervisor app")
doc.h3("4.1 First-run and scanning")
doc.ul([
    "Click Choose Students’ Root… and select the shared OneDrive folder.",
    "Use Scan to refresh. Optionally enable Auto-rescan (every 90 seconds).",
    "Filter by Search, Status (All/New/In review/Returned), and Type (Word/LaTeX)."
])
doc.h3("4.2 Opening submissions")
doc.ul([
    "Double-click a row in the table.",
    "Word: the app copies the submitted file to “reviews/<id>/working.docx” and opens it with your default Word application.",
    "LaTeX: the app opens the LaTeX Review Workspace (see below)."
])
doc.h3("4.3 LaTeX Review Workspace")
doc.ul([
    "Left: file list and filter. Centre: editor with line numbers in the status bar. Right: comments (general and itemised).",
    "Build PDF compiles with Tectonic (bundled) and displays logs below the editor.",
    "Add comment from selection sets the line range automatically from the editor selection; Save comments writes “comments.json”.",
    "Open compiled.pdf opens the most recent compilation in your system viewer.",
    "If “latexdiff” is available on PATH (from TeX Live or MiKTeX), the app can produce a highlighted diff PDF during Return."
])
doc.h3("4.4 Returning feedback")
doc.ul([
    "Select one or more submissions → Return selected.",
    "Word: “working.docx” is copied to “returned.docx”, and comments.json is written (if missing).",
    "LaTeX: the app builds either a standard “compiled.pdf” or a “compiled_diff.pdf” (if latexdiff is available), and writes a human-readable “returned.html” that links to the PDF and lists comments.",
    "A “returned” event is logged so the student can see the timeline."
])
doc.h3("4.5 Updates & trust")
doc.ul([
    "A lightweight silent check runs after the app starts; you can use Check for updates at any time.",
    "Updates are staged only if a signed archive is found. If you choose No when prompted, nothing is downloaded.",
    "When an update is staged, you will be asked to restart the app; otherwise a clear Up-to-date message is shown."
])
doc.h3("4.6 Troubleshooting (Supervisor)")
doc.ul([
    "LaTeX build fails: save the current file and check the build log for missing packages or TeX errors; ensure the main .tex is correctly detected.",
    "Diff not produced: install “latexdiff” (MiKTeX/TeX Live) and ensure it is on PATH; otherwise the app falls back to a standard PDF build.",
    "Nothing appears under a student: confirm the Students’ Root is correct and OneDrive has fully synced; click Scan or enable Auto-rescan."
])

# Directory structure
doc.h2("5. Standard directory layout (shared)")
doc.p("The following layout is produced under the Students’ Root:")
doc.p("""\
Students’ Root/
  <Student Name>/
    <manuscript-slug>/
      submissions/
        <YYYYMMDDHHMMSS>/
          payload/          ← submitted files (Word/LaTeX)
          manifest.json
      reviews/
        <submission-id>/
          working.docx      (Word flow, optional)
          compiled.pdf      (LaTeX)
          compiled_diff.pdf (LaTeX + latexdiff, optional)
          returned.docx / returned.html
          comments.json
      events/
        ... (submitted_at / returned_at timestamps)
""")

# OneDrive behaviour and sync
doc.h2("6. OneDrive behaviour and sync considerations")
doc.ul([
    "Paperforge relies on the operating system and OneDrive to transport files between users; the apps do not perform peer-to-peer transfers themselves.",
    "Visibility of new submissions and returned feedback depends on OneDrive completing both the upload on the sender’s machine and the download on the receiver’s machine.",
    "If something seems missing, check OneDrive’s status icons (blue arrows/spinning, green tick) and wait for synchronisation to finish. Then click Refresh (Student: Inbox; Supervisor: Scan).",
    "Large binaries or very many small files may slow synchronisation; consider excluding non-essential artefacts from submissions."
])

# Updates & security
doc.h2("7. Updates, signing, and provenance")
doc.ul([
    "Release archives are published on the official GitHub repository under “Releases”.",
    "Each archive is accompanied by a detached signature; the app verifies updates with a public key embedded at build time.",
    "If signature verification fails (for example, a modified or unofficial archive), the app refuses to update and informs you. Download only from the official repository."
])

# FAQ
doc.h2("8. Frequently asked questions (FAQ)")
doc.h3("Q1. When I restore, where do deleted files go?")
doc.p("If you choose CLEAN when restoring, Paperforge removes files from the working folder that are not part of the selected snapshot. The app does not send them to the Recycle Bin — removal is immediate. If you may need those files, make a separate backup first. If you choose OVERLAY, unrelated files are kept and only tracked files are overwritten.")
doc.h3("Q2. Why does a submission or a returned review take time to appear?")
doc.p("Because synchronisation is handled by OneDrive. The sender must finish uploading before the receiver can download. On both sides, verify OneDrive shows a green tick for the relevant folders. Network conditions and file sizes affect the delay.")
doc.h3("Q3. Can I change the Students’ Root later?")
doc.p("Yes. In Student, use Set/Change Students’ Root…. In Supervisor, use Choose Students’ Root…. Both apps remember your recent selections.")
doc.h3("Q4. Where are comments stored?")
doc.p("Comments are stored as JSON in “reviews/<submission-id>/comments.json”. For LaTeX returns, “returned.html” lists the general notes and itemised comments. Students can copy the comments file when pulling a returned review into their working folder.")
doc.h3("Q5. How do I speed up OneDrive?")
doc.ul([
    "Ensure you are signed in and OneDrive is not paused.",
    "Keep the Paperforge folders on a local drive (not a slow network share).",
    "Avoid submitting unnecessary large assets; prefer vector images or compressed formats where possible.",
    "Give OneDrive time to settle before expecting the other side to see changes."
])
doc.h3("Q6. Why does the LaTeX diff sometimes not appear?")
doc.p("The highlighted diff requires “latexdiff” to be installed and available on PATH on the Supervisor’s machine. Without it, the app builds a standard PDF instead, which is still linked from the return page.")
doc.h3("Q7. What happens if I click “No” on an update prompt?")
doc.p("Nothing is downloaded and your current version continues to run. You can check again later via Check for updates.")
doc.h3("Q8. The update progress appears to run forever.")
doc.p("Ensure the machine can reach GitHub Releases (corporate firewalls may block downloads). If the archive cannot be downloaded or verified, the app will eventually report an error; otherwise, if you suspect a stall, cancel, and try Check for updates again.")

# Rendering to PDF using matplotlib
pdf_path = "Paperforge_User_Guide_EN_GB.pdf"
pp = PdfPages(pdf_path)

def new_page():
    fig = plt.figure(figsize=(PAGE_W_IN, PAGE_H_IN))
    ax = fig.add_axes([0,0,1,1])
    ax.set_axis_off()
    return fig, ax

def draw_line(ax, x_in, y_in, text, fontsize=BODY_FONTSIZE, weight='normal'):
    # Convert inches to figure fraction for positioning
    x = x_in / PAGE_W_IN
    y = y_in / PAGE_H_IN
    ax.text(x, y, text, fontsize=fontsize, fontweight=weight, va='top', ha='left', wrap=False)

# State for layout
current_fig, current_ax = new_page()
cursor_y_in = PAGE_H_IN - MARGIN_IN  # start from top margin

def ensure_space(lines_needed):
    global current_fig, current_ax, cursor_y_in
    available_lines = int((cursor_y_in - MARGIN_IN) / BODY_LINE_IN)
    if available_lines < lines_needed:
        pp.savefig(current_fig, bbox_inches='tight')
        plt.close(current_fig)
        current_fig, current_ax = new_page()
        cursor_y_in = PAGE_H_IN - MARGIN_IN

def add_spacer(lines=1.0):
    global cursor_y_in
    cursor_y_in -= lines * BODY_LINE_IN

for kind, text in doc.blocks:
    if kind == "H1":
        # Leave space if near the bottom
        ensure_space(4)
        draw_line(current_ax, MARGIN_IN, cursor_y_in, text, fontsize=H1_SIZE, weight='bold')
        add_spacer(lines=2.0)
        continue
    if kind == "H2":
        ensure_space(3)
        draw_line(current_ax, MARGIN_IN, cursor_y_in, text, fontsize=H2_SIZE, weight='bold')
        add_spacer(lines=1.4)
        continue
    if kind == "H3":
        ensure_space(2)
        draw_line(current_ax, MARGIN_IN, cursor_y_in, text, fontsize=H3_SIZE, weight='bold')
        add_spacer(lines=1.0)
        continue
    if kind == "P":
        # Wrap and draw paragraph lines
        wrapped = wrap_paragraph(text, width=CHARS_PER_LINE)
        # Ensure enough space for this paragraph
        needed = max(1, len(wrapped)) + int(PARA_SPACING_LINES)
        ensure_space(needed)
        for line in wrapped:
            draw_line(current_ax, MARGIN_IN, cursor_y_in, line, fontsize=BODY_FONTSIZE)
            add_spacer(lines=1.0)
        add_spacer(lines=PARA_SPACING_LINES)
        continue

# Save last page
pp.savefig(current_fig, bbox_inches='tight')
plt.close(current_fig)
pp.close()