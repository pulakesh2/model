# Stillframe

A Flask photo and video sharing site with account registration, a community feed, media uploads, per-user ratings, and a profile gallery.

## Run locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY = "replace-this-with-a-long-random-value"
python app.py
```

Open `http://127.0.0.1:5000`. The SQLite database (`photo_ratings.db`) and uploads in `static/uploads/` are created automatically. Upload PNG, JPG, GIF, WebP, MP4, WebM, or MOV files up to 100 MB. Clicking a feed item opens the full size media viewer. Each account can rate a post once; submitting another rating updates that user's rating. Accounts cannot rate their own posts.
