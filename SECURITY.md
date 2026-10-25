# Security

## Never commit secrets

Do not commit any of the following:

- `.env`
- `data/settings.json` (it can contain a Gemini API key)
- `config/config.yaml` if you added private paths or keys
- `data/cache.db` (contains your local file metadata)

These paths are listed in `.gitignore`.

## API keys

A Gemini API key is optional. If you add one, it is stored locally in
`%USERPROFILE%\FileCategorizer\data\settings.json`. Revoke it at
<https://aistudio.google.com/apikey> if it is ever exposed.

If a key was previously committed or shared, revoke it immediately and
create a new one. Removing it from a later commit does not remove it from
Git history.

## Reporting a problem

Open a private security advisory on GitHub or contact the repository owner.
Do not include API keys, personal paths or private screenshots in a public
issue.
