# s3xfr

A tiny utility for transferring files and directories between machines using S3.

Instead of setting up SCP, SSH access, VPNs, or temporary web servers, `s3xfr` uploads an archive to a shared S3 bucket and generates a portable token. Any machine with access to the same AWS account can use the token to download and extract the content.

## Features

- Transfer files or directories between machines
- Uses S3 as the transport layer
- Single-token download workflow
- Keeps local transfer history
- Maintains a remote manifest in S3
- Optional configuration file support
- No server required

## Requirements

Python 3.8+

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure AWS credentials:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
export AWS_DEFAULT_REGION=us-west-2
```

Configure transfer bucket:

```bash
export S3_TRANSFER_BUCKET=my-temp-bucket
export S3_TRANSFER_PREFIX=tmp-transfer
```

Or create an optional config file:

```json
~/.s3xfr.json

{
  "S3_TRANSFER_BUCKET": "my-temp-bucket",
  "S3_TRANSFER_PREFIX": "tmp-transfer",
  "AWS_DEFAULT_REGION": "us-west-2"
}
```

Environment variables always override values from the config file.

## Send

```bash
python s3xfr.py send ./data
```

The command uploads the file or directory and prints a transfer token.

## Receive

```bash
python s3xfr.py receive '<token>'
```

Or specify an output directory:

```bash
python s3xfr.py receive '<token>' -o ./received
```

## Local History

```bash
python s3xfr.py history
```

History is stored in:

```text
~/.s3xfr_history.jsonl
```

## Remote History

```bash
python s3xfr.py remote-history
```

The manifest is stored at:

```text
s3://$S3_TRANSFER_BUCKET/$S3_TRANSFER_PREFIX/manifest.json
```

## Configuration

`s3xfr` loads configuration in the following order:

1. Environment variables
2. `~/.s3xfr.json`
3. Built-in defaults

This allows a shared default configuration while still making it easy to temporarily override settings from the shell.

## How It Works

When sending:

1. Archive source as `.tar.gz`
2. Upload archive to S3
3. Generate a portable token
4. Save metadata locally (~/.s3xfr_history.jsonl)
5. Update remote manifest in S3 (manifest.json)

When receiving:

1. Decode token
2. Download archive from S3
3. Extract contents

## Example

Machine A:

```bash
python s3xfr.py send ./logs
```

Machine B:

```bash
python s3xfr.py receive '<token>' -o ./logs
```

Done.

## License

MIT
