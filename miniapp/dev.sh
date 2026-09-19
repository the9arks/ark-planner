#!/bin/bash
export PATH="/Users/germangrisin/.nvm/versions/node/v24.21.0/bin:$PATH"
cd "$(dirname "$0")"
exec npm run dev -- --host
