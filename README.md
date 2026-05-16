# ALGOS
Algorithmic Trading Strategies Codes

## YouTube car Shorts uploader

Use `youtube_car_shorts_uploader.py` to upload car short videos to your YouTube channel.

Install dependencies:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
```

Run:

```bash
python youtube_car_shorts_uploader.py \
  --videos-dir /absolute/path/to/your/videos \
  --client-secrets /absolute/path/to/client_secrets.json \
  --privacy-status private
```

Only files with car-related keywords in the filename are uploaded, and uploaded files are tracked in `.uploaded_car_shorts.json`.
