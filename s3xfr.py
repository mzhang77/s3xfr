'''
usage:

python s3xfr.py send ./data

python s3xfr.py receive '<token>' -o ./received
python s3xfr.py receive 3 -o ./received

python s3xfr.py history

python s3xfr.py remote-history

optional config file:
~/.s3xfr.json

example:
{
  "S3_TRANSFER_BUCKET": "my-temp-bucket",
  "S3_TRANSFER_PREFIX": "tmp-transfer",
  "AWS_DEFAULT_REGION": "us-west-2"
}

Environment variables override config file values.
'''



#!/usr/bin/env python3
import argparse
import base64
import json
import os
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

import boto3



HISTORY_FILE = Path.home() / ".s3xfr_history.jsonl"
CONFIG_FILE = Path.home() / ".s3xfr.json"
MANIFEST_NAME = "manifest.json"


def load_config():
    if not CONFIG_FILE.exists():
        return

    with open(CONFIG_FILE) as f:
        config = json.load(f)

    for key, value in config.items():
        if value is not None and key not in os.environ:
            os.environ[key] = str(value)


def save_history(src_path: str, token: str, bucket: str, key: str):
    record = {
        "time": int(time.time()),
        "src": str(Path(src_path).resolve()),
        "bucket": bucket,
        "key": key,
        "token": token,
    }

    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


# Manifest helpers
def manifest_key(prefix: str) -> str:
    return f"{prefix.rstrip('/')}/{MANIFEST_NAME}"


def write_manifest(s3, bucket: str, prefix: str, record: dict):
    key = manifest_key(prefix)
    manifest = []

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        manifest = json.loads(obj["Body"].read().decode())
    except s3.exceptions.NoSuchKey:
        manifest = []
    except Exception:
        manifest = []

    manifest.append(record)

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )


def read_manifest(s3, bucket: str, prefix: str):
    key = manifest_key(prefix)
    obj = s3.get_object(Bucket=bucket, Key=key)
    return json.loads(obj["Body"].read().decode())


def resolve_receive_meta(value: str) -> dict:
    """Resolve a receive argument as either a remote-history index or a token."""
    if not value.isdigit():
        return b64url_decode(value)

    index = int(value)
    if index <= 0:
        raise ValueError("History index must be 1 or greater")

    bucket = os.environ["S3_TRANSFER_BUCKET"]
    prefix = os.environ.get("S3_TRANSFER_PREFIX", "machine-transfer")

    s3 = boto3.client("s3")
    records = read_manifest(s3, bucket, prefix)

    if index > len(records):
        raise IndexError(f"History index {index} is out of range; remote history has {len(records)} item(s)")

    record = records[index - 1]
    if "token" in record:
        return b64url_decode(record["token"])

    return {
        "bucket": record["bucket"],
        "key": record["key"],
        "type": "tar.gz",
        "created_at": record.get("time"),
    }


def b64url_encode(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def b64url_decode(token: str) -> dict:
    padding = "=" * (-len(token) % 4)
    raw = base64.urlsafe_b64decode(token + padding)
    return json.loads(raw)


def make_archive(src: Path) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".tar.gz")[1])
    with tarfile.open(tmp, "w:gz") as tar:
        tar.add(src, arcname=src.name)
    return tmp


def send(args):
    bucket = os.environ["S3_TRANSFER_BUCKET"]
    prefix = os.environ.get("S3_TRANSFER_PREFIX", "machine-transfer")

    src = Path(args.path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)

    archive = make_archive(src)
    object_key = f"{prefix}/{int(time.time())}-{uuid.uuid4().hex}.tar.gz"

    s3 = boto3.client("s3")
    s3.upload_file(str(archive), bucket, object_key)

    created_at = int(time.time())
    token = b64url_encode({
        "bucket": bucket,
        "key": object_key,
        "type": "tar.gz",
        "created_at": created_at,
    })

    record = {
        "time": created_at,
        "src": str(src),
        "bucket": bucket,
        "key": object_key,
        "token": token,
    }

    save_history(src, token, bucket, object_key)
    write_manifest(s3, bucket, prefix, record)

    print(token)
    print(f"History saved to: {HISTORY_FILE}")
    print(f"Manifest saved to: s3://{bucket}/{manifest_key(prefix)}")

def history(args):
    if not HISTORY_FILE.exists():
        print("No history found")
        return

    with open(HISTORY_FILE) as f:
        for line in f:
            r = json.loads(line)
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['time']))}")
            print(f"SRC   : {r['src']}")
            print(f"TOKEN : {r['token']}")
            print()


# Remote history
def remote_history(args):
    bucket = os.environ["S3_TRANSFER_BUCKET"]
    prefix = os.environ.get("S3_TRANSFER_PREFIX", "machine-transfer")

    s3 = boto3.client("s3")
    records = read_manifest(s3, bucket, prefix)

    for i, r in enumerate(records, 1):
        print(f"[{i}] {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['time']))}")
        print(f"SRC   : {r['src']}")
        print(f"S3    : s3://{r['bucket']}/{r['key']}")
        print(f"TOKEN : {r['token']}")
        print()


def receive(args):
    meta = resolve_receive_meta(args.token)

    bucket = meta["bucket"]
    key = meta["key"]

    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = out_dir / Path(key).name

    s3 = boto3.client("s3")
    s3.download_file(bucket, key, str(tmp))

    with tarfile.open(tmp, "r:gz") as tar:
        tar.extractall(out_dir)

    print(f"Downloaded and extracted to: {out_dir}")


def main():
    parser = argparse.ArgumentParser()
    load_config()
    sub = parser.add_subparsers(required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("path")
    p_send.set_defaults(func=send)

    p_recv = sub.add_parser("receive")
    p_recv.add_argument("token", help="Transfer token, or a number from remote-history")
    p_recv.add_argument("-o", "--output", default=".")
    p_recv.set_defaults(func=receive)

    p_hist = sub.add_parser("history")
    p_hist.set_defaults(func=history)

    p_remote_hist = sub.add_parser("remote-history")
    p_remote_hist.set_defaults(func=remote_history)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()