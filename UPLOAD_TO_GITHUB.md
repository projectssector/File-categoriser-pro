# Publish this on GitHub

This folder is ready to become a GitHub repository. The large installer is in
`release\` and is **not** committed to Git. It is attached to a GitHub
**Release** instead. GitHub rejects normal repository files over 100 MB, and
the installer is much larger than that.

## Before you start

**Revoke the old Gemini API key.** A key was previously stored in
`.env.example` in the source folder. It has been removed from this package,
but if the old folder was ever uploaded or shared, revoke that key at
<https://aistudio.google.com/apikey> and create a new one. Never commit
`.env` or `data/settings.json`.

## 1. Create the repository

1. Sign in to GitHub and click **New repository**.
2. Name it `file-categorizer` (or anything you like).
3. Choose **Public**.
4. Do **not** add a README, `.gitignore` or license (this folder has them).
5. Click **Create repository**.

## 2. Upload the files

### Option A: GitHub Desktop (easiest)

1. Install GitHub Desktop from <https://desktop.github.com/>.
2. **File** > **Add local repository** and choose this `github ready` folder.
3. When asked, click **create a repository** here.
4. Commit the files with the message `File Categorizer 1.0.0`.
5. Click **Publish repository** and choose the repository you created.

The `.gitignore` already excludes `release\*.exe`, `data\`, `.env`, build
output and Python caches.

### Option B: Command line

Open PowerShell in this folder and run:

```powershell
git init
git add .
git commit -m "File Categorizer 1.0.0"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/file-categorizer.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. If Git asks for a
password, use a Personal Access Token instead.

Check that the installer was not committed:

```powershell
git status --ignored
```

`release\FileCategorizer-Setup-1.0.0.exe` should appear as ignored.

## 3. Create the release and attach the installer

1. In the repository, click **Releases** > **Draft a new release**.
2. Click **Choose a tag**, type `v1.0.0`, and select **Create new tag**.
3. Release title: `File Categorizer 1.0.0`.
4. In the description, paste the contents of `RELEASE_NOTES.md`.
5. Under **Attach binaries**, upload:
   - `release\FileCategorizer-Setup-1.0.0.exe`
   - `SHA256SUMS.txt`
6. Click **Publish release**.

GitHub allows a single release asset up to 2 GB, so this installer is fine.

## 4. Check the download link

The README links to `../../releases/latest`, which resolves to the newest
release in the repository. Open the repository page and click the download
link once to confirm it starts the installer download.

## 5. Optional polish

- Add a repository description: `Local-first AI file organizer for Windows`.
- Add topics: `windows`, `python`, `ai`, `file-organizer`, `clip`, `pyside6`.
- Add a screenshot or short GIF at the top of `README.md`.
- Keep `SECURITY.md` visible so users know not to commit API keys.
- Replace the MIT license holder if you want a different name. The current
  file says `File Categorizer contributors`.

## Updating the app later

1. Change the version in:
   - `FileCategorizer.iss` (`MyAppVersion`)
   - `pyproject.toml`
   - `src\file_categorizer\__init__.py`
   - `version_info.txt`
2. Rebuild:

   ```powershell
   python -m PyInstaller FileCategorizer.spec --noconfirm --clean
   & "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" FileCategorizer.iss
   ```

3. Create a new GitHub Release (for example `v1.0.1`) and attach the new
   `FileCategorizer-Setup-1.0.1.exe`.
4. Update `SHA256SUMS.txt` with the new hash.
