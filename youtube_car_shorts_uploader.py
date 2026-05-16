import argparse
import json
from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
DEFAULT_CAR_KEYWORDS = (
    "car",
    "cars",
    "supercar",
    "mustang",
    "ferrari",
    "bmw",
    "audi",
    "lamborghini",
    "porsche",
    "mercedes",
    "tesla",
)


def load_uploaded_state(state_file: Path) -> set[str]:
    if not state_file.exists():
        return set()
    try:
        return set(json.loads(state_file.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def save_uploaded_state(state_file: Path, uploaded_files: set[str]) -> None:
    temp_file = state_file.with_name(f"{state_file.name}.tmp")
    temp_file.write_text(
        json.dumps(sorted(uploaded_files), indent=2),
        encoding="utf-8",
    )
    temp_file.replace(state_file)


def authenticate(client_secrets_path: Path, token_file: Path) -> Resource:
    credentials = None

    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_path), SCOPES
            )
            credentials = flow.run_local_server(port=0)
        token_file.write_text(credentials.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=credentials)


def candidate_videos(
    videos_dir: Path, car_keywords: Iterable[str], uploaded_state: set[str]
) -> list[Path]:
    keywords = tuple(keyword.strip().lower() for keyword in car_keywords if keyword.strip())
    candidates = []

    for file_path in sorted(videos_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        file_name = file_path.name.lower()
        if not any(keyword in file_name for keyword in keywords):
            continue

        if str(file_path.resolve()) in uploaded_state:
            continue

        candidates.append(file_path)

    return candidates


def upload_video(
    youtube: Resource,
    file_path: Path,
    title_prefix: str,
    privacy_status: str,
    category_id: str,
) -> str:
    title = f"{title_prefix} {file_path.stem}".strip()[:100]
    description = f"Car short: {file_path.stem}\n#shorts #cars"
    tags = ["shorts", "cars", "carvideos"]

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media_file = MediaFileUpload(str(file_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media_file,
    )

    response = None
    attempts = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as error:
            attempts += 1
            print(f"Upload retry {attempts}/3 after API error: {error}")
            if attempts >= 3:
                raise
        except Exception as error:
            attempts += 1
            print(f"Upload retry {attempts}/3 after unexpected error: {error}")
            if attempts >= 3:
                raise

    return response["id"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Automatically upload car Shorts from a local folder to YouTube."
    )
    parser.add_argument("--videos-dir", required=True, help="Folder with video files.")
    parser.add_argument(
        "--client-secrets",
        default="client_secrets.json",
        help="OAuth client secrets JSON from Google Cloud.",
    )
    parser.add_argument(
        "--token-file",
        default="youtube_token.json",
        help="Path to store OAuth access token.",
    )
    parser.add_argument(
        "--state-file",
        default=".uploaded_car_shorts.json",
        help="Path used to remember already uploaded files.",
    )
    parser.add_argument(
        "--title-prefix",
        default="Car Shorts",
        help="Prefix added to uploaded video title.",
    )
    parser.add_argument(
        "--privacy-status",
        default="private",
        choices=["private", "public", "unlisted"],
        help="Visibility for uploaded videos.",
    )
    parser.add_argument(
        "--category-id",
        default="2",
        help="YouTube category id. '2' is Autos & Vehicles.",
    )
    parser.add_argument(
        "--max-uploads",
        type=int,
        default=3,
        help="Max number of videos to upload in one run.",
    )
    parser.add_argument(
        "--car-keywords",
        default=",".join(DEFAULT_CAR_KEYWORDS),
        help="Comma-separated keywords. Only files containing these terms are uploaded.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    videos_dir = Path(args.videos_dir).resolve()
    client_secrets_path = Path(args.client_secrets).resolve()
    token_file = Path(args.token_file).resolve()
    state_file = Path(args.state_file).resolve()

    if not videos_dir.exists() or not videos_dir.is_dir():
        raise FileNotFoundError(f"Videos directory not found: {videos_dir}")
    if not client_secrets_path.exists():
        raise FileNotFoundError(f"Client secrets file not found: {client_secrets_path}")

    uploaded_state = load_uploaded_state(state_file)
    keywords = [keyword.strip() for keyword in args.car_keywords.split(",")]
    videos = candidate_videos(videos_dir, keywords, uploaded_state)[: args.max_uploads]

    if not videos:
        print("No matching car short videos found to upload.")
        return

    youtube = authenticate(client_secrets_path, token_file)

    for video in videos:
        try:
            video_id = upload_video(
                youtube=youtube,
                file_path=video,
                title_prefix=args.title_prefix,
                privacy_status=args.privacy_status,
                category_id=args.category_id,
            )
            uploaded_state.add(str(video.resolve()))
            save_uploaded_state(state_file, uploaded_state)
            print(f"Uploaded: {video.name} | videoID={video_id}")
        except HttpError as error:
            print(f"Failed to upload {video.name}: {error}")
        except Exception as error:
            print(f"Unexpected failure for {video.name}: {error}")


if __name__ == "__main__":
    main()
