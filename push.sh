#!/usr/bin/env bash
# One-shot: commit whatever is in the working tree and push to GitHub.
#   ./push.sh "message"
set -euo pipefail
cd "$(dirname "$0")"
MSG="${1:?pass a commit message: ./push.sh \"your message\"}"
git add -A
git -c user.name="Akshat Agrawal" -c user.email="akshatxagrawal@gmail.com" \
    commit -q -m "$MSG" || { echo "nothing new to commit"; exit 0; }
git push -q origin main
echo "pushed -> https://github.com/5upernova4/NLP-Prepathon-Customer360"
