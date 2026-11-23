#!/bin/bash
set -e
echo "Fetching updates from official MediaFusion..."
git fetch upstream main
echo "Merging upstream into your custom branch..."
git checkout custom-prod
git merge upstream/main -m "Merge official MediaFusion updates"
echo "Sync complete!"
