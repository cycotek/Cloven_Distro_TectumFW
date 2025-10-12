### ✅ Final `update_readme.sh`


```bash
#!/bin/bash


# ---- Auto-generate README.md and ABOUT.md from templates ----


set -e


# Metadata
GIT_HASH=$(git rev-parse --short HEAD)
DATE=$(date '+%Y-%m-%d')
VERSION_FILE=".version"


# Auto-increment patch version
if [ -f "$VERSION_FILE" ]; then
VERSION=$(cat $VERSION_FILE)
MAJOR=$(echo $VERSION | cut -d. -f1)
MINOR=$(echo $VERSION | cut -d. -f2)
PATCH=$(echo $VERSION | cut -d. -f3)
PATCH=$((PATCH + 1))
VERSION="$MAJOR.$MINOR.$PATCH"
else
VERSION="0.1.0"
fi


# Save new version
echo $VERSION > $VERSION_FILE


# Replace placeholders in README
for template in README.template.md ABOUT.template.md; do
output="${template%.template.md}.md"
sed -e "s/{{VERSION}}/$VERSION/g" \
-e "s/{{GIT_HASH}}/$GIT_HASH/g" \
-e "s/{{DATE}}/$DATE/g" \
"$template" > "$output"
echo "✅ Generated $output"
done
