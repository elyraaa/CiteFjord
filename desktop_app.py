"""Native desktop interface for CiteFjord."""

from __future__ import annotations

import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from src.library import (
    APP_NAME, TEXT_SUFFIXES, app_home, database_dir, delete_documents,
    document_dir, import_document, index_is_current, list_documents,
    mark_index_current, read_document, save_document,
)

if getattr(sys, "frozen", False):
    packaged_cache = Path(sys.executable).parent / "model_cache"
    os.environ.setdefault("RAG_MODEL_CACHE", str(packaged_cache if packaged_cache.is_dir() else app_home() / "model_cache"))

class CiteFjordApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1100x760")
        self.root.minsize(780, 560)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.busy = False
        self.dirty = False
        self.index_pending = not index_is_current()
        self.selected_name: str | None = None
        self.file_names: list[str] = []
        self.status = tk.StringVar(value="Ready. Add files or ask a question.")
        self._build()
        self._refresh_files()
        self.root.after(100, self._poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        heading = ttk.Frame(outer)
        heading.pack(fill="x", pady=(0, 10))
        ttk.Label(heading, text=APP_NAME, font=("Segoe UI", 17, "bold")).pack(side="left")
        self.index_button = ttk.Button(heading, text="Update Index", command=self._index)
        self.index_button.pack(side="right")

        body = ttk.PanedWindow(outer, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=3)

        ttk.Label(left, text="Your files", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(left, text="Text, code, Markdown, and PDF").pack(anchor="w", pady=(0, 6))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(list_frame, selectmode="extended", exportselection=False, activestyle="none")
        self.file_list.pack(side="left", fill="both", expand=True)
        file_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        file_scroll.pack(side="right", fill="y")
        self.file_list.configure(yscrollcommand=file_scroll.set)
        self.file_list.bind("<<ListboxSelect>>", self._on_select)
        file_actions = ttk.Frame(left)
        file_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(file_actions, text="Add Files", command=self._add_files).grid(row=0, column=0, padx=(0, 4), pady=2, sticky="ew")
        ttk.Button(file_actions, text="New Text File", command=self._new_file).grid(row=0, column=1, pady=2, sticky="ew")
        ttk.Button(file_actions, text="Delete", command=self._delete_file).grid(row=1, column=0, padx=(0, 4), pady=2, sticky="ew")
        ttk.Button(file_actions, text="Delete Selected", command=self._delete_selected).grid(row=1, column=1, pady=2, sticky="ew")
        ttk.Button(file_actions, text="Select All", command=self._select_all).grid(row=2, column=0, columnspan=2, pady=2, sticky="ew")
        ttk.Label(left, text="Use Ctrl or Shift to select multiple files.").pack(anchor="w", pady=(4, 0))
        file_actions.columnconfigure(0, weight=1)
        file_actions.columnconfigure(1, weight=1)

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        editor_tab = ttk.Frame(notebook, padding=8)
        ask_tab = ttk.Frame(notebook, padding=8)
        notebook.add(editor_tab, text="Edit files")
        notebook.add(ask_tab, text="Ask questions")
        self.notebook = notebook

        editor_header = ttk.Frame(editor_tab)
        editor_header.pack(fill="x", pady=(0, 6))
        self.editor_title = ttk.Label(editor_header, text="Choose a text file to edit")
        self.editor_title.pack(side="left")
        self.save_button = ttk.Button(editor_header, text="Save Changes", command=self._save, state="disabled")
        self.save_button.pack(side="right")
        editor_frame = ttk.Frame(editor_tab)
        editor_frame.pack(fill="both", expand=True)
        self.editor = tk.Text(editor_frame, wrap="none", undo=True, font=("Consolas", 10), state="disabled")
        self.editor.pack(side="left", fill="both", expand=True)
        editor_scroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self.editor.yview)
        editor_scroll.pack(side="right", fill="y")
        self.editor.configure(yscrollcommand=editor_scroll.set)
        self.editor.bind("<<Modified>>", self._on_modified)
        ttk.Label(editor_tab, text="PDFs are searchable but cannot be edited here. Imported files are copies in this app's library.").pack(anchor="w", pady=(6, 0))

        ttk.Label(ask_tab, text="Ask about your indexed files", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        question_row = ttk.Frame(ask_tab)
        question_row.pack(fill="x", pady=(8, 8))
        self.question = ttk.Entry(question_row)
        self.question.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.question.bind("<Return>", lambda _event: self._ask())
        self.ask_button = ttk.Button(question_row, text="Ask", command=self._ask)
        self.ask_button.pack(side="right")
        ttk.Label(ask_tab, text="Answer and sources").pack(anchor="w")
        answer_frame = ttk.Frame(ask_tab)
        answer_frame.pack(fill="both", expand=True)
        self.answer = tk.Text(answer_frame, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.answer.pack(side="left", fill="both", expand=True)
        answer_scroll = ttk.Scrollbar(answer_frame, orient="vertical", command=self.answer.yview)
        answer_scroll.pack(side="right", fill="y")
        self.answer.configure(yscrollcommand=answer_scroll.set)

        ttk.Separator(outer).pack(fill="x", pady=(10, 6))
        ttk.Label(outer, textvariable=self.status, anchor="w").pack(fill="x")

    def _refresh_files(self, select: str | None = None) -> None:
        self.file_names = [path.name for path in list_documents()]
        self.file_list.delete(0, "end")
        for name in self.file_names:
            self.file_list.insert("end", name)
        if select in self.file_names:
            index = self.file_names.index(select)
            self.file_list.selection_set(index)
            self.file_list.see(index)

    def _select_previous(self) -> None:
        self.file_list.selection_clear(0, "end")
        if self.selected_name in self.file_names:
            self.file_list.selection_set(self.file_names.index(self.selected_name))

    def _confirm_unsaved(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved changes", "Save changes to the current file?", parent=self.root)
        if answer is None:
            return False
        if answer:
            return self._save()
        self.dirty = False
        return True

    def _on_select(self, _event: object = None) -> None:
        chosen = self.file_list.curselection()
        if not chosen:
            return
        active = self.file_list.index("active")
        name = self.file_names[active if active in chosen else chosen[0]]
        if name == self.selected_name:
            return
        if not self._confirm_unsaved():
            self._select_previous()
            return
        self.selected_name = name
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.edit_modified(False)
        if Path(name).suffix.lower() in TEXT_SUFFIXES:
            try:
                content = read_document(name)
            except (OSError, UnicodeError, ValueError) as exc:
                self.editor_title.configure(text=f"{name} — cannot edit: {exc}")
                self.editor.configure(state="disabled")
                self.save_button.configure(state="disabled")
                return
            self.editor.insert("1.0", content)
            self.editor.edit_modified(False)
            self.editor_title.configure(text=name)
            self.save_button.configure(state="normal")
        else:
            self.editor_title.configure(text=f"{name} — PDF (read only)")
            self.editor.configure(state="disabled")
            self.save_button.configure(state="disabled")
        self.dirty = False

    def _on_modified(self, _event: object) -> None:
        if self.editor.edit_modified():
            if self.selected_name and str(self.editor.cget("state")) == "normal":
                self.dirty = True
                self.status.set(f"Unsaved changes: {self.selected_name}")
            self.editor.edit_modified(False)

    def _save(self) -> bool:
        if self.busy:
            messagebox.showinfo("Please wait", "Wait for the current operation to finish before saving.", parent=self.root)
            return False
        if not self.selected_name or Path(self.selected_name).suffix.lower() not in TEXT_SUFFIXES:
            return False
        try:
            save_document(self.selected_name, self.editor.get("1.0", "end-1c"))
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("Could not save", str(exc), parent=self.root)
            return False
        self.dirty = False
        self.index_pending = True
        self._clear_answer()
        self.status.set(f"Saved {self.selected_name}. Update the index to search the new content.")
        return True

    def _new_file(self) -> None:
        if self.busy or not self._confirm_unsaved():
            return
        name = simpledialog.askstring("New file", "Name, including .txt or .md:", parent=self.root)
        if not name:
            return
        try:
            save_document(name, "", create=True)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Could not create file", str(exc), parent=self.root)
            return
        self.index_pending = True
        self._clear_answer()
        self._refresh_files(name)
        self._on_select()
        self.status.set(f"Created {name}. Add your text, save, then update the index.")

    def _add_files(self) -> None:
        if self.busy or not self._confirm_unsaved():
            return
        paths = filedialog.askopenfilenames(parent=self.root, title="Add files to your library")
        if not paths:
            return
        imported: list[str] = []
        errors: list[str] = []
        for raw_path in paths:
            source = Path(raw_path)
            try:
                existing = (document_dir() / source.name).exists()
                overwrite = False
                if existing:
                    overwrite = messagebox.askyesno("Replace file?", f"Replace {source.name} in the library?", parent=self.root)
                    if not overwrite:
                        continue
                target = import_document(source, overwrite=overwrite)
                imported.append(target.name)
            except (OSError, ValueError) as exc:
                errors.append(f"{source.name}: {exc}")
        if imported:
            self.index_pending = True
            self._clear_answer()
            self.selected_name = None
            self.dirty = False
            self._refresh_files(imported[-1])
            self._on_select()
            self.status.set(f"Added {len(imported)} file(s). Update the index to search them.")
        if errors:
            messagebox.showerror("Some files were not added", "\n".join(errors), parent=self.root)

    def _delete_file(self) -> None:
        if self.busy or not self.selected_name:
            return
        self._delete_names([self.selected_name])

    def _select_all(self) -> None:
        if self.file_names:
            self.file_list.selection_set(0, "end")

    def _delete_selected(self) -> None:
        if self.busy:
            return
        names = [self.file_names[index] for index in self.file_list.curselection()]
        if names:
            self._delete_names(names)

    def _delete_names(self, names: list[str]) -> None:
        if not self._confirm_unsaved():
            return
        count = len(names)
        prompt = (f"Delete {names[0]} from this app's library?" if count == 1
                  else f"Delete {count} selected files from this app's library?")
        if not messagebox.askyesno("Delete files?", prompt, parent=self.root):
            return
        result = delete_documents(names)
        if not result.deleted and result.failed:
            messagebox.showerror("Could not delete", "\n".join(f"{name}: {error}" for name, error in result.failed), parent=self.root)
            return
        self.selected_name = None
        self.dirty = False
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.configure(state="disabled")
        self.editor_title.configure(text="Choose a text file to edit")
        self.save_button.configure(state="disabled")
        self._refresh_files()
        self.index_pending = True
        self._clear_answer()
        self.status.set(f"Deleted {len(result.deleted)} file(s). Update the index to remove them from search.")
        if result.failed:
            messagebox.showerror("Some files were not deleted", "\n".join(f"{name}: {error}" for name, error in result.failed), parent=self.root)

    def _clear_answer(self) -> None:
        self.answer.configure(state="normal")
        self.answer.delete("1.0", "end")
        self.answer.configure(state="disabled")

    def _start_job(self, action: str, fn: object) -> None:
        if self.busy:
            return
        self.busy = True
        self.index_button.configure(state="disabled")
        self.ask_button.configure(state="disabled")
        self.status.set(f"{action}…")

        def work() -> None:
            try:
                result = fn()
                self.events.put(("done", (action, result)))
            except Exception as exc:
                try:
                    home = app_home()
                    home.mkdir(parents=True, exist_ok=True)
                    (home / "last-error.log").write_text(f"{action}\n{traceback.format_exc()}", encoding="utf-8")
                except OSError:
                    pass
                self.events.put(("error", (action, str(exc))))

        threading.Thread(target=work, daemon=True).start()

    def _index(self) -> None:
        if not self._confirm_unsaved():
            return
        def run_index():
            from src.ingest import ingest_folder
            return ingest_folder(document_dir(), database_dir(), offline=getattr(sys, "frozen", False))
        self._start_job("Indexing files", run_index)

    def _ask(self) -> None:
        question = self.question.get().strip()
        if not question:
            messagebox.showinfo("Enter a question", "Type a question first.", parent=self.root)
            return
        if not self._confirm_unsaved():
            return
        if self.index_pending or not index_is_current():
            self.index_pending = True
            self._clear_answer()
            messagebox.showinfo("Update index", "Your files have changed. Use Update Index before asking.", parent=self.root)
            return
        self.notebook.select(1)
        def run_question():
            from src.retriever import ask
            return ask(question, db_path=database_dir())
        self._start_job("Finding answer", run_question)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                action, value = payload
                self.busy = False
                self.index_button.configure(state="normal")
                self.ask_button.configure(state="normal")
                if kind == "error":
                    self.status.set(f"{action} failed")
                    messagebox.showerror(action, str(value), parent=self.root)
                elif action == "Indexing files":
                    try:
                        mark_index_current()
                    except OSError as exc:
                        self.status.set("Index updated, but its state could not be saved")
                        messagebox.showerror("Index state", str(exc), parent=self.root)
                        continue
                    self.index_pending = False
                    self._clear_answer()
                    self.status.set(
                        f"Index ready: {value.scanned} scanned, {value.indexed} updated, "
                        f"{value.unchanged} unchanged, {value.removed} removed."
                    )
                else:
                    lines = [value.answer]
                    if value.sources:
                        lines += ["", "Sources:"]
                        for source in value.sources:
                            page = f", page {source.page}" if source.page else ""
                            lines.append(f"[{source.number}] {source.relative_path}{page}")
                    self.answer.configure(state="normal")
                    self.answer.delete("1.0", "end")
                    self.answer.insert("1.0", "\n".join(lines))
                    self.answer.configure(state="disabled")
                    self.status.set("Answer ready")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _close(self) -> None:
        if self.busy:
            messagebox.showinfo("Please wait", "Wait for the current operation to finish before closing.", parent=self.root)
            return
        if self._confirm_unsaved():
            self.root.destroy()


def main() -> None:
    if sys.argv[1:] == ["--index-once"]:
        from src.ingest import ingest_folder
        home = app_home()
        home.mkdir(parents=True, exist_ok=True)
        try:
            result = ingest_folder(document_dir(), database_dir(), offline=True)
            mark_index_current()
            (home / "index-diagnostic.txt").write_text(f"SUCCESS: {result}\n", encoding="utf-8")
        except Exception:
            (home / "index-diagnostic.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    CiteFjordApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
