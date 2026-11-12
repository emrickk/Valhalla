#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Install Python 3.11+ first: https://www.python.org/downloads/'
else
  python3 clean_phone.py
fi
printf '\nPress Enter to close...'
read -r answer
