Git Hooks: Commit-msg Checker

Dieses Repo enthält einen Commit-Message-Checker unter `.githooks/`.

Enthaltene Dateien:

- `.githooks/check_commit_msg.py` — Python-Skript, das die Commit-Nachricht prüft.
- `.githooks/commit-msg` — Unix-Shell-Wrapper für die Hook-Ausführung.
- `.githooks/commit-msg.ps1` — PowerShell-Wrapper für Windows.

Verhalten:
- Wenn die erste Zeile der Commit-Nachricht mit `Release ` beginnt, wird geprüft, ob sie dem Muster `Release x.x.x - <Kurzbeschreibung>` entspricht.
- Bei Nichtübereinstimmung wird der Commit abgebrochen und eine Fehlermeldung ausgegeben.
- Alle anderen Commit-Nachrichten werden nicht blockiert.

Aktivieren der Hooks (einmalig lokal im Repository):

```powershell
# Setze Git dazu, Hooks aus dem Repository-Verzeichnis zu verwenden
git config core.hooksPath .githooks
```

PowerShell-Hook: Das Hook-Skript versucht zuerst, die Python-Executable aus der Projekt-`.venv` (`.venv\Scripts\python.exe`) zu verwenden. Falls diese nicht vorhanden ist, wird die Umgebungsvariable `PYTHON` genutzt; als letzter Fallback wird `python` aus dem PATH aufgerufen.

Hinweis:
- Das Setzen von `core.hooksPath` ist lokal zur Arbeitskopie und wird nicht automatisch auf andere Klone übertragen.
- Team-Mitglieder sollten ebenfalls `git config core.hooksPath .githooks` ausführen oder ein Setup-Script verwenden.

Wenn du möchtest, kann ich ein kurzes `scripts/setup_hooks.ps1` hinzufügen, das das in einem Schritt für Windows und WSL erledigt.
