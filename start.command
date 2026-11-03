#!/bin/bash
cd "$(dirname "$0")"
(sleep 1 && open http://localhost:3001) &
python3 server.py
